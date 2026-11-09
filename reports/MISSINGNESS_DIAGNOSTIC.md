# Post-freeze missingness diagnostic

Exploratory descriptive analysis performed after the model/split plan was frozen. It did not change preprocessing, features, models or thresholds.

Population: integrity-valid flows, before the P_capture temporal purge. Source/target labels are descriptive strata here, never calibration inputs from the target.

| Capture | Feature | Flows | NaN | Inf | Nonfinite fraction |
|---|---|---:|---:|---:|---:|
| A | DST_TO_SRC_SECOND_BYTES | 1,131,909 | 0 | 31,810 | 2.8103% |
| A | SRC_TO_DST_SECOND_BYTES | 1,131,909 | 7,343 | 24,467 | 2.8103% |
| B | DST_TO_SRC_SECOND_BYTES | 1,218,700 | 0 | 77,315 | 6.3441% |
| B | SRC_TO_DST_SECOND_BYTES | 1,218,700 | 42,758 | 34,557 | 6.3441% |

Detailed benign/attack and TCP/UDP/ICMP/Other counts: `results/missingness_by_capture_protocol.csv`.

Nonfinite values are replaced with NaN, then imputed using training medians within each saved pipeline. A capture-dependent missingness pattern is a potential environment proxy; this audit does not establish its causal effect on false alarms. A missingness-feature sensitivity study would be a separate follow-up experiment.
