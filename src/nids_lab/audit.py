"""Full CSV audit before modelling, written using bounded row-group batches."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .data import START, END, EXPECTED_ROWS, file_hash, resolve_dataset
from .features import RAW_FEATURES, feature_columns
from .splits import sessionize, stable_hash


def audit_dataset(data_path: str | Path | None, workspace: str | Path = Path(".")) -> dict:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    processed = workspace / "data/processed"
    reports.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    source, provenance = resolve_dataset(data_path, workspace)
    report_path = reports / "dataset_audit.json"
    destination = processed / "dataset.parquet"
    if destination.exists() and report_path.exists():
        old = json.loads(report_path.read_text(encoding="utf-8"))
        if old.get("provenance", {}).get("csv_sha256") == provenance["csv_sha256"] and old.get("processed_sha256") == file_hash(destination):
            return old
        raise ValueError("Existing audited cache has mismatched fingerprint; preserve and inspect it before rebuilding.")
    original_columns = pd.read_csv(source, nrows=0).columns.str.strip().tolist()
    if len(original_columns) != 55 or set(original_columns) != set(RAW_FEATURES) | {
        START, END, "Label", "Attack", "IPV4_SRC_ADDR", "IPV4_DST_ADDR", "DNS_QUERY_ID"}:
        raise ValueError(f"Unexpected schema: {len(original_columns)} columns")
    text_columns = {"Attack", "IPV4_SRC_ADDR", "IPV4_DST_ADDR"}
    dtype = {c: (str if c in text_columns else "int64" if c in {START, END, "Label"} else "float64") for c in original_columns}
    event_columns = [c for c in original_columns if c not in {"Label", "Attack"}]
    metadata_columns = [START, END, "IPV4_SRC_ADDR", "IPV4_DST_ADDR", "L4_SRC_PORT", "L4_DST_PORT", "PROTOCOL", "Label", "Attack"]
    audit = {c: {"dtype": str(dtype[c]), "missing": 0, "positive_inf": 0, "negative_inf": 0,
                 "min": None, "max": None} for c in original_columns}
    label_counts, attack_counts, date_counts, date_attack_counts = Counter(), Counter(), Counter(), Counter()
    metadata_chunks, event_hashes, record_hashes, feature_hashes = [], [], [], []
    previous_timestamp, inversions, offset = None, 0, 0
    stage = processed / "audit_stage.parquet.partial"
    writer = None
    try:
        for chunk in pd.read_csv(source, dtype=dtype, chunksize=100_000):
            chunk.columns = chunk.columns.str.strip()
            for column in original_columns:
                series, info = chunk[column], audit[column]
                info["missing"] += int(series.isna().sum())
                if column not in text_columns:
                    info["positive_inf"] += int(np.isposinf(series.to_numpy()).sum())
                    info["negative_inf"] += int(np.isneginf(series.to_numpy()).sum())
                finite = series.replace([np.inf, -np.inf], np.nan) if column not in text_columns else series
                lo, hi = finite.min(), finite.max()
                if pd.notna(lo):
                    lo = lo.item() if isinstance(lo, np.generic) else lo
                    hi = hi.item() if isinstance(hi, np.generic) else hi
                    info["min"] = lo if info["min"] is None else min(info["min"], lo)
                    info["max"] = hi if info["max"] is None else max(info["max"], hi)
            label_counts.update(chunk.Label.value_counts().to_dict())
            attack_counts.update(chunk.Attack.value_counts().to_dict())
            dates = pd.to_datetime(chunk[START], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
            date_counts.update(dates.value_counts().to_dict())
            date_attack_counts.update(dates[chunk.Label.eq(1)].value_counts().to_dict())
            starts = chunk[START].to_numpy()
            inversions += int((np.diff(starts) < 0).sum())
            if previous_timestamp is not None:
                inversions += int(starts[0] < previous_timestamp)
            previous_timestamp = int(starts[-1])
            event = stable_hash(chunk[event_columns])
            event_hashes.append(event)
            record_hashes.append(stable_hash(chunk))
            feature_hashes.append(stable_hash(chunk[RAW_FEATURES]))
            chunk["row_id"] = np.arange(offset, offset + len(chunk), dtype=np.int64)
            chunk["event_hash"] = event
            meta = chunk[metadata_columns + ["row_id", "event_hash"]].copy()
            metadata_chunks.append(meta)
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(stage, table.schema, compression="zstd")
            writer.write_table(table, row_group_size=100_000)
            offset += len(chunk)
            print(f"audit: {offset:,} rows read", flush=True)
    finally:
        if writer is not None:
            writer.close()
    if offset != EXPECTED_ROWS or dict(label_counts) != {0: 2_237_731, 1:127_693}:
        raise ValueError(f"Dataset expected-count mismatch: rows={offset}, labels={dict(label_counts)}")
    for info in audit.values():
        info["constant"] = info["min"] == info["max"] and info["missing"] < offset
    metadata = pd.concat(metadata_chunks, ignore_index=True)
    del metadata_chunks
    all_events = np.concatenate(event_hashes)
    duplicate_event = pd.Series(all_events).duplicated(keep="first").to_numpy()
    conflicts = metadata.groupby("event_hash", sort=False).agg(label_count=("Label", "nunique"), attack_count=("Attack", "nunique"))
    conflicting_ids = conflicts.index[conflicts.label_count.gt(1) | conflicts.attack_count.gt(1)]
    del conflicts
    label_conflict = metadata.event_hash.isin(conflicting_ids).to_numpy()
    label_mapping_invalid = (~metadata.Label.isin([0, 1]) | (metadata.Label.eq(0) != metadata.Attack.eq("Benign"))).to_numpy()
    invalid_interval = (metadata[END] < metadata[START]) | (metadata[START] < 0) | (metadata[END] < 0)
    dates = pd.to_datetime(metadata[START], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    capture = np.where(dates.isin(["2015-01-22", "2015-01-23"]), "A", np.where(dates.eq("2015-02-18"), "B", "unknown"))
    print("audit: constructing bidirectional interval sessions", flush=True)
    metadata["group_id"] = sessionize(metadata, idle_seconds=60)
    metadata["capture"] = capture
    reason = np.full(offset, "", dtype=object)
    reason[duplicate_event] = "duplicate_event"
    reason[label_conflict] = "conflicting_event_labels"
    reason[label_mapping_invalid] = "invalid_label_mapping"
    reason[invalid_interval.to_numpy()] = "invalid_timestamp_interval"
    reason[capture == "unknown"] = "unexpected_capture_date"
    metadata["integrity_reason"] = reason
    additions = ["group_id", "capture", "integrity_reason"]
    final_stage = processed / "dataset.parquet.partial"
    writer = None
    batch_offset = 0
    try:
        for batch in pq.ParquetFile(stage).iter_batches(batch_size=100_000):
            table = pa.Table.from_batches([batch])
            for column in additions:
                values = metadata.iloc[batch_offset:batch_offset+len(batch)][column]
                table = table.append_column(column, pa.array(values, from_pandas=True))
            if writer is None:
                writer = pq.ParquetWriter(final_stage, table.schema, compression="zstd")
            writer.write_table(table, row_group_size=100_000)
            batch_offset += len(batch)
    finally:
        if writer is not None:
            writer.close()
    os.replace(final_stage, destination)
    stage.unlink()
    duplicates = {"exact_record_extra_rows": int(offset - len(np.unique(np.concatenate(record_hashes)))),
                  "event_extra_rows": int(duplicate_event.sum()),
                  "feature_vector_extra_rows_F1": int(offset - len(np.unique(np.concatenate(feature_hashes)))),
                  "conflicting_event_ids": len(conflicting_ids), "conflicting_event_rows": int(label_conflict.sum()),
                  "definition": "event = every original field except Label/Attack; exact record includes labels; feature vector uses only F1 predictors",
                  "rule": "retain smallest original row_id for repeated events; exclude all conflicting event labels; identical behavioral feature vectors are retained"}
    group_sizes = metadata.groupby("group_id").size()
    report = {"provenance": provenance, "rows": offset, "columns": len(original_columns), "column_audit": audit,
              "labels": {str(k):int(v) for k,v in label_counts.items()}, "attacks": dict(attack_counts),
              "dates_utc": {k:{"rows":int(v),"attack":int(date_attack_counts.get(k,0))} for k,v in sorted(date_counts.items())},
              "capture_counts": pd.Series(capture).value_counts().to_dict(),
              "timestamps": {"unit": "epoch milliseconds", "interpretation": "UTC for audit; original capture timezone unknown",
                             "storage": "int64", "adjacent_time_inversions_in_csv": inversions,
                             "invalid_intervals": int(invalid_interval.sum()),
                             "start_min_ms": int(metadata[START].min()), "start_max_ms": int(metadata[START].max())},
              "duplicates": duplicates, "label_mapping_invalid_rows": int(label_mapping_invalid.sum()),
              "integrity_exclusions": pd.Series(reason[reason != ""]).value_counts().to_dict(),
              "rows_after_integrity_exclusions": int((reason == "").sum()),
              "sessions": {"count": int(len(group_sizes)), "max_rows": int(group_sizes.max()),
                           "median_rows": float(group_sizes.median()), "idle_seconds":60,
                           "definition":"Bidirectional endpoint+port+protocol with start <= running maximum prior end + 60 seconds; heuristic grouping, not true PCAP sessions."},
              "hashing": {"dataset":"SHA256 and BagIt SHA1 verified", "row_id":"zero-based int64 original CSV position; identity is (dataset CSV SHA256, row_id)",
                          "event_group":"pandas stable uint64 hash with fixed key nidslab-2026-key; noncryptographic, collision probability not zero"},
              "prior_label_access":"Initial user descriptive audit already inspected labels; this is not an entirely unseen-label dataset.",
              "cache":"Single Parquet file with 100,000-row compressed row groups; all CSV reads and cache writes chunked; only audit/session metadata collected in RAM.",
              "processed_sha256":file_hash(destination), "processed_path":str(destination)}
    report_path.write_text(json.dumps(report, indent=2, default=int), encoding="utf-8")
    schema = {"raw_columns":original_columns, "F0":feature_columns(original_columns,"F0"),
              "F1":feature_columns(original_columns,"F1"), "raw_feature_counts":{"F0":40,"F1":48},
              "preprocessing":"training-fitted median imputer, deterministic signed log1p and StandardScaler for numeric features; PROTOCOL/L7_PROTO training-fitted OneHotEncoder unknown=ignore; ports numeric; output float32; timestamps never predictors",
              "excluded_predictors":[c for c in original_columns if c not in RAW_FEATURES] + ["row_id","event_hash","group_id","capture","integrity_reason"],
              "source_dictionary":"data/raw/NetFlow_v3_Features.csv; leading/trailing field whitespace normalized; meanings not repaired from suspected dictionary errors"}
    (reports / "feature_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    lines = ["# Full local dataset audit", "", f"Rows: {offset:,}; original columns: 55. ZIP and CSV match expected identity.", "",
        "Timestamp values retain int64 epoch milliseconds and are interpreted as UTC only for auditing. Original CSV order is not chronological.", "",
        "The user-provided prior audit inspected descriptive labels. This project does not claim all target labels were previously unseen.", "",
        "| UTC date | Rows | Attack rows |", "|---|---:|---:|"]
    lines += [f"| {d} | {v['rows']:,} | {v['attack']:,} |" for d,v in report["dates_utc"].items()]
    lines += ["", f"Exact record duplicate extras: {duplicates['exact_record_extra_rows']:,}; event duplicate extras: {duplicates['event_extra_rows']:,}; identical F1 feature vector extras: {duplicates['feature_vector_extra_rows_F1']:,}.",
              f"Conflicting event labels: {duplicates['conflicting_event_rows']:,} rows. Exclusions: {report['integrity_exclusions']}.",
              "", f"Sessions: {len(group_sizes):,}, maximum {group_sizes.max():,} flows. {report['sessions']['definition']}",
              "", "Duplicate events retain their first CSV row; feature-identical flows with different event metadata remain. All rows, including excluded rows, remain in the cache with an integrity reason.",
              "", "| Column | dtype | Missing | +Inf | -Inf | Constant |", "|---|---|---:|---:|---:|---|"]
    lines += [f"| {c} | {a['dtype']} | {a['missing']} | {a['positive_inf']} | {a['negative_inf']} | {a['constant']} |" for c,a in audit.items()]
    lines += ["", "Metadata dependence: labels, IP addresses, absolute timestamps, DNS_QUERY_ID and generated identifiers are excluded by an explicit allowlist. Ports, TTL and TCP windows remain possible environment proxies; optional F2 removes them. No target-based feature selection is used.",
              "", "All original numeric predictors are cached as float64 for stable chunk schemas, timestamps/row IDs/Label as int64. Model inputs become float32 only inside preprocessing. Parquet uses 100,000-row groups; the directory contains one file for consistent manifest joins.",
              "", "Full machine-readable details: `reports/dataset_audit.json`; explicit feature order: `reports/feature_schema.json`."]
    (reports / "DATA_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
