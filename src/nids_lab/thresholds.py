"""Source-only empirical thresholds. All decisions use the strict ``score > tau`` rule."""
from __future__ import annotations

import numpy as np
import pandas as pd


def pooled_threshold(scores, alpha: float) -> float:
    values = np.asarray(scores, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("Threshold calibration needs a nonempty finite score vector")
    if not 0 <= alpha < 1:
        raise ValueError("alpha must be in [0, 1)")
    # The order statistic is the smallest OBSERVED score whose strict upper tail
    # has at most floor(alpha*n) observations. Repeated values remain tied.
    rank = len(values) - int(np.floor(alpha * len(values))) - 1
    return float(np.partition(values, rank)[rank])


def temporal_blocks(timestamps, n_blocks: int = 4, min_block_size: int = 10000):
    """Return original indices in ordered blocks, preserving timestamp ties.

    Initial cuts use the nearest timestamp boundary to each equal-count target
    (the earlier boundary wins a tie). Repeated boundaries are dropped. The first
    undersized block is merged with the smaller adjacent block, earlier on ties.
    Merges depend only on time/order/count, never labels or scores.
    """
    times = np.asarray(timestamps, dtype=np.int64)
    if times.ndim != 1 or n_blocks < 1 or min_block_size < 1:
        raise ValueError("Invalid temporal block arguments")
    if len(times) == 0:
        return []
    order = np.argsort(times, kind="stable")
    ordered = times[order]
    boundaries = np.flatnonzero(ordered[1:] != ordered[:-1]) + 1
    cuts = []
    if len(boundaries):
        for k in range(1, n_blocks):
            target = len(times) * k / n_blocks
            position = int(np.searchsorted(boundaries, target))
            candidates = boundaries[max(0, position - 1): min(len(boundaries), position + 1)]
            cuts.append(int(min(candidates, key=lambda x: (abs(x-target), x))))
    blocks = list(np.split(order, sorted(set(cuts))))
    while len(blocks) > 1:
        undersized = next((i for i, b in enumerate(blocks) if len(b) < min_block_size), None)
        if undersized is None:
            break
        i = undersized
        neighbours = [j for j in (i-1, i+1) if 0 <= j < len(blocks)]
        j = min(neighbours, key=lambda x: (len(blocks[x]), x))
        left, right = sorted((i, j))
        blocks[left:right+1] = [np.concatenate((blocks[left], blocks[right]))]
    return blocks


def fit_thresholds(calibration: pd.DataFrame, alphas=(0.001, 0.01),
                   min_block_size: int = 10000, n_blocks: int = 4) -> dict:
    benign = calibration.loc[calibration["Label"].eq(0)]
    scores = benign["score"].to_numpy(dtype=np.float64)
    if len(scores) == 0:
        raise ValueError("No source benign calibration rows; thresholds are undefined")
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite calibration scores")
    blocks = temporal_blocks(benign["FLOW_START_MILLISECONDS"].to_numpy(), n_blocks, min_block_size)
    block_info = [{"block": i, "n_benign": len(indices),
                   "start_ms": int(benign.iloc[indices]["FLOW_START_MILLISECONDS"].min()),
                   "end_ms": int(benign.iloc[indices]["FLOW_START_MILLISECONDS"].max())}
                  for i, indices in enumerate(blocks)]
    entries = [{"id": "T0", "rule": "T0", "alpha": None, "threshold": 0.5,
                "eligible": True, "source_n_benign": len(scores),
                "source_fpr": float(np.mean(scores > 0.5))}]
    for alpha in alphas:
        alpha = float(alpha)
        tau = pooled_threshold(scores, alpha)
        suffix = format(alpha, ".6g")
        entries.append({"id": f"T1_alpha_{suffix}", "rule": "T1", "alpha": alpha,
                        "threshold": tau, "eligible": True, "source_n_benign": len(scores),
                        "source_fpr": float(np.mean(scores > tau))})
        eligible = len(blocks) >= 2 and all(len(b) >= min_block_size for b in blocks)
        taus = [pooled_threshold(scores[b], alpha) for b in blocks] if eligible else []
        tau = max(taus) if taus else None
        entries.append({"id": f"T2_alpha_{suffix}", "rule": "T2", "alpha": alpha,
                        "threshold": tau, "eligible": eligible, "source_n_benign": len(scores),
                        "source_fpr": float(np.mean(scores > tau)) if eligible else None,
                        "block_thresholds": taus,
                        "block_fprs": [float(np.mean(scores[b] > tau)) for b in blocks] if eligible else [],
                        "reason": None if eligible else "Fewer than two temporal benign blocks meeting minimum support"})
    return {"decision_rule": "score > threshold", "calibration_uses": "source Label == 0 only",
            "block_method": "nearest equal-count timestamp boundary; first undersized block merged with smallest adjacent block, earlier on ties",
            "min_block_size": min_block_size, "blocks": block_info, "entries": entries}
