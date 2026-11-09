# Post-hoc threshold-update audit

Reproduce with `.venv/Scripts/python.exe scripts/posthoc_mitigation.py`, then
`scripts/revision_numbers.py` for the derived summary metrics. Both
read frozen predictions only; no model, preprocessing step or saved threshold is changed.

## Why this exists

This audit evaluates simple threshold-update rules
on the frozen February scores. It was specified after the main results, and after the two-hour
burst pattern of February false positives, had been seen. It is exploratory.

## Design

- Windows: 30-minute bins of `FLOW_START_MILLISECONDS` (UTC as read); February has 25 observed
  windows, no gaps. Evaluation span: windows 6 to 24 (03:00 to 12:29), 887,512 benign and
  87,244 attack flows, identical for every rule. No rule uses the window it is applied to.
- Rules (strict `score > tau`): static January `T1`/`T2` and `T0 = 0.5` (re-derived with
  `nids_lab.thresholds.fit_thresholds` and asserted equal to the saved thresholds); headroom
  (`T1` at alpha/10 on January); re-baseline on benign flows of the first k February windows
  (k = 2..6, history ending 01:00 to 03:00); rolling re-estimation from the benign flows of the
  previous 2, 4 or 6 windows (1, 2, 3 h); label-free rolling variants pooling every flow that `T0`
  does not flag.
- Uncertainty: i.i.d. bootstrap over the 19 evaluation windows (1,000 resamples, seed 20261108),
  common random numbers across rules, thresholds held fixed.
- Hashes of `predictions.parquet`, `thresholds.json` and `pipeline.joblib` for all 12 core runs
  are recorded before and after and must match.

## Main results (XGBoost/F1, alpha = 0.1%, three-seed means, evaluation span)

| Rule | FPR (%) | FPR / budget | Benign alerts/h | Recall (%) | FPR / budget if ties flagged |
|---|---:|---:|---:|---:|---:|
| Static January T1 | 1.202 | 12.02 | 1,124 | 99.9996 | 12.83 |
| Headroom alpha/10 | 0.947 | 9.47 | 886 | 99.9866 | 9.49 |
| Default T0 = 0.5 | 0.041 | 0.41 | 39 | 99.9408 | 0.41 |
| Re-baseline to 01:30 | 1.131 | 11.31 | 1,058 | 99.9996 | 11.87 |
| Re-baseline to 03:00 | 0.061 | 0.61 | 57 | 99.9866 | 5.92 |
| Rolling 1 h | 0.164 | 1.64 | 153 | 99.9870 | 6.46 |
| Rolling 2 h (labeled or label-free), 3 h | 0.061 | 0.61 | 57 | 99.9866 | 5.92 |

Across the four capture models, rolling 3 h keeps the budget ratio between 0.61 and 1.00.
Label-free rolling matches the labeled rule for XGBoost but not for LR on F1 (1.16), whose
pool still holds attacks in about 44% of its upper tail.

## Caveats that must accompany these numbers

1. **Ties.** For XGBoost every re-estimated threshold that meets the budget equals the exact
   score shared by about 4,700 benign UDP flows of the evaluation span (none in January, no
   attacks at that score). A rule that respects the budget must leave that group unflagged;
   flagging it gives about 0.59% (5.9x budget). No rate in between is attainable.
2. **Design dependence.** A re-baseline whose history ends at 01:30, before the first burst, still
   misses by 11.3x; scored from 04:00, the 1 h lookback equals the 2 h one (0.61x). The ranking of
   rules depends on where the bursts fall relative to the history and evaluation windows.
3. **Labels.** Labeled rules assume complete labels for past windows (a stand-in for triage).
4. **Scope.** One corpus, one February day; intervals cover window resampling only.

## Verification

An independent re-implementation written from the specification alone (without reading the
script) reproduced all 264 run-level records, the summary and violation tables, and every
bootstrap interval exactly; T1 and T2 re-derive exactly; hashes match the September freeze
records. The adversarial review that found the tie and design-dependence caveats is the source
of caveats 1 and 2, which are now computed by the script (`fpr_ties_flagged`, `rebaseline_k`,
`fpr_from_0400`) rather than asserted.

Outputs: `results/posthoc_mitigation_runs.csv`, `results/posthoc_mitigation_summary.csv`,
`results/posthoc_mitigation_windows_xgb_f1.csv`, `results/posthoc_mitigation.json`,
`results/revision_numbers.json`.
