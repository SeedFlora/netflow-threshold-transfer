"""Post-hoc mitigation audit on frozen P_capture predictions; never refits models.

Run: .venv/Scripts/python.exe scripts/posthoc_mitigation.py

Question: when a January-fitted benign-quantile threshold misses its budget in
February, which threshold-update rules bring the realized benign false-positive
rate back toward the budget, and what recall do they give up?

This analysis is exploratory and post hoc: it was specified after the main results
had been read (round-1 review, November 2026), and after the two-hour burst pattern of
February false positives had been seen. Predictions, saved thresholds and fitted
pipelines are read-only; their SHA-256 hashes are recorded before and after the run and
must be identical (this shows the script did not modify them; their agreement with the
September freeze records was checked separately). Saved T0/T1/T2 thresholds are
re-derived with nids_lab.thresholds.fit_thresholds and asserted equal.

Two caveats are computed rather than asserted. (1) Ties: for XGBoost a re-estimated
threshold can land exactly on a score shared by thousands of benign flows; the strict rule
leaves the tie unflagged, and fpr_ties_flagged reports the rate if it were flagged.
(2) Design dependence: rebaseline_k varies the history length and fpr_from_0400 scores
every rule from 04:00, because the ranking of rules depends on where the bursts fall.

Strategies (strict ``score > tau`` everywhere):
  static_T1, static_T2, T0   saved thresholds; T1/T2 are re-derived and asserted
  headroom_10                January benign quantile at alpha/10 (no target data)
  rebaseline_K               one-shot refit on benign flows of the first K February
                             windows (needs triaged labels for those windows only)
  rolling_L                  tau for window i from benign flows of windows i-L..i-1
                             (needs triaged labels for past windows only)
  rolling_L_labelfree        same, but the pool is every flow of windows i-L..i-1
                             with score <= 0.5, i.e. flows the default rule did not
                             alert on; no labels are used
The evaluation span is February windows with index >= K_EVAL, identical rows for
every strategy, so no strategy is ever scored on a window used to set its threshold.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nids_lab.thresholds import fit_thresholds

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (42, 2026, 3407)
CORE = (("lr", "F0"), ("lr", "F1"), ("xgboost", "F0"), ("xgboost", "F1"))
ALPHAS = (0.001, 0.01)
WINDOW_MS = 30 * 60 * 1000
K_EVAL = 6                 # first evaluated February window (03:00 UTC); windows 0..5 = history
LOOKBACKS = (2, 4, 6)      # 1 h, 2 h, 3 h of history
REBASELINE_HISTORIES = (2, 3, 4, 5, 6)   # history ends 01:00, 01:30, 02:00, 02:30, 03:00
PRIMARY_LOOKBACK = 4
N_BOOT, BOOT_SEED = 1000, 20261108
DEFAULT_T0 = 0.5


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pooled_threshold(scores, alpha: float) -> float:
    """Identical to nids_lab.thresholds.pooled_threshold (strict upper tail <= floor(alpha*n))."""
    values = np.asarray(scores, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("Threshold calibration needs a nonempty finite score vector")
    rank = len(values) - int(np.floor(alpha * len(values))) - 1
    return float(np.partition(values, rank)[rank])


def run_dir(model: str, feature: str, seed: int) -> Path:
    found = list((ROOT / "runs").glob(f"main_P_capture_{model}_{feature}_{seed}_*"))
    assert len(found) == 1, (model, feature, seed, found)
    return found[0]


def utc(ms: int) -> str:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M:%S")


def window_table(frame: pd.DataFrame, tau_per_window: np.ndarray, win_index: np.ndarray):
    """Per-window counts for one strategy. tau_per_window is indexed by window index."""
    tau = tau_per_window[win_index]
    pred = frame["score"].to_numpy() > tau
    label = frame["Label"].to_numpy()
    n = int(win_index.max()) + 1
    nb = np.bincount(win_index[label == 0], minlength=n)
    fp = np.bincount(win_index[(label == 0) & pred], minlength=n)
    na = np.bincount(win_index[label == 1], minlength=n)
    tp = np.bincount(win_index[(label == 1) & pred], minlength=n)
    return nb, fp, na, tp


def block_bootstrap(nb, fp, na, tp, rng):
    k = len(nb)
    weights = rng.multinomial(k, np.full(k, 1 / k), size=N_BOOT)
    b_fpr = (weights @ fp) / np.maximum(weights @ nb, 1)
    b_rec = (weights @ tp) / np.maximum(weights @ na, 1)
    q = lambda v: [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))]
    return q(b_fpr), q(b_rec)


def main() -> None:
    split = json.loads((ROOT / "reports/split_report.json").read_text(encoding="utf-8"))
    parts = split["partitions"]["P_capture"]
    periods = {name: {"rows": parts[name]["rows"], "start_utc": utc(parts[name]["start_min_ms"]),
                      "end_utc": utc(parts[name]["start_max_ms"]),
                      "hours": (parts[name]["start_max_ms"] - parts[name]["start_min_ms"]) / 3.6e6}
               for name in ("train", "development", "calibration", "test")}
    periods["cutoff_utc"] = split["cutoff_utc"]
    periods["embargo_seconds"] = split["embargo_seconds"]

    hashes_before, records, windows_out, run_meta = {}, [], [], []
    shared_ids = None
    for model, feature in CORE:
        for seed in SEEDS:
            directory = run_dir(model, feature, seed)
            paths = [directory / "predictions.parquet", directory / "thresholds.json",
                     directory / "pipeline.joblib"]
            for p in paths:
                hashes_before[str(p.relative_to(ROOT))] = digest(p)
            saved = json.loads(paths[1].read_text(encoding="utf-8"))
            assert saved["decision_rule"] == "score > threshold"
            tau_saved = {e["id"]: e["threshold"] for e in saved["entries"]}
            frame = pd.read_parquet(paths[0], columns=["row_id", "split", "score", "Label",
                                                        "FLOW_START_MILLISECONDS", "PROTOCOL"])
            assert np.isfinite(frame["score"]).all()
            source = frame.loc[frame["split"].eq("calibration")]
            # T1 and T2 re-derived with the project's own frozen implementation.
            refit = {e["id"]: e["threshold"] for e in fit_thresholds(source, ALPHAS)["entries"]}
            for key in ("T0", "T1_alpha_0.001", "T2_alpha_0.001", "T1_alpha_0.01", "T2_alpha_0.01"):
                assert refit[key] == tau_saved[key], ("saved threshold does not re-derive", key)
            target = frame.loc[frame["split"].eq("test")].sort_values(
                ["FLOW_START_MILLISECONDS", "row_id"], kind="stable").reset_index(drop=True)
            assert source["Label"].eq(0).all() and len(source) == 337801
            assert len(target) == 1218700 and int(target["Label"].eq(0).sum()) == 1108481
            ids = np.sort(target["row_id"].to_numpy())
            if shared_ids is None:
                shared_ids = ids
            assert np.array_equal(shared_ids, ids), "target rows differ between runs"
            src_scores = source["score"].to_numpy(dtype=np.float64)

            bins = target["FLOW_START_MILLISECONDS"].to_numpy(dtype=np.int64) // WINDOW_MS
            observed = np.unique(bins)
            gaps = int(np.sum(np.diff(observed) != 1))
            win = np.searchsorted(observed, bins)          # observed-window index 0..W-1
            n_win = len(observed)
            label = target["Label"].to_numpy()
            score = target["score"].to_numpy(dtype=np.float64)
            eval_mask_w = np.arange(n_win) >= K_EVAL
            eval_rows = win >= K_EVAL
            span_ms = (target.loc[eval_rows, "FLOW_START_MILLISECONDS"].max()
                       - int(observed[K_EVAL]) * WINDOW_MS)
            eval_hours = span_ms / 3.6e6
            full_hours = (target["FLOW_START_MILLISECONDS"].max()
                          - target["FLOW_START_MILLISECONDS"].min()) / 3.6e6
            run_meta.append({"run": directory.name, "model": model, "feature_set": feature,
                             "seed": seed, "target_windows": n_win, "window_gaps": gaps,
                             "first_window_utc": utc(int(observed[0]) * WINDOW_MS),
                             "eval_start_utc": utc(int(observed[K_EVAL]) * WINDOW_MS),
                             "eval_hours": eval_hours, "full_target_hours": full_hours,
                             "eval_benign": int(((label == 0) & eval_rows).sum()),
                             "eval_attack": int(((label == 1) & eval_rows).sum())})

            for alpha in ALPHAS:
                suffix = format(alpha, ".6g")
                t1 = pooled_threshold(src_scores, alpha)
                assert t1 == tau_saved[f"T1_alpha_{suffix}"], "saved T1 does not re-derive"
                t2 = tau_saved[f"T2_alpha_{suffix}"]
                strategies = {
                    "static_T1": np.full(n_win, t1),
                    "static_T2": np.full(n_win, t2),
                    "T0": np.full(n_win, DEFAULT_T0),
                    "headroom_10": np.full(n_win, pooled_threshold(src_scores, alpha / 10)),
                }
                # Re-baseline sensitivity: history = the first k February windows (k <= K_EVAL),
                # always scored on the same evaluation windows >= K_EVAL.
                for k in REBASELINE_HISTORIES:
                    hist = (win < k) & (label == 0)
                    strategies[f"rebaseline_{k}"] = np.full(n_win, pooled_threshold(score[hist], alpha))
                contamination, tail_contamination = {}, {}
                for lb in LOOKBACKS:
                    roll = np.full(n_win, np.nan)
                    roll_lf = np.full(n_win, np.nan)
                    contaminated, tail = [], []
                    for i in range(K_EVAL, n_win):
                        past = (win >= i - lb) & (win < i)
                        roll[i] = pooled_threshold(score[past & (label == 0)], alpha)
                        pool = past & (score <= DEFAULT_T0)
                        roll_lf[i] = pooled_threshold(score[pool], alpha)
                        contaminated.append(int((pool & (label == 1)).sum()) / int(pool.sum()))
                        upper = pool & (score >= roll_lf[i])
                        tail.append(int((upper & (label == 1)).sum()) / int(upper.sum()))
                    strategies[f"rolling_{lb}"] = roll
                    strategies[f"rolling_{lb}_labelfree"] = roll_lf
                    contamination[lb] = float(np.mean(contaminated))
                    tail_contamination[lb] = float(np.mean(tail))
                for name, tau_w in strategies.items():
                    # Common random numbers: identical operating points get identical intervals.
                    rng = np.random.default_rng(BOOT_SEED)
                    tau_rows = np.where(eval_rows, tau_w[win], np.inf)
                    nb, fp, na, tp = window_table(target, np.nan_to_num(tau_w, nan=np.inf), win)
                    e = slice(K_EVAL, n_win)
                    FP, NB, TP, NA = int(fp[e].sum()), int(nb[e].sum()), int(tp[e].sum()), int(na[e].sum())
                    # Aggregation check only (bincount versus a row-level count); the windowing
                    # and pooling were verified by an independent re-implementation.
                    direct_fp = int(((score > tau_rows) & (label == 0) & eval_rows).sum())
                    assert direct_fp == FP, (name, direct_fp, FP)
                    # Tie counterfactual: flag flows whose score equals tau (tau lowered by 1 ulp).
                    tau_cf = np.nextafter(tau_rows, -np.inf)
                    fp_ties = int(((score > tau_cf) & (label == 0) & eval_rows).sum())
                    at_tau = int(((score == tau_rows) & (label == 0) & eval_rows).sum())
                    # Same rule scored only from 04:00 (window index >= K_EVAL + 2).
                    late = slice(K_EVAL + 2, n_win)
                    fpr_late = int(fp[late].sum()) / int(nb[late].sum())
                    win_fpr = fp[e] / np.maximum(nb[e], 1)
                    fpr_ci, rec_ci = block_bootstrap(nb[e], fp[e], na[e], tp[e], rng)
                    taus = tau_w[e]
                    lb_used = int(name.split("_")[1]) if name.startswith("rolling") else None
                    records.append({
                        "model": model, "feature_set": feature, "seed": seed, "alpha": alpha,
                        "strategy": name, "lookback_windows": lb_used,
                        "uses_target_labels": name.startswith("rebaseline") or (
                            name.startswith("rolling") and not name.endswith("labelfree")),
                        "uses_target_data": not name.startswith(("static", "T0", "headroom")),
                        "eval_benign": NB, "eval_attack": NA, "fp": FP, "tp": TP,
                        "fpr": FP / NB, "recall": TP / NA, "budget_ratio": (FP / NB) / alpha,
                        "fp_per_hour": FP / eval_hours,
                        "budget_fp_per_hour": alpha * NB / eval_hours,
                        "windows_over_budget": int(np.sum(win_fpr > alpha)),
                        "windows_evaluated": int(n_win - K_EVAL),
                        "fpr_ci95": fpr_ci, "recall_ci95": rec_ci,
                        "tau_min": float(np.min(taus)), "tau_median": float(np.median(taus)),
                        "tau_max": float(np.max(taus)),
                        "benign_at_tau": at_tau, "fp_ties_flagged": fp_ties,
                        "fpr_ties_flagged": fp_ties / NB,
                        "fpr_from_0400": fpr_late, "budget_ratio_from_0400": fpr_late / alpha,
                        "pool_attack_fraction_mean": (contamination[lb_used]
                                                      if name.endswith("labelfree") else None),
                        "pool_tail_attack_fraction_mean": (tail_contamination[lb_used]
                                                           if name.endswith("labelfree") else None),
                    })
                    if model == "xgboost" and feature == "F1":
                        for i in range(n_win):
                            windows_out.append({
                                "seed": seed, "alpha": alpha, "strategy": name, "window": i,
                                "window_start_utc": utc(int(observed[i]) * WINDOW_MS),
                                "evaluated": bool(i >= K_EVAL), "tau": float(tau_w[i]) if np.isfinite(tau_w[i]) else None,
                                "benign": int(nb[i]), "fp": int(fp[i]), "attack": int(na[i]), "tp": int(tp[i]),
                                "fpr": float(fp[i] / nb[i]) if nb[i] else None})

    hashes_after = {k: digest(ROOT / k) for k in hashes_before}
    assert hashes_after == hashes_before, "an input artifact changed during the audit"

    rec = pd.DataFrame(records)
    keys = ["model", "feature_set", "alpha", "strategy"]
    agg = rec.groupby(keys, sort=False).agg(
        fpr_mean=("fpr", "mean"), fpr_sd=("fpr", "std"), recall_mean=("recall", "mean"),
        recall_sd=("recall", "std"), budget_ratio_mean=("budget_ratio", "mean"),
        fp_mean=("fp", "mean"), tp_mean=("tp", "mean"), fp_per_hour_mean=("fp_per_hour", "mean"),
        budget_fp_per_hour=("budget_fp_per_hour", "mean"),
        windows_over_budget_mean=("windows_over_budget", "mean"),
        windows_evaluated=("windows_evaluated", "first"),
        fpr_ties_flagged_mean=("fpr_ties_flagged", "mean"),
        benign_at_tau_mean=("benign_at_tau", "mean"),
        budget_ratio_from_0400_mean=("budget_ratio_from_0400", "mean"),
        pool_tail_attack_fraction_mean=("pool_tail_attack_fraction_mean", "mean"),
        seeds_over_budget=("budget_ratio", lambda v: int(np.sum(np.asarray(v) > 1))),
        n=("seed", "count")).reset_index()
    # operating points over budget across the 4 core models x 3 seeds, per alpha and strategy
    violations = (rec.assign(over=rec["budget_ratio"] > 1)
                  .groupby(["alpha", "strategy"], sort=False)["over"].agg(["sum", "count"]).reset_index()
                  .rename(columns={"sum": "operating_points_over_budget", "count": "operating_points"}))

    out_dir = ROOT / "results"
    rec.drop(columns=["fpr_ci95", "recall_ci95"]).assign(
        fpr_ci95_low=[c[0] for c in rec["fpr_ci95"]], fpr_ci95_high=[c[1] for c in rec["fpr_ci95"]],
        recall_ci95_low=[c[0] for c in rec["recall_ci95"]], recall_ci95_high=[c[1] for c in rec["recall_ci95"]],
    ).to_csv(out_dir / "posthoc_mitigation_runs.csv", index=False)
    agg.to_csv(out_dir / "posthoc_mitigation_summary.csv", index=False)
    pd.DataFrame(windows_out).to_csv(out_dir / "posthoc_mitigation_windows_xgb_f1.csv", index=False)
    payload = {
        "description": __doc__.strip().splitlines()[0],
        "design": {"k_eval": K_EVAL, "lookbacks": LOOKBACKS, "primary_lookback": PRIMARY_LOOKBACK,
                   "window_minutes": 30, "bootstrap": {"resamples": N_BOOT, "seed": BOOT_SEED,
                   "unit": "evaluation window (30 min), resampled with replacement"},
                   "decision_rule": "score > threshold", "default_threshold": DEFAULT_T0},
        "periods": periods, "runs": run_meta, "violations": violations.to_dict(orient="records"),
        "summary": agg.to_dict(orient="records"),
        "input_hashes": hashes_before, "hashes_unchanged": True,
    }
    (out_dir / "posthoc_mitigation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 300)
    show = agg.copy()
    show["fpr%"] = (show.fpr_mean * 100).round(4)
    show["recall%"] = (show.recall_mean * 100).round(4)
    print(json.dumps(periods, indent=1))
    print(pd.DataFrame(run_meta)[["run", "target_windows", "window_gaps", "eval_start_utc", "eval_hours",
                                  "full_target_hours", "eval_benign", "eval_attack"]].to_string())
    show["ties_flagged%"] = (show.fpr_ties_flagged_mean * 100).round(4)
    print(show[["model", "feature_set", "alpha", "strategy", "fpr%", "recall%", "budget_ratio_mean",
                "fp_per_hour_mean", "windows_over_budget_mean", "seeds_over_budget", "ties_flagged%",
                "benign_at_tau_mean", "budget_ratio_from_0400_mean",
                "pool_tail_attack_fraction_mean"]].to_string())
    print(violations.to_string())


if __name__ == "__main__":
    main()
