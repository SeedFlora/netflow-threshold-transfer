"""Descriptive audit of existing XGB/F1 capture predictions; never refits models.

Run: .venv/Scripts/python.exe scripts/posthoc_operating_points.py
Only the three named post-hoc output files are written. Existing predictions,
thresholds and decomposition tables are independently reconciled and hashed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (42, 2026, 3407)
RULES = ("T0", "T1_alpha_0.001", "T2_alpha_0.001")
STRATA = ("TCP", "UDP", "ICMP", "Other")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ratio(a: float, b: float) -> float | None:
    return float(a / b) if b else None


def moments(rows: list[dict], keys: list[str]) -> dict:
    return {key: {"mean": float(np.mean([r[key] for r in rows])),
                  "sample_sd": float(np.std([r[key] for r in rows], ddof=1))}
            for key in keys}


def run() -> None:
    inputs, bands, references, threshold_pairs = [], [], [], []
    main_path = ROOT / "results/main_metrics.csv"
    main_hash = digest(main_path)
    main = pd.read_csv(main_path)
    shared_target_ids = None
    for seed in SEEDS:
        candidates = list((ROOT / "runs").glob(f"main_P_capture_xgboost_F1_{seed}_*"))
        assert len(candidates) == 1, (seed, candidates)
        directory = candidates[0]
        paths = [directory / n for n in ("predictions.parquet", "thresholds.json", "decomposition.csv")]
        before = {str(p.relative_to(ROOT)): digest(p) for p in paths}
        threshold_file = json.loads(paths[1].read_text(encoding="utf-8"))
        assert threshold_file["decision_rule"] == "score > threshold"
        tau = {e["id"]: float(e["threshold"]) for e in threshold_file["entries"]}
        assert tau["T1_alpha_0.001"] <= tau["T2_alpha_0.001"] <= tau["T0"] == 0.5
        frame = pd.read_parquet(paths[0], columns=["row_id", "split", "score", "Label", "PROTOCOL", "Attack"])
        assert np.isfinite(frame.score).all()
        frame["stratum"] = np.select([frame.PROTOCOL.eq(6), frame.PROTOCOL.eq(17), frame.PROTOCOL.eq(1)],
                                     ["TCP", "UDP", "ICMP"], default="Other")
        target = frame.loc[frame.split.eq("test")].copy()
        source = frame.loc[frame.split.eq("calibration") & frame.Label.eq(0)]
        ids = target.row_id.to_numpy()
        if shared_target_ids is None:
            shared_target_ids = ids
        else:
            assert np.array_equal(shared_target_ids, ids)
        benign = target.Label.eq(0)
        attack = target.Label.eq(1)
        assert (len(source), int(benign.sum()), int(attack.sum())) == (337801, 1108481, 110219)
        dec = pd.read_csv(paths[2])
        counts = {}
        for rule in RULES:
            pred = target.score.gt(tau[rule])
            fp, tp = int((pred & benign).sum()), int((pred & attack).sum())
            check = main.loc[main.run_id.eq(directory.name) & main.threshold_id.eq(rule)]
            assert len(check) == 1 and fp == int(check.iloc[0].fp) and tp == int(check.iloc[0].tp)
            counts[rule] = {"fp": fp, "tp": tp}
            d = dec.loc[dec.threshold_id.eq(rule)].set_index("stratum").loc[list(STRATA)]
            for stratum in STRATA:
                t = target.loc[benign & target.stratum.eq(stratum)]
                s = source.loc[source.stratum.eq(stratum)]
                assert len(t) == int(d.loc[stratum, "target_n_benign"])
                assert len(s) == int(d.loc[stratum, "source_n_benign"])
                assert int(t.score.gt(tau[rule]).sum()) == int(d.loc[stratum, "target_fp"])
                assert int(s.score.gt(tau[rule]).sum()) == int(d.loc[stratum, "source_fp"])
            supported = d.source_n_benign.gt(0)
            ds = d.loc[supported]
            ws, wt = ds.source_weight.to_numpy(), ds.target_weight.to_numpy()
            rs, rt = ds.source_fpr.to_numpy(), ds.target_fpr.to_numpy()
            source_fpr = float(d.source_fp.sum() / d.source_n_benign.sum())
            target_fpr = fp / int(benign.sum())
            comp_source_ref = float(np.sum((wt - ws) * rs))
            within_target_weights = float(np.sum(wt * (rt - rs)))
            comp_target_ref = float(np.sum((wt - ws) * rt))
            within_source_weights = float(np.sum(ws * (rt - rs)))
            unsupported = float(d.loc[~supported, "target_fp"].sum() / d.target_n_benign.sum())
            delta = target_fpr - source_fpr
            assert np.isclose(delta, comp_source_ref + within_target_weights + unsupported, atol=1e-12)
            assert np.isclose(delta, comp_target_ref + within_source_weights + unsupported, atol=1e-12)
            tcp_udp = d.loc[["TCP", "UDP"]]
            sw = tcp_udp.source_n_benign / tcp_udp.source_n_benign.sum()
            shared_source = float(tcp_udp.source_fp.sum() / tcp_udp.source_n_benign.sum())
            shared_target = float(tcp_udp.target_fp.sum() / tcp_udp.target_n_benign.sum())
            shared_standardized = float((sw * tcp_udp.target_fpr).sum())
            references.append({
                "record_type": "reference_sensitivity", "row_kind": "seed", "seed": seed, "rule": rule,
                "source_fpr": source_fpr, "target_fpr": target_fpr, "delta_fpr": delta,
                "composition_source_rates": comp_source_ref,
                "within_target_weights": within_target_weights,
                "composition_target_rates": comp_target_ref,
                "within_source_weights": within_source_weights,
                "unsupported_target": unsupported,
                "within_target_weights_share_delta": ratio(within_target_weights, delta),
                "within_source_weights_share_delta": ratio(within_source_weights, delta),
                "source_standardized_target_fpr_all_source_supported": float(np.sum(ws * rt)),
                "tcp_udp_source_n_benign": int(tcp_udp.source_n_benign.sum()),
                "tcp_udp_target_n_benign": int(tcp_udp.target_n_benign.sum()),
                "tcp_udp_source_fp": int(tcp_udp.source_fp.sum()),
                "tcp_udp_target_fp": int(tcp_udp.target_fp.sum()),
                "tcp_udp_source_fpr": shared_source, "tcp_udp_target_fpr": shared_target,
                "tcp_udp_source_standardized_target_fpr": shared_standardized,
            })
        for rule in RULES[1:]:
            band = target.score.gt(tau[rule]) & target.score.le(tau["T0"])
            fp_mask, tp_mask = band & benign, band & attack
            extra_fp, recovered = int(fp_mask.sum()), int(tp_mask.sum())
            assert extra_fp == counts[rule]["fp"] - counts["T0"]["fp"]
            assert recovered == counts[rule]["tp"] - counts["T0"]["tp"]
            protocol_fp = {p: int((fp_mask & target.stratum.eq(p)).sum()) for p in STRATA}
            family_tp = {str(k): int(v) for k, v in target.loc[tp_mask, "Attack"].value_counts().sort_index().items()}
            assert sum(protocol_fp.values()) == extra_fp and sum(family_tp.values()) == recovered
            bands.append({
                "record_type": "score_band", "row_kind": "seed", "seed": seed, "rule": rule,
                "lower_threshold": tau[rule], "upper_threshold": tau["T0"],
                "additional_fp": extra_fp, "recovered_attacks": recovered,
                "additional_fp_per_recovered_attack": ratio(extra_fp, recovered),
                "udp_share_additional_fp": ratio(protocol_fp["UDP"], extra_fp),
                **{f"additional_fp_{p.lower()}": n for p, n in protocol_fp.items()},
                "recovered_attack_families": family_tp,
                "t0_fp": counts["T0"]["fp"], "t0_tp": counts["T0"]["tp"],
                "selected_fp": counts[rule]["fp"], "selected_tp": counts[rule]["tp"],
            })
        threshold_pairs.append({"seed": seed, "t2_equals_t1": tau[RULES[2]] == tau[RULES[1]],
                                "t2_fewer_fp_than_t1": counts[RULES[1]]["fp"] - counts[RULES[2]]["fp"],
                                "t2_fewer_tp_than_t1": counts[RULES[1]]["tp"] - counts[RULES[2]]["tp"]})
        after = {str(p.relative_to(ROOT)): digest(p) for p in paths}
        assert before == after
        inputs.append({"seed": seed, "run_id": directory.name, "unchanged_sha256": before})

    band_summary = {}
    for rule in RULES[1:]:
        selected = [r for r in bands if r["rule"] == rule]
        sum_keys = ["additional_fp", "recovered_attacks", "additional_fp_tcp", "additional_fp_udp", "additional_fp_icmp", "additional_fp_other"]
        totals = {k: sum(r[k] for r in selected) for k in sum_keys}
        pooled = {**totals, "additional_fp_per_recovered_attack": ratio(totals["additional_fp"], totals["recovered_attacks"]),
                  "udp_share_additional_fp": ratio(totals["additional_fp_udp"], totals["additional_fp"])}
        band_summary[rule] = {"mean_and_sample_sd": moments(selected, sum_keys), "pooled_model_flow_decisions": pooled}
    reference_summary = {}
    ref_fields = [k for k, v in references[0].items() if isinstance(v, (int, float)) and k != "seed"]
    for rule in RULES:
        selected = [r for r in references if r["rule"] == rule]
        summary = moments(selected, ref_fields)
        summary["ratio_of_mean_within_target_to_mean_delta"] = summary["within_target_weights"]["mean"] / summary["delta_fpr"]["mean"]
        summary["ratio_of_mean_within_source_to_mean_delta"] = summary["within_source_weights"]["mean"] / summary["delta_fpr"]["mean"]
        reference_summary[rule] = summary
    result = {
        "analysis": "Post-hoc descriptive frozen-score audit; no retraining, threshold fitting or tuning.",
        "protocol": "P_capture", "model": "xgboost", "feature_set": "F1", "seeds": list(SEEDS),
        "alpha": 0.001, "band_definition": "tau_selected < score <= 0.5 on target flows",
        "rate_units": "probabilities, not percentages; multiply by 100 for percentage or percentage-point reporting",
        "pooling_note": "Pooled counts repeat the same target flows across three fitted models; these are model-flow decisions, not independent or unique flows. Pooled ratios are ratios of count sums, not means of seed ratios.",
        "support_note": "TCP+UDP is a deliberately restricted post-hoc two-stratum subset. Other also has source support; ICMP alone is absent from benign source calibration. Standardized FPR changes the weighting estimand and is not a deployed alarm rate.",
        "reference_note": "Both allocation conventions are exact. Source-rate composition/target-weight within allocation assigns the interaction to within; target-rate composition/source-weight within assigns it to composition. Neither is causal.",
        "crosscheck_metrics_sha256": main_hash,
        "analysis_script_sha256": digest(Path(__file__)),
        "inputs": inputs, "bands": bands, "band_summary": band_summary,
        "reference_sensitivity": references, "reference_summary": reference_summary,
        "t1_t2_comparisons": threshold_pairs,
    }
    assert digest(main_path) == main_hash
    (ROOT / "results/posthoc_operating_points.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    csv_rows = [{**r, "recovered_attack_families": json.dumps(r["recovered_attack_families"], sort_keys=True)} for r in bands] + references
    for rule, summary in band_summary.items():
        csv_rows.append({"record_type": "score_band", "row_kind": "pooled_model_flow_decisions", "seed": "all", "rule": rule, **summary["pooled_model_flow_decisions"]})
        csv_rows.append({"record_type": "score_band", "row_kind": "seed_mean", "seed": "all", "rule": rule, **{k: v["mean"] for k, v in summary["mean_and_sample_sd"].items()}})
    pd.DataFrame(csv_rows).to_csv(ROOT / "results/posthoc_operating_points.csv", index=False)
    lines = ["# Post-hoc operating-point audit", "", "Reproduce with `.venv/Scripts/python.exe scripts/posthoc_operating_points.py`. This reads frozen XGBoost/F1 capture predictions for seeds 42, 2026, and 3407. No models or thresholds change. Input hashes and independent reconciliations with the existing metrics/decomposition tables are recorded in the JSON.", "", "The band is `tau_rule < score <= 0.5`. Counts below are additional false positives and recovered attack detections when lowering T0 to the named rule; both calibrated rules use alpha = 0.001.", "", "| Seed | Rule | Additional FP | Recovered attacks | FP / recovered attack | UDP share of additional FP |", "|---|---|---:|---:|---:|---:|"]
    for r in bands:
        lines.append(f"| {r['seed']} | {r['rule'][:2]} | {r['additional_fp']:,} | {r['recovered_attacks']} | {r['additional_fp_per_recovered_attack']:.2f} | {100*r['udp_share_additional_fp']:.2f}% |")
    for rule, s in band_summary.items():
        p = s["pooled_model_flow_decisions"]
        lines.append(f"| Pooled decisions | {rule[:2]} | {p['additional_fp']:,} | {p['recovered_attacks']} | {p['additional_fp_per_recovered_attack']:.2f} | {100*p['udp_share_additional_fp']:.2f}% |")
    lines += ["", "## Reference sensitivity", "", "All rates below are means over three seeds, in percent; components are percentage points. TCP+UDP denominators are 337,629 source and 1,107,590 target benign flows. Other is source-supported but deliberately excluded from this restricted subset.", "", "| Rule | Full target FPR | TCP+UDP source FPR | TCP+UDP target FPR | TCP+UDP target at source weights | Within, target weights (pp) | Within, source weights (pp) |", "|---|---:|---:|---:|---:|---:|---:|"]
    for rule, r in reference_summary.items():
        fields = ("target_fpr", "tcp_udp_source_fpr", "tcp_udp_target_fpr", "tcp_udp_source_standardized_target_fpr", "within_target_weights", "within_source_weights")
        lines.append("| " + rule[:2] + " | " + " | ".join(f"{100*r[k]['mean']:.4f}" for k in fields) + " |")
    lines += ["", "The full-population alternative reference retains the unsupported ICMP term and source-supported Other stratum. Original: composition uses source rates, within uses target weights. Alternative: composition uses target rates, within uses source weights. Both sum exactly to the same observed change. Full per-seed moments, protocol counts, recovered attack families, and source-standardized rates are in `results/posthoc_operating_points.json`; all probabilities are stored without multiplication by 100.", "", "The count and decomposition assertions passed; hashes of all nine input artifacts remained unchanged.", ""]
    (ROOT / "reports/POSTHOC_OPERATING_POINTS.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"band_summary": band_summary, "t1_t2_comparisons": threshold_pairs}, indent=2))


if __name__ == "__main__":
    run()
