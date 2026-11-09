"""Evaluate saved, frozen predictions without fitting or target adaptation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .decomposition import bootstrap_draws, fpr_decomposition, protocol_strata, summarize_draws
from .common import hash_object
from .metrics import binary_metrics, per_attack_metrics, ranking_metrics, window_metrics
from .thresholds import fit_thresholds


def _json_clean(value):
    if isinstance(value, dict):
        return {str(k): _json_clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _write_json(path, value):
    Path(path).write_text(json.dumps(_json_clean(value), indent=2, allow_nan=False), encoding="utf-8")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}


def _records_frame(frames):
    """Small analysis tables: preserve null columns without concat dtype drift."""
    return pd.DataFrame.from_records(record for frame in frames for record in frame.to_dict('records'))


def _row_signature(frame):
    columns = ["row_id", "Label", "PROTOCOL", "FLOW_START_MILLISECONDS", "capture"]
    ordered = frame[columns].sort_values("row_id")
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()


def _score_tails(frame, split, window_minutes):
    benign = frame.loc[frame["Label"].eq(0), ["score", "PROTOCOL", "capture", "FLOW_START_MILLISECONDS"]].copy()
    benign["stratum"] = protocol_strata(benign["PROTOCOL"])
    benign["window_start_ms"] = benign["FLOW_START_MILLISECONDS"]//(window_minutes*60000)*(window_minutes*60000)
    records = []
    for stratum, group in benign.groupby("stratum", observed=True, sort=True):
        records.append(_tail_row(group, split, str(stratum), "all", None))
    for (capture, window, stratum), group in benign.groupby(["capture", "window_start_ms", "stratum"], observed=True, sort=True):
        records.append(_tail_row(group, split, str(stratum), str(capture), int(window)))
    return pd.DataFrame(records)


def _tail_row(group, split, stratum, capture, window):
    quantiles = group["score"].quantile([.5, .9, .99, .999, 1.])
    return {"split": split, "stratum": stratum, "capture": capture, "window_start_ms": window,
            "n_benign": len(group), **{name: float(quantiles[q]) for name, q in
            (("q50", .5), ("q90", .9), ("q99", .99), ("q999", .999), ("max", 1.))}}


def evaluate_run(run_dir, config) -> dict:
    run_dir = Path(run_dir)
    metadata = _read_json(run_dir / "metadata.json")
    if metadata.get("config_hash") is not None and metadata["config_hash"] != hash_object(config):
        raise ValueError("Evaluation config hash differs from the frozen training config")
    threshold_path = run_dir / "thresholds.json"
    frozen_threshold_hash = metadata.get("thresholds_hash_before_test_prediction")
    if frozen_threshold_hash is not None:
        if not threshold_path.exists() or hashlib.sha256(threshold_path.read_bytes()).hexdigest() != frozen_threshold_hash:
            raise ValueError("Threshold artifact hash differs from the pre-test freeze")
    predictions = pd.read_parquet(run_dir / "predictions.parquet")
    required = {"row_id", "split", "score", "Label", "Attack", "PROTOCOL", "FLOW_START_MILLISECONDS", "capture", "group_id"}
    if missing := required-set(predictions.columns):
        raise ValueError(f"Prediction artifact lacks columns: {sorted(missing)}")
    if predictions["row_id"].duplicated().any():
        raise ValueError("Duplicate or cross-split row IDs in frozen predictions")
    if not np.isfinite(predictions["score"].to_numpy()).all():
        raise ValueError("Nonfinite frozen predictions")
    source = predictions.loc[predictions["split"].eq("calibration")]
    target = predictions.loc[predictions["split"].eq("test")]
    if len(source) == 0 or len(target) == 0:
        raise ValueError("Both calibration and test predictions must be present")
    if set(source["group_id"]) & set(target["group_id"]):
        raise ValueError("Calibration/test grouping overlap")
    options = config.get("evaluation", {})
    alphas = config.get("thresholds", {}).get("alphas", options.get("alphas", [0.001, 0.01]))
    if threshold_path.exists():
        thresholds = _read_json(threshold_path)
    else:
        threshold_options = config.get("thresholds", {})
        thresholds = fit_thresholds(source, alphas,
                                    threshold_options.get("min_block_size", options.get("min_block_size", 10000)),
                                    threshold_options.get("n_blocks", options.get("n_blocks", 4)))
        thresholds["freeze_note"] = "Reconstructed only from source calibration cached scores during evaluation; no target score or label used"
        _write_json(threshold_path, thresholds)
    if thresholds.get("decision_rule") != "score > threshold":
        raise ValueError("Threshold artifact must declare strict score > threshold decisions")
    profile = _read_json(run_dir / "profiling.json")
    n_resamples = int(options.get("bootstrap_resamples", 500))
    bootstrap_seed = int(options.get("bootstrap_seed", 78193))
    window_minutes = int(options.get("window_minutes", 30))
    result = {"run_id": run_dir.name, "metadata": metadata, "profiling": profile,
              "row_signatures": {"calibration": _row_signature(source), "test": _row_signature(target)},
              "ranking": {"calibration": ranking_metrics(source["Label"], source["score"]),
                          "test": ranking_metrics(target["Label"], target["score"])},
              "operating_points": [], "bootstrap_metadata": {}}
    decompositions, attacks, windows, intervals, draws_all = [], [], [], [], []
    for entry in thresholds["entries"]:
        point = {"threshold_id": entry["id"], **{k: entry.get(k) for k in ("rule", "alpha", "threshold", "eligible", "reason")}}
        if not entry["eligible"]:
            result["operating_points"].append(point)
            continue
        tau = float(entry["threshold"])
        point["calibration"] = binary_metrics(source["Label"], source["score"], tau, entry["alpha"])
        point["test"] = binary_metrics(target["Label"], target["score"], tau, entry["alpha"])
        point["decomposition"], table = fpr_decomposition(source, target, tau)
        decompositions.append(table.assign(threshold_id=entry["id"]))
        attacks.append(per_attack_metrics(target, tau).assign(threshold_id=entry["id"]))
        for split, frame in (("calibration", source), ("test", target)):
            windows.append(window_metrics(frame, tau, window_minutes).assign(split=split, threshold_id=entry["id"]))
        draws, bootstrap_meta = bootstrap_draws(source, target, tau, n_resamples, bootstrap_seed, window_minutes)
        result["bootstrap_metadata"][entry["id"]] = bootstrap_meta
        source_recall = point["calibration"]["recall"]
        target_recall = point["test"]["recall"]
        estimates = {**point["decomposition"], "test_fpr": point["test"]["fpr"], "test_recall": target_recall,
                     "delta_recall": target_recall-source_recall if source_recall is not None and target_recall is not None else None}
        intervals.append(summarize_draws(draws, estimates).assign(threshold_id=entry["id"]))
        draws_all.append(draws.assign(threshold_id=entry["id"]))
        result["operating_points"].append(point)
    for name, parts in (("decomposition", decompositions), ("per_attack", attacks), ("windows", windows), ("bootstrap", intervals)):
        _records_frame(parts).to_csv(run_dir / f"{name}.csv", index=False)
    pd.concat([_score_tails(source, "calibration", window_minutes), _score_tails(target, "test", window_minutes)], ignore_index=True).to_csv(run_dir / "score_tails.csv", index=False)
    all_draws = pd.concat(draws_all, ignore_index=True) if draws_all else pd.DataFrame()
    all_draws.to_parquet(run_dir / "bootstrap_draws.parquet", index=False)
    _threshold_comparisons(result, all_draws).to_csv(run_dir / "paired_threshold_differences.csv", index=False)
    _write_json(run_dir / "metrics.json", result)
    return _json_clean(result)


def _threshold_comparisons(result, draws):
    rows = []
    entries = result["operating_points"]
    if draws.empty:
        return pd.DataFrame(rows)
    for second in entries:
        if second["rule"] != "T2" or not second["eligible"]:
            continue
        first = next(x for x in entries if x["rule"] == "T1" and x["alpha"] == second["alpha"])
        left = draws.loc[draws["threshold_id"].eq(first["threshold_id"])].set_index("replicate").drop(columns="threshold_id")
        right = draws.loc[draws["threshold_id"].eq(second["threshold_id"])].set_index("replicate").drop(columns="threshold_id")
        estimates = {"test_fpr": second["test"]["fpr"]-first["test"]["fpr"],
                     "test_recall": (second["test"]["recall"]-first["test"]["recall"]) if second["test"]["recall"] is not None else None}
        for key in ("delta_fpr", "composition", "within_stratum", "unsupported_target"):
            a, b = first["decomposition"][key], second["decomposition"][key]
            estimates[key] = b-a if a is not None and b is not None else None
        summary = summarize_draws(right-left, estimates)
        rows.append(summary.assign(comparison="T2 minus T1", alpha=second["alpha"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def compare_feature_runs(run_f0, run_f1) -> pd.DataFrame:
    """Paired F1-minus-F0 confidence intervals on exactly matching frozen rows."""
    p0, p1 = Path(run_f0), Path(run_f1)
    m0, m1 = _read_json(p0 / "metrics.json"), _read_json(p1 / "metrics.json")
    for key in ("protocol", "model", "seed", "profile", "split_hash"):
        if m0["metadata"].get(key) != m1["metadata"].get(key):
            raise ValueError(f"Feature comparison requires matching {key}")
    if not m0["metadata"].get("training_rows_hash") or m0["metadata"].get("training_rows_hash") != m1["metadata"].get("training_rows_hash"):
        raise ValueError("Feature comparison requires matching saved training row hashes")
    if m0["row_signatures"] != m1["row_signatures"]:
        raise ValueError("Feature comparison requires identical calibration and test rows/labels/times")
    if m0["bootstrap_metadata"] != m1["bootstrap_metadata"]:
        raise ValueError("Feature comparison requires identical temporal resampling configuration")
    d0, d1 = pd.read_parquet(p0 / "bootstrap_draws.parquet"), pd.read_parquet(p1 / "bootstrap_draws.parquet")
    if d0.empty or d1.empty:
        return pd.DataFrame()
    records = []
    for first in m0["operating_points"]:
        if not first["eligible"]:
            continue
        second = next((x for x in m1["operating_points"] if x["threshold_id"] == first["threshold_id"] and x["eligible"]), None)
        if second is None:
            continue
        key = first["threshold_id"]
        left = d0.loc[d0["threshold_id"].eq(key)].set_index("replicate").drop(columns="threshold_id")
        right = d1.loc[d1["threshold_id"].eq(key)].set_index("replicate").drop(columns="threshold_id")
        estimates = {}
        for metric in ("fpr", "recall"):
            a, b = first["test"][metric], second["test"][metric]
            estimates[f"test_{metric}"] = b-a if a is not None and b is not None else None
        for metric in ("delta_fpr", "composition", "within_stratum", "unsupported_target"):
            a, b = first["decomposition"][metric], second["decomposition"][metric]
            estimates[metric] = b-a if a is not None and b is not None else None
        a_s, a_t = first["calibration"]["recall"], first["test"]["recall"]
        b_s, b_t = second["calibration"]["recall"], second["test"]["recall"]
        estimates["delta_recall"] = (b_t-b_s)-(a_t-a_s) if all(x is not None for x in (a_s, a_t, b_s, b_t)) else None
        records.append(summarize_draws(right-left, estimates).assign(
            comparison="F1 minus F0", threshold_id=key, alpha=first["alpha"],
            model=m0["metadata"].get("model"), protocol=m0["metadata"].get("protocol"),
            seed=m0["metadata"].get("seed"), run_f0=p0.name, run_f1=p1.name))
    return _records_frame(records)
