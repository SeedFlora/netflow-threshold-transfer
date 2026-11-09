"""Derived numbers for the round-2 revision, computed from existing frozen artifacts.

Run: .venv/Scripts/python.exe scripts/revision_numbers.py
Writes results/revision_numbers.json. Reads only; never refits or rescans thresholds.
Every number added to the revised manuscript that is not already in an earlier
results file is produced here, so its provenance is one script and one JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (42, 2026, 3407)
N_BENIGN_T, N_ATTACK_T, N_BENIGN_S = 1108481, 110219, 337801


def clopper_pearson(k: int, n: int, level: float = 0.95):
    a = 1 - level
    lo = 0.0 if k == 0 else float(beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a / 2, k + 1, n - k))
    return [lo, hi]


def main() -> None:
    split = json.loads((ROOT / "reports/split_report.json").read_text(encoding="utf-8"))
    test = split["partitions"]["P_capture"]["test"]
    target_hours = (test["start_max_ms"] - test["start_min_ms"]) / 3.6e6
    cal = split["partitions"]["P_capture"]["calibration"]
    source_hours = (cal["start_max_ms"] - cal["start_min_ms"]) / 3.6e6

    s = pd.read_csv(ROOT / "results/main_seed_summary.csv")
    s = s.loc[s.protocol.eq("P_capture")]
    rows = []
    for _, r in s.iterrows():
        alpha = r.alpha if np.isfinite(r.alpha) else None
        ref_alpha = alpha if alpha is not None else 0.001
        rows.append({
            "model": r.model, "feature_set": r.feature_set, "threshold_id": r.threshold_id,
            "rule": r.rule, "alpha": alpha,
            "average_precision_mean": r.average_precision_mean,
            "target_fpr_mean": r.fpr_mean, "target_fpr_sd": r.fpr_std,
            "source_fpr_mean": r.source_fpr_mean,
            "source_budget_ratio": r.source_fpr_mean / ref_alpha,
            "target_budget_ratio": r.fpr_mean / ref_alpha,
            "budget_ratio_reference_alpha": ref_alpha,
            "recall_mean": r.recall_mean, "fp_mean": r.fp_mean,
            "benign_alerts_per_hour": r.fp_mean / target_hours,
            "attack_alerts_per_hour": r.recall_mean * N_ATTACK_T / target_hours,
        })
    ops = pd.DataFrame(rows)

    budget = {str(a): {"benign_alerts_allowed_target": a * N_BENIGN_T,
                       "allowed_per_hour_target": a * N_BENIGN_T / target_hours,
                       "benign_alerts_allowed_source": a * N_BENIGN_S,
                       "allowed_per_hour_source": a * N_BENIGN_S / source_hours}
              for a in (0.001, 0.01)}

    # exploratory cohort (seed 42, from results/posthoc_missingness.csv provenance)
    cohort = {"source_flagged": 41, "source_n": 41, "target_flagged": 11560, "target_n": 11560,
              "source_rate_ci95": clopper_pearson(41, 41),
              "target_rate_ci95": clopper_pearson(11560, 11560),
              "source_share_of_benign_udp": 41 / 74339, "target_share_of_benign_udp": 11560 / 259486,
              "source_share_ci95": clopper_pearson(41, 74339),
              "target_share_ci95": clopper_pearson(11560, 259486)}

    # tied-score groups and periodic bursts, XGBoost/F1 at T1 alpha=0.001
    ties, bursts = [], []
    for seed in SEEDS:
        d = next((ROOT / "runs").glob(f"main_P_capture_xgboost_F1_{seed}_*"))
        thr = json.loads((d / "thresholds.json").read_text(encoding="utf-8"))
        t1 = next(e["threshold"] for e in thr["entries"] if e["id"] == "T1_alpha_0.001")
        f = pd.read_parquet(d / "predictions.parquet",
                            columns=["split", "score", "Label", "PROTOCOL", "FLOW_START_MILLISECONDS"])
        tb = f.loc[f.split.eq("test") & f.Label.eq(0)]
        sb = f.loc[f.split.eq("calibration")]
        band = tb.loc[(tb.score > t1) & (tb.score <= 0.5)]
        counts = band.score.value_counts()
        top2 = counts.head(2)
        groups = []
        for value, n in top2.items():
            members = band.loc[band.score.eq(value)]
            win = members.FLOW_START_MILLISECONDS // 1800000
            groups.append({"score": float(value), "n": int(n),
                           "udp_share": float(members.PROTOCOL.eq(17).mean()),
                           "source_benign_at_score": int(sb.score.eq(value).sum()),
                           "windows_present": int(win.nunique())})
        ties.append({"seed": seed, "t1": t1, "band_benign": int(len(band)),
                     "top_two_tied_groups": groups,
                     "top_two_share_of_band": float(top2.sum() / len(band)),
                     "top_two_share_of_t1_fp": float(top2.sum() / int((tb.score > t1).sum()))})
        win = tb.FLOW_START_MILLISECONDS // 1800000
        per = tb.assign(w=win, fp=tb.score > t1).groupby("w").agg(n=("fp", "size"), fp=("fp", "sum"))
        per = per.loc[per.n >= 1000]
        per["fpr"] = per.fp / per.n
        high = per.loc[per.fpr > 0.01]
        bursts.append({"seed": seed, "windows_with_1000plus_benign": int(len(per)),
                       "windows_over_1pct": int(len(high)),
                       "burst_window_starts_utc": [pd.Timestamp(int(w) * 1800000, unit="ms", tz="UTC")
                                                   .strftime("%H:%M") for w in high.index],
                       "windows_over_budget_0p1pct": int((per.fpr > 0.001).sum()),
                       "median_fpr_outside_bursts": float(per.loc[per.fpr <= 0.01, "fpr"].median()),
                       "median_fpr_in_bursts": float(high.fpr.median()) if len(high) else None})

    # link the tied groups and bursts to the NaN-rate UDP cohort (raw byte-rate state)
    raw = pd.read_parquet(ROOT / "data/processed/dataset.parquet",
                          columns=["row_id", "SRC_TO_DST_SECOND_BYTES"])
    v = raw["SRC_TO_DST_SECOND_BYTES"]
    raw["state"] = np.where(v.isna(), "nan", np.where(np.isinf(v), "inf", "finite"))
    raw = raw[["row_id", "state"]]
    burst_starts = set(bursts[0]["burst_window_starts_utc"])
    cohort_link = []
    for seed, tie in zip(SEEDS, ties):
        d = next((ROOT / "runs").glob(f"main_P_capture_xgboost_F1_{seed}_*"))
        f = pd.read_parquet(d / "predictions.parquet",
                            columns=["row_id", "split", "score", "Label", "PROTOCOL",
                                     "FLOW_START_MILLISECONDS"])
        tb = f.loc[f.split.eq("test") & f.Label.eq(0)].merge(raw, on="row_id", how="left",
                                                               validate="one_to_one")
        tied_scores = [g["score"] for g in tie["top_two_tied_groups"]]
        tied = tb.loc[tb.score.isin(tied_scores)]
        nan_udp = tb.loc[tb.state.eq("nan") & tb.PROTOCOL.eq(17)]
        hhmm = pd.to_datetime(nan_udp.FLOW_START_MILLISECONDS // 1800000 * 1800000, unit="ms",
                              utc=True).dt.strftime("%H:%M")
        cohort_link.append({"seed": seed, "tied_flows": int(len(tied)),
                            "tied_state_counts": tied.state.value_counts().to_dict(),
                            "nan_udp_cohort": int(len(nan_udp)),
                            "nan_udp_in_tied_groups": int(nan_udp.score.isin(tied_scores).sum()),
                            "nan_udp_share_in_burst_windows": float(hhmm.isin(burst_starts).mean())})

    m = pd.read_csv(ROOT / "results/posthoc_mitigation_summary.csv")
    mit = m.loc[m.model.eq("xgboost") & m.feature_set.eq("F1")].to_dict(orient="records")

    out = {"target_hours": target_hours, "source_calibration_hours": source_hours,
           "budget_translation": budget, "operating_points": ops.to_dict(orient="records"),
           "exploratory_cohort_seed42": cohort, "tied_groups": ties, "bursts": bursts,
           "cohort_link": cohort_link, "mitigation_xgb_f1": mit}
    (ROOT / "results/revision_numbers.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    pd.set_option("display.width", 220)
    print("target hours %.4f | source calibration hours %.4f" % (target_hours, source_hours))
    print(json.dumps(budget, indent=1))
    show = ops.loc[ops.model.isin(["lr", "xgboost", "rf"])].copy()
    for c in ("target_fpr_mean", "source_fpr_mean"):
        show[c] = show[c] * 100
    show["recall_mean"] = show["recall_mean"] * 100
    print(show[["model", "feature_set", "threshold_id", "average_precision_mean", "source_fpr_mean",
                "target_fpr_mean", "source_budget_ratio", "target_budget_ratio", "fp_mean",
                "benign_alerts_per_hour", "recall_mean"]].round(4).to_string())
    print(json.dumps(cohort, indent=1))
    print(json.dumps(ties, indent=1))
    print(json.dumps(bursts, indent=1))
    print(json.dumps(cohort_link, indent=1))


if __name__ == "__main__":
    main()
