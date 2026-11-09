# Post-hoc nonfinite-rate association

This exploratory analysis joins raw-valued byte-rate features to existing frozen XGBoost/F1 predictions. No model, preprocessing, or threshold is modified. The source population is benign calibration; the target population is benign test under P_capture. Decisions use strict `score > threshold`.

The two directional rate features have identical nonfinite masks over all raw rows: True. Nonfinite means NaN or either infinity. These values were median-imputed by the previously frozen preprocessing pipeline. The finer `source_rate_nan` and `source_rate_inf` strata describe original source-to-destination values; both are mapped to missing before imputation, so the distinction is not an explicit flag seen by the model.

## Representative seed 42

| Split | Rule | Protocol | Rate values | Benign n | False positives | FPR | Share of protocol false positives |
|---|---|---|---|---:|---:|---:|---:|
| calibration | T0 | All | all | 337,801 | 0 | 0.0000% | N/A |
| calibration | T0 | All | finite | 330,785 | 0 | 0.0000% | N/A |
| calibration | T0 | All | nonfinite | 7,016 | 0 | 0.0000% | N/A |
| calibration | T0 | All | source_rate_nan | 68 | 0 | 0.0000% | N/A |
| calibration | T0 | All | source_rate_inf | 6,948 | 0 | 0.0000% | N/A |
| calibration | T0 | TCP | all | 263,290 | 0 | 0.0000% | N/A |
| calibration | T0 | TCP | finite | 262,788 | 0 | 0.0000% | N/A |
| calibration | T0 | TCP | nonfinite | 502 | 0 | 0.0000% | N/A |
| calibration | T0 | TCP | source_rate_nan | 27 | 0 | 0.0000% | N/A |
| calibration | T0 | TCP | source_rate_inf | 475 | 0 | 0.0000% | N/A |
| calibration | T0 | UDP | all | 74,339 | 0 | 0.0000% | N/A |
| calibration | T0 | UDP | finite | 67,825 | 0 | 0.0000% | N/A |
| calibration | T0 | UDP | nonfinite | 6,514 | 0 | 0.0000% | N/A |
| calibration | T0 | UDP | source_rate_nan | 41 | 0 | 0.0000% | N/A |
| calibration | T0 | UDP | source_rate_inf | 6,473 | 0 | 0.0000% | N/A |
| calibration | T1_alpha_0.001 | All | all | 337,801 | 253 | 0.0749% | 100.0000% |
| calibration | T1_alpha_0.001 | All | finite | 330,785 | 182 | 0.0550% | 71.9368% |
| calibration | T1_alpha_0.001 | All | nonfinite | 7,016 | 71 | 1.0120% | 28.0632% |
| calibration | T1_alpha_0.001 | All | source_rate_nan | 68 | 68 | 100.0000% | 26.8775% |
| calibration | T1_alpha_0.001 | All | source_rate_inf | 6,948 | 3 | 0.0432% | 1.1858% |
| calibration | T1_alpha_0.001 | TCP | all | 263,290 | 35 | 0.0133% | 100.0000% |
| calibration | T1_alpha_0.001 | TCP | finite | 262,788 | 6 | 0.0023% | 17.1429% |
| calibration | T1_alpha_0.001 | TCP | nonfinite | 502 | 29 | 5.7769% | 82.8571% |
| calibration | T1_alpha_0.001 | TCP | source_rate_nan | 27 | 27 | 100.0000% | 77.1429% |
| calibration | T1_alpha_0.001 | TCP | source_rate_inf | 475 | 2 | 0.4211% | 5.7143% |
| calibration | T1_alpha_0.001 | UDP | all | 74,339 | 46 | 0.0619% | 100.0000% |
| calibration | T1_alpha_0.001 | UDP | finite | 67,825 | 4 | 0.0059% | 8.6957% |
| calibration | T1_alpha_0.001 | UDP | nonfinite | 6,514 | 42 | 0.6448% | 91.3043% |
| calibration | T1_alpha_0.001 | UDP | source_rate_nan | 41 | 41 | 100.0000% | 89.1304% |
| calibration | T1_alpha_0.001 | UDP | source_rate_inf | 6,473 | 1 | 0.0154% | 2.1739% |
| test | T0 | All | all | 1,108,481 | 279 | 0.0252% | 100.0000% |
| test | T0 | All | finite | 1,062,113 | 274 | 0.0258% | 98.2079% |
| test | T0 | All | nonfinite | 46,368 | 5 | 0.0108% | 1.7921% |
| test | T0 | All | source_rate_nan | 11,811 | 5 | 0.0423% | 1.7921% |
| test | T0 | All | source_rate_inf | 34,557 | 0 | 0.0000% | 0.0000% |
| test | T0 | TCP | all | 848,104 | 39 | 0.0046% | 100.0000% |
| test | T0 | TCP | finite | 845,151 | 34 | 0.0040% | 87.1795% |
| test | T0 | TCP | nonfinite | 2,953 | 5 | 0.1693% | 12.8205% |
| test | T0 | TCP | source_rate_nan | 6 | 5 | 83.3333% | 12.8205% |
| test | T0 | TCP | source_rate_inf | 2,947 | 0 | 0.0000% | 0.0000% |
| test | T0 | UDP | all | 259,486 | 240 | 0.0925% | 100.0000% |
| test | T0 | UDP | finite | 216,316 | 240 | 0.1109% | 100.0000% |
| test | T0 | UDP | nonfinite | 43,170 | 0 | 0.0000% | 0.0000% |
| test | T0 | UDP | source_rate_nan | 11,560 | 0 | 0.0000% | 0.0000% |
| test | T0 | UDP | source_rate_inf | 31,610 | 0 | 0.0000% | 0.0000% |
| test | T1_alpha_0.001 | All | all | 1,108,481 | 12,868 | 1.1609% | 100.0000% |
| test | T1_alpha_0.001 | All | finite | 1,062,113 | 1,057 | 0.0995% | 8.2142% |
| test | T1_alpha_0.001 | All | nonfinite | 46,368 | 11,811 | 25.4723% | 91.7858% |
| test | T1_alpha_0.001 | All | source_rate_nan | 11,811 | 11,811 | 100.0000% | 91.7858% |
| test | T1_alpha_0.001 | All | source_rate_inf | 34,557 | 0 | 0.0000% | 0.0000% |
| test | T1_alpha_0.001 | TCP | all | 848,104 | 88 | 0.0104% | 100.0000% |
| test | T1_alpha_0.001 | TCP | finite | 845,151 | 82 | 0.0097% | 93.1818% |
| test | T1_alpha_0.001 | TCP | nonfinite | 2,953 | 6 | 0.2032% | 6.8182% |
| test | T1_alpha_0.001 | TCP | source_rate_nan | 6 | 6 | 100.0000% | 6.8182% |
| test | T1_alpha_0.001 | TCP | source_rate_inf | 2,947 | 0 | 0.0000% | 0.0000% |
| test | T1_alpha_0.001 | UDP | all | 259,486 | 11,889 | 4.5818% | 100.0000% |
| test | T1_alpha_0.001 | UDP | finite | 216,316 | 329 | 0.1521% | 2.7673% |
| test | T1_alpha_0.001 | UDP | nonfinite | 43,170 | 11,560 | 26.7779% | 97.2327% |
| test | T1_alpha_0.001 | UDP | source_rate_nan | 11,560 | 11,560 | 100.0000% | 97.2327% |
| test | T1_alpha_0.001 | UDP | source_rate_inf | 31,610 | 0 | 0.0000% | 0.0000% |

