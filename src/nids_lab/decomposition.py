"""Descriptive protocol-mixture decomposition and temporal-block uncertainty."""
from __future__ import annotations

import numpy as np
import pandas as pd

STRATA = ("TCP", "UDP", "ICMP", "Other")


def protocol_strata(protocols):
    values = np.asarray(protocols)
    return np.select((values == 6, values == 17, values == 1), ("TCP", "UDP", "ICMP"), default="Other")


def decompose_counts(source_n, source_fp, target_n, target_fp):
    """Counts end in the four strata; leading axes may be bootstrap replicates."""
    sn, sf, tn, tf = [np.asarray(x, dtype=np.float64) for x in (source_n, source_fp, target_n, target_fp)]
    if any(x.shape != sn.shape for x in (sf, tn, tf)) or sn.shape[-1] != 4:
        raise ValueError("Four equal-shaped protocol count arrays required")
    if np.any(sn < 0) or np.any(tn < 0) or np.any(sf < 0) or np.any(tf < 0) or np.any(sf > sn) or np.any(tf > tn):
        raise ValueError("Invalid negative/false-positive counts")
    st, tt = sn.sum(axis=-1, keepdims=True), tn.sum(axis=-1, keepdims=True)
    ws = np.divide(sn, st, out=np.full_like(sn, np.nan), where=st > 0)
    wt = np.divide(tn, tt, out=np.full_like(tn, np.nan), where=tt > 0)
    # Zero placeholders are used only in products with zero support. The public
    # stratum table reports unsupported conditional rates as None, never zero.
    rs = np.divide(sf, sn, out=np.zeros_like(sf), where=sn > 0)
    rt = np.divide(tf, tn, out=np.zeros_like(tf), where=tn > 0)
    composition = np.where(sn > 0, (wt-ws)*rs, 0.)
    within = np.where(sn > 0, wt*(rt-rs), 0.)
    unsupported = np.where(sn == 0, wt*rt, 0.)
    source_fpr = np.divide(sf.sum(axis=-1), st[..., 0], out=np.full(st.shape[:-1], np.nan), where=st[..., 0] > 0)
    target_fpr = np.divide(tf.sum(axis=-1), tt[..., 0], out=np.full(tt.shape[:-1], np.nan), where=tt[..., 0] > 0)
    valid = (st[..., 0] > 0) & (tt[..., 0] > 0)
    return {"source_fpr": source_fpr, "target_fpr": target_fpr,
            "delta_fpr": target_fpr-source_fpr,
            "composition": np.where(valid, composition.sum(axis=-1), np.nan),
            "within_stratum": np.where(valid, within.sum(axis=-1), np.nan),
            "unsupported_target": np.where(valid, unsupported.sum(axis=-1), np.nan),
            "ws": ws, "wt": wt, "rs": rs, "rt": rt,
            "composition_by_stratum": composition, "within_by_stratum": within,
            "unsupported_by_stratum": unsupported}


def _counts(frame, threshold):
    benign = frame.loc[frame["Label"].eq(0)]
    strata = protocol_strata(benign["PROTOCOL"])
    pred = benign["score"].to_numpy() > threshold
    return (np.array([np.sum(strata == g) for g in STRATA]),
            np.array([np.sum((strata == g) & pred) for g in STRATA]))


def fpr_decomposition(source: pd.DataFrame, target: pd.DataFrame, threshold: float):
    sn, sf = _counts(source, threshold)
    tn, tf = _counts(target, threshold)
    d = decompose_counts(sn, sf, tn, tf)
    summary = {k: float(d[k]) if np.isfinite(d[k]) else None for k in
               ("source_fpr", "target_fpr", "delta_fpr", "composition", "within_stratum", "unsupported_target")}
    if summary["delta_fpr"] is not None:
        residual = summary["delta_fpr"]-sum(summary[k] for k in ("composition", "within_stratum", "unsupported_target"))
        if abs(residual) > 1e-12:
            raise AssertionError("FPR decomposition identity violated")
        summary["identity_residual"] = residual
    rows = []
    for i, name in enumerate(STRATA):
        rows.append({"stratum": name, "source_n_benign": int(sn[i]), "target_n_benign": int(tn[i]),
                     "source_fp": int(sf[i]), "target_fp": int(tf[i]),
                     "source_weight": float(d["ws"][i]) if sn.sum() else None,
                     "target_weight": float(d["wt"][i]) if tn.sum() else None,
                     "source_fpr": float(d["rs"][i]) if sn[i] else None,
                     "target_fpr": float(d["rt"][i]) if tn[i] else None,
                     "composition": float(d["composition_by_stratum"][i]) if sn.sum() and tn.sum() else None,
                     "within_stratum": float(d["within_by_stratum"][i]) if sn.sum() and tn.sum() else None,
                     "unsupported_target": float(d["unsupported_by_stratum"][i]) if sn.sum() and tn.sum() else None})
    return summary, pd.DataFrame(rows)


