"""Binary detection metrics with explicit undefined cases."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def ranking_metrics(labels, scores) -> dict:
    labels = np.asarray(labels)
    scores = np.asarray(scores)
    if not np.isin(labels, [0, 1]).all() or not np.isfinite(scores).all():
        raise ValueError("Binary labels and finite scores are required")
    two_classes = len(np.unique(labels)) == 2
    return {"average_precision": float(average_precision_score(labels, scores)) if two_classes else None,
            "roc_auc": float(roc_auc_score(labels, scores)) if two_classes else None,
            "ranking_reason": None if two_classes else "AP/ROC-AUC not reported for a one-class or empty split",
            "average_precision_estimator": "sklearn.metrics.average_precision_score"}


def metrics_from_counts(tn, fp, fn, tp, alpha=None) -> dict:
    tn, fp, fn, tp = (int(x) for x in (tn, fp, fn, tp))
    if min(tn, fp, fn, tp) < 0:
        raise ValueError("Confusion counts cannot be negative")
    n_benign, n_attack = tn + fp, tp + fn
    recall = tp / n_attack if n_attack else None
    precision = tp / (tp + fp) if tp + fp else None
    fpr = fp / n_benign if n_benign else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    benign_f1 = 2 * tn / (2 * tn + fp + fn) if 2 * tn + fp + fn else None
    return {"n": n_benign + n_attack, "n_benign": n_benign, "n_attack": n_attack,
            "tn": tn, "fp": fp, "fn": fn, "tp": tp,
            "confusion_matrix": [[tn, fp], [fn, tp]], "precision": precision,
            "precision_reason": None if precision is not None else "No positive predictions",
            "recall": recall, "recall_reason": None if recall is not None else "No attack support",
            "f1": f1, "binary_macro_f1": (f1 + benign_f1) / 2 if f1 is not None and benign_f1 is not None else None,
            "fpr": fpr, "fpr_reason": None if fpr is not None else "No benign support",
            "false_alarms_per_10000_benign": 10000 * fpr if fpr is not None else None,
            "fpr_over_alpha": fpr / alpha if fpr is not None and alpha else None,
            "fpr_excess": max(0., fpr-alpha) if fpr is not None and alpha is not None else None,
            "attack_prevalence": n_attack / (n_benign + n_attack) if n_benign+n_attack else None}


def binary_metrics(labels, scores, threshold: float, alpha=None) -> dict:
    labels = np.asarray(labels)
    scores = np.asarray(scores, dtype=np.float64)
    if labels.shape != scores.shape or not np.isin(labels, [0, 1]).all() or not np.isfinite(scores).all():
        raise ValueError("Matching binary labels and finite scores are required")
    positive = scores > threshold
    benign = labels == 0
    return metrics_from_counts(np.sum(benign & ~positive), np.sum(benign & positive),
                               np.sum(~benign & ~positive), np.sum(~benign & positive), alpha)


def per_attack_metrics(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    records = []
    for attack, data in frame.loc[frame["Label"].eq(1)].groupby("Attack", observed=True, sort=True):
        n = len(data)
        detected = int(data["score"].gt(threshold).sum())
        p = detected/n
        z = 1.959963984540054
        denominator = 1+z*z/n
        centre = (p+z*z/(2*n))/denominator
        margin = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
        records.append({"Attack": str(attack), "n_attack": n, "detected": detected,
                        "binary_recall": p, "wilson_lower": max(0., centre-margin),
                        "wilson_upper": min(1., centre+margin),
                        "interval_caveat": "Descriptive binomial Wilson interval; correlated flows violate iid assumption"})
    return pd.DataFrame(records)


def window_metrics(frame: pd.DataFrame, threshold: float, window_minutes: int = 30) -> pd.DataFrame:
    width = int(window_minutes)*60000
    if width <= 0:
        raise ValueError("window_minutes must be positive")
    work = frame[["capture", "FLOW_START_MILLISECONDS", "Label", "score"]].copy()
    work["window_start_ms"] = (work["FLOW_START_MILLISECONDS"].astype("int64") // width)*width
    records = []
    for (capture, start), data in work.groupby(["capture", "window_start_ms"], observed=True, sort=True):
        m = binary_metrics(data["Label"], data["score"], threshold)
        records.append({"capture": str(capture), "window_start_ms": int(start),
                        "window_start_utc": pd.Timestamp(start, unit="ms", tz="UTC").isoformat(),
                        **{k: m[k] for k in ("n", "n_benign", "n_attack", "fp", "tp", "fpr", "recall")}})
    return pd.DataFrame(records)
