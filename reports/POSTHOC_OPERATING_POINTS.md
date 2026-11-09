# Post-hoc operating-point audit

Reproduce with `.venv/Scripts/python.exe scripts/posthoc_operating_points.py`. This reads frozen XGBoost/F1 capture predictions for seeds 42, 2026, and 3407. No models or thresholds change. Input hashes and independent reconciliations with the existing metrics/decomposition tables are recorded in the JSON.

The band is `tau_rule < score <= 0.5`. Counts below are additional false positives and recovered attack detections when lowering T0 to the named rule; both calibrated rules use alpha = 0.001.

| Seed | Rule | Additional FP | Recovered attacks | FP / recovered attack | UDP share of additional FP |
|---|---|---:|---:|---:|---:|
| 42 | T1 | 12,589 | 62 | 203.05 | 92.53% |
| 42 | T2 | 12,589 | 62 | 203.05 | 92.53% |
| 2026 | T1 | 12,533 | 65 | 192.82 | 91.90% |
| 2026 | T2 | 12,402 | 65 | 190.80 | 92.87% |
| 3407 | T1 | 12,287 | 83 | 148.04 | 94.28% |
| 3407 | T2 | 12,287 | 83 | 148.04 | 94.28% |
| Pooled decisions | T1 | 37,409 | 210 | 178.14 | 92.89% |
| Pooled decisions | T2 | 37,278 | 210 | 177.51 | 93.22% |

## Reference sensitivity

All rates below are means over three seeds, in percent; components are percentage points. TCP+UDP denominators are 337,629 source and 1,107,590 target benign flows. Other is source-supported but deliberately excluded from this restricted subset.

| Rule | Full target FPR | TCP+UDP source FPR | TCP+UDP target FPR | TCP+UDP target at source weights | Within, target weights (pp) | Within, source weights (pp) |
|---|---:|---:|---:|---:|---:|---:|
| T0 | 0.0432 | 0.0000 | 0.0293 | 0.0278 | 0.0293 | 0.0278 |
| T1 | 1.1682 | 0.0317 | 1.0887 | 1.0245 | 1.0556 | 0.9923 |
| T2 | 1.1642 | 0.0281 | 1.0847 | 1.0205 | 1.0552 | 0.9919 |

The full-population alternative reference retains the unsupported ICMP term and source-supported Other stratum. Original: composition uses source rates, within uses target weights. Alternative: composition uses target rates, within uses source weights. Both sum exactly to the same observed change. Full per-seed moments, protocol counts, recovered attack families, and source-standardized rates are in `results/posthoc_operating_points.json`; all probabilities are stored without multiplication by 100.

The count and decomposition assertions passed; hashes of all nine input artifacts remained unchanged.