def block_sufficient_counts(frame: pd.DataFrame, threshold: float, window_minutes: int = 30):
    """One row per capture/window; 4 benign counts, 4 FP counts, attacks, TP."""
    window = frame["FLOW_START_MILLISECONDS"].to_numpy(dtype=np.int64)//(window_minutes*60000)
    keys = pd.MultiIndex.from_arrays([frame["capture"].astype(str), window], names=["capture", "window"])
    block, unique = pd.factorize(keys, sort=True)
    n_blocks = len(unique)
    label = frame["Label"].to_numpy()
    pred = frame["score"].to_numpy() > threshold
    strata = protocol_strata(frame["PROTOCOL"])
    out = np.zeros((n_blocks, 10), dtype=np.int64)
    for i, name in enumerate(STRATA):
        mask = (label == 0) & (strata == name)
        out[:, i] = np.bincount(block[mask], minlength=n_blocks)
        out[:, i+4] = np.bincount(block[mask & pred], minlength=n_blocks)
    out[:, 8] = np.bincount(block[label == 1], minlength=n_blocks)
    out[:, 9] = np.bincount(block[(label == 1) & pred], minlength=n_blocks)
    return out, unique


def _resample_counts(counts, keys, n_resamples, rng):
    result = np.zeros((n_resamples, counts.shape[1]), dtype=np.float64)
    captures = np.asarray(keys.get_level_values(0))
    support = {}
    for capture in sorted(set(captures)):
        selected = counts[captures == capture]
        k = len(selected)
        support[str(capture)] = k
        # Multinomial weights are exactly equivalent to sampling k blocks with
        # replacement, without ever expanding individual flow observations.
        weights = rng.multinomial(k, np.full(k, 1/k), size=n_resamples)
        result += weights @ selected
    return result, support


def bootstrap_draws(source, target, threshold, n_resamples=500, seed=78193, window_minutes=30):
    if n_resamples < 1:
        return pd.DataFrame(), {"reason": "Bootstrap disabled by config", "resamples": 0}
    rng = np.random.default_rng(seed)
    source_counts, source_keys = block_sufficient_counts(source, threshold, window_minutes)
    target_counts, target_keys = block_sufficient_counts(target, threshold, window_minutes)
    s, source_support = _resample_counts(source_counts, source_keys, n_resamples, rng)
    t, target_support = _resample_counts(target_counts, target_keys, n_resamples, rng)
    d = decompose_counts(s[:, :4], s[:, 4:8], t[:, :4], t[:, 4:8])
    original_source_support = source_counts[:, :4].sum(axis=0) > 0
    preserves_source_support = np.all(s[:, :4][:, original_source_support] > 0, axis=1)
    # The decomposition reference support is fixed by the observed source. A
    # resample losing an originally supported stratum cannot estimate its source
    # conditional FPR; do not silently relabel that stratum as unsupported.
    for key in ("composition", "within_stratum", "unsupported_target"):
        d[key] = np.where(preserves_source_support, d[key], np.nan)
    sr = np.divide(s[:, 9], s[:, 8], out=np.full(n_resamples, np.nan), where=s[:, 8] > 0)
    tr = np.divide(t[:, 9], t[:, 8], out=np.full(n_resamples, np.nan), where=t[:, 8] > 0)
    rows = {"replicate": np.arange(n_resamples), "delta_fpr": d["delta_fpr"],
            "delta_recall": tr-sr, "test_fpr": d["target_fpr"], "test_recall": tr,
            "composition": d["composition"], "within_stratum": d["within_stratum"],
            "unsupported_target": d["unsupported_target"]}
    metadata = {"resamples": n_resamples, "seed": seed, "window_minutes": window_minutes,
                "source_blocks_per_capture": source_support, "target_blocks_per_capture": target_support,
                "estimand": "Frozen-model/threshold conditional temporal-block uncertainty; source and target resampled separately, stratified by capture",
                "pairing": "Identical seed and ordered capture/window keys pair all thresholds and matched feature sets",
                "caveat": "Few temporal blocks and dependence between blocks limit intervals; no between-organization uncertainty; decomposition components are undefined in resamples losing original source-stratum support",
                "resamples_preserving_source_stratum_support": int(preserves_source_support.sum()),
                "delta_recall_reason": "No source attack support" if int(source_counts[:, 8].sum()) == 0 else None}
    return pd.DataFrame(rows), metadata


def summarize_draws(draws: pd.DataFrame, points=None):
    records = []
    if draws.empty:
        return pd.DataFrame(records)
    for metric in draws.columns:
        if metric in ("replicate", "threshold_id"):
            continue
        values = draws[metric].to_numpy(dtype=float)
        valid = values[np.isfinite(values)]
        records.append({"metric": metric, "estimate": (points or {}).get(metric),
                        "lower_95": float(np.quantile(valid, .025)) if len(valid) else None,
                        "upper_95": float(np.quantile(valid, .975)) if len(valid) else None,
                        "valid_resamples": len(valid), "requested_resamples": len(values),
                        "reason": None if len(valid) else "Undefined support in every resample"})
    return pd.DataFrame(records)
