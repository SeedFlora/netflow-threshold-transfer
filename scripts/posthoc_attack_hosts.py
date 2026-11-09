"""Post-hoc audit of benign-labeled flows that involve the testbed's attack hosts.

Run: .venv/Scripts/python.exe -I scripts/posthoc_attack_hosts.py
Writes results/posthoc_attack_hosts.json. Reads the processed dataset and the frozen
predictions/thresholds only; nothing is refitted. Raised by the round-2 internal review:
the February excess of false positives is dominated by benign-labeled flows exchanged with
the subnet that sources every attack flow, a subnet absent from the January calibration
window. This script recomputes those facts from primary artifacts so the manuscript can cite
them with provenance. Exploratory and post hoc.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (42, 2026, 3407)
MODELS = (("lr", "F0"), ("lr", "F1"), ("xgboost", "F0"), ("xgboost", "F1"), ("rf", "F1"))
ATTACK_SUBNET = "175.45.176."
ALPHA = 0.001


def utc(ms) -> str:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M:%S")


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_dir(model, feature, seed) -> Path:
    found = list((ROOT / "runs").glob(f"main_P_capture_{model}_{feature}_{seed}_*"))
    assert len(found) == 1
    return found[0]


def main() -> None:
    cols = ["row_id", "IPV4_SRC_ADDR", "IPV4_DST_ADDR", "L4_DST_PORT", "L7_PROTO", "MIN_TTL",
            "PROTOCOL", "SRC_TO_DST_SECOND_BYTES", "Label", "capture", "FLOW_START_MILLISECONDS",
            "integrity_reason"]
    raw = pd.read_parquet(ROOT / "data/processed/dataset.parquet", columns=cols)
    raw["src_sub"] = raw.IPV4_SRC_ADDR.astype(str).str.startswith(ATTACK_SUBNET)
    raw["dst_sub"] = raw.IPV4_DST_ADDR.astype(str).str.startswith(ATTACK_SUBNET)
    raw["subnet"] = raw.src_sub | raw.dst_sub
    raw["nan_rate"] = raw.SRC_TO_DST_SECOND_BYTES.isna()
    out = {"attack_subnet": ATTACK_SUBNET + "0/24"}

    # 1. attack flows and the subnet, per capture (all rows of the file)
    per_capture = {}
    for cap, g in raw.groupby("capture"):
        att = g.loc[g.Label.eq(1)]
        ben = g.loc[g.Label.eq(0)]
        per_capture[cap] = {
            "attack_flows": int(len(att)),
            "attack_flows_with_subnet": int(att.subnet.sum()),
            "attack_flows_subnet_as_source": int(att.src_sub.sum()),
            "attack_first_start_utc": utc(att.FLOW_START_MILLISECONDS.min()) if len(att) else None,
            "attack_last_start_utc": utc(att.FLOW_START_MILLISECONDS.max()) if len(att) else None,
            "benign_flows_with_subnet": int(ben.subnet.sum()),
            "benign_subnet_first_start_utc": utc(ben.loc[ben.subnet].FLOW_START_MILLISECONDS.min())
            if ben.subnet.any() else None,
            "benign_subnet_last_start_utc": utc(ben.loc[ben.subnet].FLOW_START_MILLISECONDS.max())
            if ben.subnet.any() else None,
        }
    out["per_capture_all_rows"] = per_capture

    # 2. populations used by the frozen protocol (same row sets in every run)
    pred = pd.read_parquet(run_dir("xgboost", "F1", 42) / "predictions.parquet",
                           columns=["row_id", "split", "Label"])
    frame = pred.merge(raw.drop(columns=["Label"]), on="row_id", how="left", validate="one_to_one")
    cal = frame.loc[frame.split.eq("calibration")]
    tgt_b = frame.loc[frame.split.eq("test") & frame.Label.eq(0)]
    tgt_a = frame.loc[frame.split.eq("test") & frame.Label.eq(1)]
    sub_b = tgt_b.loc[tgt_b.subnet]
    other_b = tgt_b.loc[~tgt_b.subnet]
    out["calibration_benign"] = int(len(cal))
    out["calibration_benign_with_subnet"] = int(cal.subnet.sum())
    out["target_benign"] = int(len(tgt_b))
    out["target_benign_with_subnet"] = int(len(sub_b))
    out["target_benign_with_subnet_share"] = float(len(sub_b) / len(tgt_b))
    out["target_benign_subnet_as_destination"] = int(sub_b.dst_sub.sum())
    out["target_benign_subnet_port53_share"] = float(sub_b.L4_DST_PORT.eq(53).mean())
    out["target_benign_subnet_dns_l7_share"] = float(np.floor(sub_b.L7_PROTO).eq(5).mean())
    out["target_benign_subnet_min_ttl0_share"] = float(sub_b.MIN_TTL.eq(0).mean())
    out["target_benign_other_min_ttl_mode"] = float(other_b.MIN_TTL.mode().iloc[0])
    out["target_attack_with_subnet_share"] = float(tgt_a.subnet.mean())

    # 3. the NaN-rate UDP cohort in both windows
    def cohort(df):
        c = df.loc[df.nan_rate & df.PROTOCOL.eq(17)]
        pairs = c.assign(a=c.IPV4_SRC_ADDR.astype(str), b=c.IPV4_DST_ADDR.astype(str)).groupby(["a", "b"]).size()
        return {"flows": int(len(c)), "with_subnet": int(c.subnet.sum()),
                "port53_share": float(c.L4_DST_PORT.eq(53).mean()) if len(c) else None,
                "endpoint_pairs": int(len(pairs))}
    out["nan_udp_cohort_calibration"] = cohort(cal)
    out["nan_udp_cohort_target"] = cohort(tgt_b)

    # 4. per model: false-positive share from subnet flows, and rho_t without them
    per_model, host_decomp = [], []
    hashes = {}
    for model, feature in MODELS:
        for seed in SEEDS:
            d = run_dir(model, feature, seed)
            for name in ("predictions.parquet", "thresholds.json"):
                hashes[str((d / name).relative_to(ROOT))] = digest(d / name)
            thr = json.loads((d / "thresholds.json").read_text(encoding="utf-8"))
            tau = next(e["threshold"] for e in thr["entries"] if e["id"] == "T1_alpha_0.001")
            p = pd.read_parquet(d / "predictions.parquet", columns=["row_id", "split", "Label", "score"])
            p = p.merge(raw[["row_id", "subnet"]], on="row_id", how="left", validate="one_to_one")
            s_b = p.loc[p.split.eq("calibration")]
            t_b = p.loc[p.split.eq("test") & p.Label.eq(0)]
            fp = t_b.score > tau
            fp_sub = int((fp & t_b.subnet).sum())
            n_other = int((~t_b.subnet).sum())
            fp_other = int((fp & ~t_b.subnet).sum())
            per_model.append({"model": model, "feature_set": feature, "seed": seed,
                              "fp": int(fp.sum()), "fp_subnet": fp_sub,
                              "fp_subnet_share": fp_sub / int(fp.sum()),
                              "subnet_flows_flagged": fp_sub, "subnet_flows": int(t_b.subnet.sum()),
                              "rho_t": float(fp.mean() / ALPHA),
                              "rho_t_without_subnet": float(fp_other / n_other / ALPHA)})
            if (model, feature) == ("xgboost", "F1"):
                # Eq. (2) with a host-role partition: {subnet, other}; no source support for subnet.
                ns = np.array([int(s_b.subnet.sum()), int((~s_b.subnet).sum())], dtype=float)
                fs_ = np.array([int(((s_b.score > tau) & s_b.subnet).sum()),
                                int(((s_b.score > tau) & ~s_b.subnet).sum())], dtype=float)
                nt = np.array([int(t_b.subnet.sum()), n_other], dtype=float)
                ft = np.array([fp_sub, fp_other], dtype=float)
                ws, wt = ns / ns.sum(), nt / nt.sum()
                rs = np.divide(fs_, ns, out=np.zeros(2), where=ns > 0)
                rt = ft / nt
                sup = ns > 0
                comp = float(np.sum(((wt - ws) * rs)[sup]))
                within = float(np.sum((wt * (rt - rs))[sup]))
                unsup = float(np.sum((wt * rt)[~sup]))
                delta = float(ft.sum() / nt.sum() - fs_.sum() / ns.sum())
                assert abs(delta - (comp + within + unsup)) < 1e-12
                host_decomp.append({"seed": seed, "delta_fpr": delta, "composition": comp,
                                    "within": within, "unsupported_target": unsup,
                                    "unsupported_share": unsup / delta})
    pm = pd.DataFrame(per_model)
    out["per_model_seed"] = per_model
    out["per_model_mean"] = (pm.groupby(["model", "feature_set"])
                             .agg(fp_subnet_share_min=("fp_subnet_share", "min"),
                                  fp_subnet_share_max=("fp_subnet_share", "max"),
                                  subnet_flagged_min=("subnet_flows_flagged", "min"),
                                  subnet_flagged_max=("subnet_flows_flagged", "max"),
                                  rho_t_mean=("rho_t", "mean"),
                                  rho_t_without_subnet_mean=("rho_t_without_subnet", "mean"))
                             .reset_index().to_dict(orient="records"))
    hd = pd.DataFrame(host_decomp)
    out["host_role_decomposition_xgb_f1"] = host_decomp
    out["host_role_decomposition_xgb_f1_mean"] = {
        k: float(hd[k].mean()) for k in ("delta_fpr", "composition", "within", "unsupported_target")}
    out["host_role_decomposition_xgb_f1_mean"]["unsupported_share_ratio_of_means"] = float(
        hd.unsupported_target.mean() / hd.delta_fpr.mean())

    # 5. Kitagawa's symmetric form for the protocol partition (average of the two references)
    po = json.loads((ROOT / "results/posthoc_operating_points.json").read_text(encoding="utf-8"))
    ref = po["reference_summary"]["T1_alpha_0.001"]
    w_t, w_s = ref["within_target_weights"]["mean"], ref["within_source_weights"]["mean"]
    dlt = ref["delta_fpr"]["mean"]
    out["protocol_within_share"] = {"target_weights": w_t / dlt, "source_weights": w_s / dlt,
                                    "symmetric": (w_t + w_s) / 2 / dlt}

    # 6. timing: February cohort/subnet flows versus attack flows per 30-minute window
    tb = frame.loc[frame.split.eq("test")]
    win = tb.FLOW_START_MILLISECONDS // 1_800_000
    per_win = pd.DataFrame({"win": win, "sub_benign": tb.subnet & tb.Label.eq(0),
                            "attack": tb.Label.eq(1)}).groupby("win").sum()
    out["window_corr_subnet_benign_vs_attack"] = float(np.corrcoef(per_win.sub_benign, per_win.attack)[0, 1])

    # 7. queue composition at T1 for XGBoost/F1 (three-seed mean), per hour of the capture
    rn = json.loads((ROOT / "results/revision_numbers.json").read_text(encoding="utf-8"))
    hours = rn["target_hours"]
    op = next(o for o in rn["operating_points"]
              if o["model"] == "xgboost" and o["feature_set"] == "F1" and o["threshold_id"] == "T1_alpha_0.001")
    tp = op["recall_mean"] * len(tgt_a)
    out["queue_xgb_f1_t1"] = {"benign_per_hour": op["fp_mean"] / hours, "attack_per_hour": tp / hours,
                              "total_per_hour": (op["fp_mean"] + tp) / hours,
                              "benign_share": op["fp_mean"] / (op["fp_mean"] + tp)}
    out["input_hashes"] = hashes
    (ROOT / "results/posthoc_attack_hosts.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_model_seed", "input_hashes")}, indent=1))


if __name__ == "__main__":
    main()