## Across three seeds

The full CSV includes all three seeds and All/TCP/UDP/ICMP/Other strata. Counts identify supports; zero false positives yield an undefined share, and empty strata yield an undefined FPR.

| Target T1, protocol/rate condition | Benign n | FP range | FPR range |
|---|---:|---:|---:|
| All / all | 1,108,481 | 12,864--13,115 | 1.1605%--1.1832% |
| All / finite | 1,062,113 | 1,051--1,306 | 0.0990%--0.1230% |
| All / nonfinite | 46,368 | 11,809--11,813 | 25.4680%--25.4766% |
| All / source_rate_inf | 34,557 | 0--2 | 0.0000%--0.0058% |
| All / source_rate_nan | 11,811 | 11,809--11,811 | 99.9831%--100.0000% |
| TCP / all | 848,104 | 84--403 | 0.0099%--0.0475% |
| TCP / finite | 845,151 | 76--397 | 0.0090%--0.0470% |
| TCP / nonfinite | 2,953 | 6--8 | 0.2032%--0.2709% |
| TCP / source_rate_inf | 2,947 | 0--2 | 0.0000%--0.0679% |
| TCP / source_rate_nan | 6 | 6--6 | 100.0000%--100.0000% |
| UDP / all | 259,486 | 11,821--11,889 | 4.5555%--4.5818% |
| UDP / finite | 216,316 | 263--329 | 0.1216%--0.1521% |
| UDP / nonfinite | 43,170 | 11,558--11,560 | 26.7732%--26.7779% |
| UDP / source_rate_inf | 31,610 | 0--0 | 0.0000%--0.0000% |
| UDP / source_rate_nan | 11,560 | 11,558--11,560 | 99.9827%--100.0000% |

