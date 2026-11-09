"""Aggregate measured runs, paired comparisons, seed variation and Pareto costs."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .evaluate import compare_feature_runs


def pareto_mask(frame: pd.DataFrame, recall="recall", fpr="fpr", cost="inference_cost_seconds_per_flow"):
    """A valid point is dominated only by another no-worse, strictly-better point."""
    values = frame[[recall, fpr, cost]].to_numpy(dtype=float)
    values[:, 0] *= -1
    valid = np.isfinite(values).all(axis=1)
    mask = np.zeros(len(frame), dtype=bool)
    for i in np.flatnonzero(valid):
        dominates = valid & np.all(values <= values[i], axis=1) & np.any(values < values[i], axis=1)
        mask[i] = not np.any(dominates)
    return mask


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fmt(value, digits=6):
    return "N/A" if value is None or (isinstance(value, float) and not np.isfinite(value)) else (f"{value:.{digits}g}" if isinstance(value, (float, np.floating)) else str(value))


def _markdown_table(frame, columns, limit=100):
    if frame.empty:
        return "No measured results available."
    table = frame[columns].head(limit)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines.extend("| " + " | ".join(_fmt(value).replace("|", "\\|") for value in row) + " |" for row in table.itertuples(index=False, name=None))
    if len(frame) > limit:
        lines.append(f"\nTable truncated to {limit} rows; full CSV has {len(frame)} rows.")
    return "\n".join(lines)


def report_experiments(config, workspace) -> dict:
    workspace = Path(workspace)
    report_dir, results_dir, figures_dir = (workspace / x for x in ("reports", "results", "figures"))
    for path in (report_dir, results_dir, figures_dir):
        path.mkdir(parents=True, exist_ok=True)
    profile = config.get("profile", "main")
    records, loaded, statuses = [], {}, []
    for run_dir in sorted((workspace / "runs").glob("*")):
        if not run_dir.is_dir() or not (run_dir / "metadata.json").exists():
            continue
        metadata = _read_json(run_dir / "metadata.json")
        if metadata.get("profile") != profile:
            continue
        state = _read_json(run_dir / "status.json") if (run_dir / "status.json").exists() else {"status": "unknown"}
        statuses.append({"run_id": run_dir.name, "status": state.get("status"), "reason": state.get("reason")})
        if not (run_dir / "metrics.json").exists():
            continue
        result = _read_json(run_dir / "metrics.json")
        loaded[run_dir] = result
        for point in result["operating_points"]:
            base = {"run_id": run_dir.name, **{k: metadata.get(k) for k in ("profile", "model", "feature_set", "protocol", "seed")},
                    **{k: point.get(k) for k in ("threshold_id", "rule", "alpha", "threshold", "eligible", "reason")}}
            measured = result.get("profiling", {})
            base.update({k: measured.get(k) for k in ("training_wall_seconds", "preprocessing_fit_seconds", "peak_process_tree_rss_bytes",
                        "peak_gpu_device_used_mb", "artifact_bytes", "inference_throughput_flows_per_second", "inference_batch_size",
                        "inference_device", "actual_training_device", "inference_model_only_seconds_per_flow",
                        "inference_end_to_end_seconds_per_flow")})
            base["inference_cost_seconds_per_flow"] = measured.get("inference_end_to_end_seconds_per_flow")
            if point["eligible"]:
                base.update({k: point["test"].get(k) for k in ("n", "n_benign", "n_attack", "tn", "fp", "fn", "tp", "precision", "recall",
                                  "f1", "binary_macro_f1", "fpr", "false_alarms_per_10000_benign", "fpr_over_alpha", "fpr_excess", "attack_prevalence")})
                base.update({k: result["ranking"]["test"].get(k) for k in ("average_precision", "roc_auc")})
                base.update({k: point["decomposition"].get(k) for k in ("delta_fpr", "composition", "within_stratum", "unsupported_target")})
                base["source_fpr"] = point["calibration"]["fpr"]
                base["source_recall"] = point["calibration"]["recall"]
            records.append(base)
    all_metrics = pd.DataFrame(records)
    status_frame = pd.DataFrame(statuses)
    status_frame.to_csv(results_dir / f"{profile}_run_status.csv", index=False)
    all_metrics.to_csv(results_dir / f"{profile}_metrics.csv", index=False)
    if all_metrics.empty:
        path = report_dir / "experiment_report.md"
        path.write_text(f"# Experiment report\n\nProfile: `{profile}`. No evaluated runs are available. No numerical research conclusions can be drawn.\n", encoding="utf-8")
        return {"report": str(path), "evaluated_runs": 0, "status_counts": status_frame["status"].value_counts().to_dict() if len(status_frame) else {}}
    metrics = all_metrics.loc[all_metrics["eligible"]].copy()
    group_cols = ["protocol", "model", "feature_set", "threshold_id", "rule", "alpha"]
    numeric = ["fpr", "recall", "precision", "f1", "binary_macro_f1", "average_precision", "roc_auc", "fp",
               "source_fpr", "delta_fpr", "composition", "within_stratum", "unsupported_target", "training_wall_seconds",
               "inference_cost_seconds_per_flow"]
    numeric = [c for c in numeric if c in metrics.columns]
    seed_summary = metrics.groupby(group_cols, dropna=False, observed=True)[numeric].agg(["mean", "std", "count"])
    seed_summary.columns = [f"{metric}_{stat}" for metric, stat in seed_summary.columns]
    seed_summary = seed_summary.reset_index()
    seed_summary.to_csv(results_dir / f"{profile}_seed_summary.csv", index=False)
    metrics["pareto_efficient"] = False
    # Cost comparison is meaningful only for the same target population and
    # inference batch/device. All thresholds, including dummy, remain visible.
    pareto_groups = ["protocol", "seed", "inference_batch_size", "inference_device"]
    for _, indices in metrics.groupby(pareto_groups, dropna=False, observed=True).groups.items():
        metrics.loc[indices, "pareto_efficient"] = pareto_mask(metrics.loc[indices])
    metrics["pareto_valid"] = np.isfinite(metrics[["recall", "fpr", "inference_cost_seconds_per_flow"]].to_numpy(dtype=float)).all(axis=1)
    metrics.to_csv(results_dir / f"{profile}_pareto.csv", index=False)
    comparisons, comparison_errors = [], []
    for run_f0, first in loaded.items():
        meta = first["metadata"]
        if meta.get("feature_set") != "F0":
            continue
        candidates = [(p, m) for p, m in loaded.items() if m["metadata"].get("feature_set") == "F1" and
                      all(m["metadata"].get(k) == meta.get(k) for k in ("model", "protocol", "seed", "profile", "split_hash", "config_hash"))]
        if len(candidates) == 1:
            try:
                comparisons.append(compare_feature_runs(run_f0, candidates[0][0]))
            except ValueError as exc:
                comparison_errors.append(f"{run_f0.name}: {exc}")
        elif len(candidates) > 1:
            comparison_errors.append(f"{run_f0.name}: ambiguous F1 pairing ({len(candidates)} candidates)")
    comparison_table = pd.concat(comparisons, ignore_index=True) if comparisons else pd.DataFrame()
    comparison_table.to_csv(results_dir / f"{profile}_paired_iat_differences.csv", index=False)
    _plots(metrics, figures_dir, profile)
    status_counts = status_frame["status"].value_counts().to_dict() if len(status_frame) else {}
    display_columns = ["protocol", "model", "feature_set", "threshold_id", "fpr_mean", "fpr_std", "fpr_count", "recall_mean", "recall_std", "recall_count", "average_precision_mean"]
    display_columns = [c for c in display_columns if c in seed_summary]
    decomposition_columns = ["protocol", "model", "feature_set", "threshold_id", "delta_fpr_mean", "composition_mean", "within_stratum_mean", "unsupported_target_mean"]
    decomposition_columns = [c for c in decomposition_columns if c in seed_summary]
    text = ["# Experiment report", "", f"Profile: `{profile}`. Evaluated fitted models: **{len(loaded)}**. Recorded run states: `{json.dumps(status_counts)}`.", "",
            "These are measured frozen-prediction results. Smoke results, when selected, are debugging evidence only. The test holdout was not used for model/feature/threshold selection. Earlier dataset-label audits were descriptive exploration, so this is not a claim that humans never viewed test labels.", "",
            "## Detection results and variation between seeds", "", _markdown_table(seed_summary, display_columns), "",
            "AP uses sklearn average_precision_score. Alpha is a source calibration FPR budget. Strict prediction rule: score > threshold. FPR is FP/(FP+TN). Standard deviation is sample standard deviation across valid runs; one valid seed gives N/A standard deviation. Each metric has its own valid-run count in the CSV.", "",
            "## False-alarm transfer decomposition", "", _markdown_table(seed_summary, decomposition_columns), "",
            "Delta FPR = composition + within-stratum + unsupported-target components, using source benign protocol support. TCP=6, UDP=17, ICMP=1, Other=remaining values. Missing conditional support is N/A. This is a descriptive identity, not causal attribution or a new theorem. Target benign labels are used only for post-freeze evaluation.", "",
            "## Paired uncertainty and IAT ablation", "",
            f"Matched F1-minus-F0 comparisons: {len(comparison_table)} metric/threshold/seed rows; see `results/{profile}_paired_iat_differences.csv`.", "",
            "Each run contains `bootstrap.csv` and `bootstrap_draws.parquet`: 95% percentile intervals from temporal 30-minute blocks by default, with source and target resampled separately within capture. Identical temporal draws pair thresholds and identical-row feature ablations. Models and thresholds stay frozen. Resample counts and valid denominator support are explicit. Few blocks and residual between-block dependence limit the intervals; these intervals do not estimate uncertainty across organizations. Calibration with no attacks yields N/A delta recall.", "",
            "Per-attack files report binary detection recall and support, plus descriptive binomial Wilson intervals whose independence assumption is not valid for correlated flows. Per-window negative/attack supports and temporal benign-score tails are retained per run.", "",
            "## Measured computation and Pareto comparison", "",
            f"`results/{profile}_pareto.csv` retains every eligible method and marks nondominated recall/FPR/measured preprocessing-plus-inference cost points. Comparisons are grouped by protocol, seed, inference batch size and inference device. Missing measured costs produce invalid Pareto status. Zero-recall all-benign methods remain visible and are not presented as successful detectors.", "",
            f"![Measured trade-off](../figures/{profile}_recall_fpr.png)", "",
            "Training time, preprocessing fit time, process-tree RSS, measured GPU device allocation, artifact bytes, warm-up/batch details and model-only versus full inference are recorded in run profiling artifacts. GPU allocation is a device measurement when available, not necessarily process-exclusive. Feature capture/extraction and packet-to-alert latency are outside this CSV experiment.", "",
            "## Scope and evidence limits", "",
            "This is one historical benchmark with two analysis capture blocks. Random and chronological protocols have different target populations; their difference is not a causal leakage estimate. The four-block conservative threshold is a source-only heuristic, not a future-FPR guarantee or conformal method. An empirical effect does not establish novelty. See CONTRIBUTION_EVIDENCE.md for the recorded experimental controls and results.", "",
            f"Full operating points: `results/{profile}_metrics.csv`; valid seed aggregates: `results/{profile}_seed_summary.csv`. Per-run artifacts: metrics.json, thresholds.json, decomposition.csv, per_attack.csv, windows.csv, score_tails.csv, bootstrap.csv, paired_threshold_differences.csv."]
    if comparison_errors:
        text += ["", "## Unavailable paired comparisons", "", *[f"- {error}" for error in comparison_errors]]
    report_path = report_dir / "experiment_report.md"
    report_path.write_text("\n".join(text)+"\n", encoding="utf-8")
    return {"report": str(report_path), "evaluated_runs": len(loaded), "status_counts": status_counts,
            "operating_points": len(metrics), "paired_iat_rows": len(comparison_table), "pairing_errors": comparison_errors}


def _plots(metrics, directory, profile):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    protocols = sorted(metrics["protocol"].dropna().unique())
    if not protocols:
        return
    fig, axes = plt.subplots(2, len(protocols), figsize=(7*len(protocols), 8), squeeze=False)
    all_groups = sorted(set(zip(metrics['model'], metrics['feature_set'])))
    color_map = {group: plt.get_cmap('tab10')(i) for i, group in enumerate(all_groups)}
    for column, protocol in enumerate(protocols):
        part = metrics.loc[metrics["protocol"].eq(protocol)]
        for row in [0, 1]:
            ax = axes[row, column]
            for (model, feature), group in part.groupby(["model", "feature_set"], observed=True):
                for rule, marker in [('T0', 'o'), ('T1', 's'), ('T2', '^')]:
                    selected = group.loc[group.rule.eq(rule)]
                    ax.scatter(selected["fpr"], selected["recall"], label=f"{model}/{feature}" if rule == 'T0' else None,
                               color=color_map[(model, feature)], marker=marker, alpha=.65, s=30)
            ax.axvline(.001, color="grey", linestyle=":", linewidth=.8)
            ax.axvline(.01, color="grey", linestyle="--", linewidth=.8)
            ax.set(xlabel="Target benign FPR (symlog)", ylabel="Attack recall",
                   title=str(protocol) + (' - all methods' if row == 0 else ' - recall detail'),
                   ylim=(-.025, 1.025) if row == 0 else (.99, 1.0005))
            ax.set_xscale("symlog", linthresh=.0001)
            ax.set_xlim(0, max(.012, part.fpr.max()*1.2))
            ax.grid(alpha=.2)
            if row == 0:
                ax.legend(fontsize=8)
    fig.suptitle('Circle: T0 (0.5); square: pooled T1; triangle: block T2. Lower panels zoom recall.', fontsize=11)
    fig.tight_layout()
    fig.savefig(directory / f"{profile}_recall_fpr.png", dpi=160)
    fig.savefig(directory / f"{profile}_recall_fpr.svg")
    plt.close(fig)
