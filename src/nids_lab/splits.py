"""Capture-aware, session-disjoint manifests with event-integrity exclusions."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from .data import START, END, file_hash

HASH_KEY = "nidslab-2026-key"


def stable_hash(frame: pd.DataFrame) -> np.ndarray:
    return pd.util.hash_pandas_object(frame, index=False, hash_key=HASH_KEY).to_numpy(dtype=np.uint64)


def sessionize(frame: pd.DataFrame, idle_seconds: int = 60) -> np.ndarray:
    """Bidirectional endpoint+port+protocol sessions, split after >60s idle.

    A flow joins if its start is at most idle_ms beyond the running maximum
    previous end for this key. This correctly handles overlapping intervals.
    Hash IDs are deterministic uint64, not ground-truth PCAP session IDs.
    """
    src = frame["IPV4_SRC_ADDR"].astype(str) + ":" + frame["L4_SRC_PORT"].astype(str)
    dst = frame["IPV4_DST_ADDR"].astype(str) + ":" + frame["L4_DST_PORT"].astype(str)
    forward = src <= dst
    endpoints = pd.DataFrame({"endpoint_a": src.where(forward, dst), "endpoint_b": dst.where(forward, src),
                              "protocol": frame["PROTOCOL"].to_numpy()})
    keys = stable_hash(endpoints)
    ordered = pd.DataFrame({"key": keys, "start": frame[START].to_numpy(dtype=np.int64),
                            "end": frame[END].to_numpy(dtype=np.int64),
                            "row": frame["row_id"].to_numpy(dtype=np.int64), "position": np.arange(len(frame))})
    ordered.sort_values(["key", "start", "row"], kind="stable", inplace=True)
    max_end = ordered.groupby("key", sort=False)["end"].cummax()
    prior_end = max_end.shift(1)
    boundary = ordered["key"].ne(ordered["key"].shift(1)) | ordered["start"].gt(prior_end + idle_seconds * 1000)
    # The first CSV row in each sorted session is its deterministic anchor.
    anchors = ordered["row"].where(boundary).ffill().astype(np.int64)
    group = stable_hash(pd.DataFrame({"key": ordered["key"].to_numpy(), "anchor_row": anchors.to_numpy()}))
    result = np.empty(len(frame), dtype=np.uint64)
    result[ordered["position"].to_numpy()] = group
    return result


def _group_holdout(groups: pd.DataFrame, fraction: float, seed: int):
    ids = groups.index.to_numpy()
    if len(ids) < 2:
        raise ValueError("At least two session groups required for a nonempty split")
    strata = groups["stratum"].astype(str)
    counts = strata.value_counts()
    feasible = counts.min() >= 2 and int(np.ceil(len(ids) * fraction)) >= len(counts) and int(np.floor(len(ids) * (1-fraction))) >= len(counts)
    first, second = train_test_split(ids, test_size=fraction, random_state=seed,
                                     stratify=strata if feasible else None)
    return first, second, bool(feasible)


def _group_table(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby("group_id", sort=True)
    result = grouped.agg(start=(START, "min"), end=(END, "max"), count=("row_id", "size"), attack=("Label", "max"))
    # Mixed-family groups retain a deterministic category-set stratum. Collapse
    # rare combinations to binary attack to avoid infeasible tiny strata.
    categories = grouped["Attack"].first()
    categories = categories.where(grouped["Attack"].nunique().eq(1), "MixedAttack")
    count = categories.value_counts()
    result["stratum"] = categories.where(categories.map(count) >= 10, result["attack"].map({0: "Benign", 1: "RareAttack"}))
    return result


def build_split_manifest(frame: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, dict]:
    """Pure split builder for testing; input includes session/event IDs."""
    seed = int(config.get("split_seed", 42))
    embargo_ms = int(config.get("embargo_seconds", 60)) * 1000
    a_fraction = float(config.get("capture_train_fraction", .7))
    dev_fraction = float(config.get("development_fraction", .2))
    columns = ["row_id", "group_id", "event_hash", "capture", START, "Label", "Attack"]
    manifest = frame[columns].copy()
    manifest["P_capture"] = "excluded"
    manifest["P_random"] = "excluded"
    integrity = frame.get("integrity_reason", pd.Series("", index=frame.index)).eq("")
    valid = frame.loc[integrity]
    a = valid.loc[valid["capture"].eq("A")].sort_values([START, "row_id"], kind="stable")
    if a.empty:
        raise ValueError("No valid January source rows")
    cutoff = int(a.iloc[min(int(len(a) * a_fraction), len(a)-1)][START])
    group_stats = valid.groupby("group_id", sort=False).agg(start=(START, "min"), end=(END, "max"), captures=("capture", "nunique"))
    crossing_capture = set(group_stats.index[group_stats["captures"].gt(1)])
    # Whole group removed if ANY member intersects the inclusive embargo.
    collision = (group_stats["start"] <= cutoff + embargo_ms) & (group_stats["end"] >= cutoff - embargo_ms)
    purged_groups = set(group_stats.index[collision]) | crossing_capture
    source_groups = _group_table(a.loc[~a["group_id"].isin(purged_groups)])
    historical = source_groups.loc[source_groups["end"] < cutoff - embargo_ms]
    calibration = source_groups.loc[source_groups["start"] > cutoff + embargo_ms]
    training, development, stratified_capture = _group_holdout(historical, dev_fraction, seed)
    manifest.loc[integrity & manifest["group_id"].isin(training), "P_capture"] = "train"
    manifest.loc[integrity & manifest["group_id"].isin(development), "P_capture"] = "development"
    manifest.loc[integrity & manifest["group_id"].isin(calibration.index), "P_capture"] = "calibration"
    manifest.loc[integrity & manifest["capture"].eq("B") & ~manifest["group_id"].isin(purged_groups), "P_capture"] = "test"
    # Four-way group-level stratification. Ratios target group counts; unequal
    # session sizes may yield different row ratios, which are reported.
    random_groups = _group_table(valid)
    train_ids, remainder_ids, strat1 = _group_holdout(random_groups, .4, seed)
    remainder = random_groups.loc[remainder_ids]
    dev_ids, cal_test_ids, strat2 = _group_holdout(remainder, .75, seed + 1)
    cal_ids, test_ids, strat3 = _group_holdout(random_groups.loc[cal_test_ids], .5, seed + 2)
    for partition, ids in (("train", train_ids), ("development", dev_ids), ("calibration", cal_ids), ("test", test_ids)):
        manifest.loc[integrity & manifest["group_id"].isin(ids), "P_random"] = partition
    verify_manifest(manifest, cutoff, embargo_ms)
    report = {"seed": seed, "cutoff_epoch_milliseconds": cutoff,
              "cutoff_utc": pd.Timestamp(cutoff, unit="ms", tz="UTC").isoformat(),
              "embargo_seconds": embargo_ms // 1000,
              "purge_rule": "Exclude entire session group intersecting inclusive cutoff +/- embargo; exclude groups spanning captures.",
              "cutoff_rule": "70% (configurable) ordered integrity-valid A rows; equal timestamps stay together.",
              "grouping": "Bidirectional endpoint+port+protocol; 60 second idle from running interval end; heuristic, not PCAP sessions.",
              "stratification": {"P_capture": stratified_capture, "P_random_stages": [strat1, strat2, strat3]},
              "random_ratio_unit": "session groups (60/10/15/15); observed row fractions below",
              "prior_label_access": "User's prior descriptive audit inspected labels; full benchmark labels used for descriptive audit and diagnostic random stratification. Target is excluded from capture model selection/calibration.",
              "total_rows": len(frame), "integrity_excluded_rows": int((~integrity).sum()),
              "integrity_exclusions_by_reason": frame.loc[~integrity, "integrity_reason"].value_counts().to_dict() if "integrity_reason" in frame else {},
              "purged_groups": len(purged_groups),
              "P_capture_temporal_excluded_rows": int((integrity & manifest["P_capture"].eq("excluded")).sum()),
              "partitions": {}}
    for protocol in ("P_capture", "P_random"):
        report["partitions"][protocol] = {}
        for partition, subset in manifest.groupby(protocol):
            report["partitions"][protocol][partition] = {"rows": len(subset), "groups": subset.group_id.nunique(),
                "label_counts": {str(k): int(v) for k,v in subset.Label.value_counts().items()},
                "attack_counts": {str(k): int(v) for k,v in subset.Attack.value_counts().items()},
                "captures": subset.capture.value_counts().to_dict(),
                "start_min_ms": int(subset[START].min()), "start_max_ms": int(subset[START].max())}
    return manifest, report


def verify_manifest(manifest: pd.DataFrame, cutoff: int | None = None, embargo_ms: int = 60_000):
    if manifest.row_id.duplicated().any():
        raise AssertionError("Duplicate row IDs")
    for protocol in ("P_capture", "P_random"):
        included = manifest.loc[manifest[protocol].ne("excluded")]
        for key in ("group_id", "event_hash"):
            if included.groupby(key)[protocol].nunique().gt(1).any():
                raise AssertionError(f"{key} overlaps partitions of {protocol}")
    if cutoff is not None:
        source = manifest.P_capture.isin(["train", "development"])
        calibration = manifest.P_capture.eq("calibration")
        assert manifest.loc[source, START].lt(cutoff - embargo_ms).all()
        assert manifest.loc[calibration, START].gt(cutoff + embargo_ms).all()
        assert manifest.loc[source | calibration, "capture"].eq("A").all()
        assert manifest.loc[manifest.P_capture.eq("test"), "capture"].eq("B").all()


def prepare_splits(config: dict, workspace: str | Path = Path(".")) -> dict:
    workspace = Path(workspace).resolve()
    output = workspace / "manifests/split_manifest.parquet"
    report_path = workspace / "reports/split_report.json"
    split_config = {k: config.get(k, v) for k,v in {"split_seed":42,"embargo_seconds":60,
        "session_idle_seconds":60,"capture_train_fraction":.7,"development_fraction":.2}.items()}
    if split_config["session_idle_seconds"] != 60:
        raise ValueError("Audit cache sessionization is frozen at 60 seconds; rebuild explicitly for sensitivity.")
    if output.exists() and report_path.exists():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        audit_identity = json.loads((workspace / "reports/dataset_audit.json").read_text(encoding="utf-8"))["provenance"]["csv_sha256"]
        if previous.get("split_config") == split_config and previous.get("split_sha256") == file_hash(output) and previous.get("dataset_csv_sha256") == audit_identity:
            return previous
        raise ValueError("Existing frozen split belongs to different configuration or hash; preserve it and use a separate workspace.")
    source = workspace / "data/processed/dataset.parquet"
    if not source.exists():
        from .audit import audit_dataset
        audit_dataset(config.get("data_path"), workspace)
    columns = ["row_id", "group_id", "event_hash", "capture", START, END, "Label", "Attack", "integrity_reason"]
    frame = pd.read_parquet(source, columns=columns)
    manifest, report = build_split_manifest(frame, config)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_parquet(output, index=False, compression="zstd", row_group_size=100_000)
    report.update(split_config=split_config, split_sha256=file_hash(output), manifest_path=str(output))
    report["dataset_csv_sha256"] = json.loads((workspace / "reports/dataset_audit.json").read_text(encoding="utf-8"))["provenance"]["csv_sha256"]
    report_path.write_text(json.dumps(report, indent=2, default=int), encoding="utf-8")
    return report


prepare = prepare_splits