## Nested UDP standardization

Apply the same descriptive composition/conditional-rate identity inside UDP, using finite versus nonfinite as the two exhaustive strata. There is support in both source strata. Values below are percentage points of UDP FPR, and this is an algebraic localization, not a causal decomposition.

| Seed | UDP FPR change (pp) | Missingness-composition term (pp) | Within-rate-condition term (pp) | Within share |
|---:|---:|---:|---:|---:|
| 42 | 4.519871 | 0.050306 | 4.469566 | 98.8870% |
| 2026 | 4.493666 | 0.050306 | 4.443360 | 98.8805% |
| 3407 | 4.525252 | 0.049445 | 4.475807 | 98.9074% |

A finer, still exploratory three-state partition (finite / original source-rate NaN / original source-rate infinity) yields a different allocation. The model transforms NaN and infinity identically before imputation; this partition is an external diagnostic and not a model input flag.

| Seed | UDP FPR change (pp) | Original-rate-state composition (pp) | Within-state term (pp) | Composition share |
|---:|---:|---:|---:|---:|
| 42 | 4.519871 | 4.399881 | 0.119991 | 97.3453% |
| 2026 | 4.493666 | 4.399881 | 0.093785 | 97.9129% |
| 3407 | 4.525252 | 4.399692 | 0.125560 | 97.2253% |

The representative seed-42 result is concentrated in the original source-rate NaN subgroup: all 41 source-calibration UDP members and all 11,560 target UDP members exceed T1, whereas no target member of either the original-infinity or NaN subgroup exceeds T0. The NaN subgroup share increases from 0.0552% to 4.4550% of benign UDP. Its stable 100% T1 subgroup rate and expanded prevalence show why the broad protocol decomposition cannot by itself distinguish conditional change from changes in finer traffic composition. The finer allocation is taxonomy-dependent, uses a source NaN support of only 41, and was discovered after observing results; it is a localization hypothesis for independent validation, not a validated causal mechanism.

Across seeds 42/2026/3407, T0 flags 0/58/64 members of the target UDP NaN subgroup, respectively, compared with 11,560/11,558/11,560 under T1. The three-state composition term averages 4.399818 percentage points of a 4.512930-point UDP FPR increase (97.4936% using the ratio of means).

Validation: all protocol-level supports and false-positive counts agree exactly with the earlier saved decomposition files. SHA256 values for the dataset and each run's predictions, threshold file, pipeline, job, and earlier decomposition are recorded in the JSON and were identical before and after this script.

## Interpretation boundary

These are descriptive conditional rates, not an intervention on missingness or imputation. Protocol, traffic duration, byte counts, application mix, and other correlated attributes can account for an association. No iid significance test is applied to temporally dependent flows. The post-hoc subgroup result must not be used to retune the reported frozen thresholds. A causal imputation or missingness-feature sensitivity claim would require a separate experiment.
