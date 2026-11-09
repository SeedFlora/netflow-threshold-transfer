"""Post-hoc association of frozen scores with nonfinite byte-rate attributes.

This script reads saved predictions and raw-valued processed attributes only.
It does not fit a model, select a threshold, or change an earlier experiment.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main(workspace=Path('.')):
    workspace = Path(workspace)
    run_directories = sorted((workspace / 'runs').glob('main_P_capture_xgboost_F1_*'))
    input_paths = [workspace / 'data/processed/dataset.parquet'] + [
        directory / name for directory in run_directories
        for name in ['predictions.parquet', 'thresholds.json', 'pipeline.joblib', 'job.json', 'decomposition.csv']]
    input_hashes = {str(p.relative_to(workspace)): sha256(p) for p in input_paths}
    features = ['SRC_TO_DST_SECOND_BYTES', 'DST_TO_SRC_SECOND_BYTES']
    raw = pd.read_parquet(workspace / 'data/processed/dataset.parquet',
                          columns=['row_id', 'integrity_reason'] + features)
    assert raw.row_id.is_unique
    masks = ~np.isfinite(raw[features].to_numpy())
    raw['nonfinite_either_rate'] = masks.any(axis=1)
    raw['mask_disagrees'] = masks[:, 0] != masks[:, 1]
    raw['source_rate_nan'] = np.isnan(raw[features[0]])
    raw['source_rate_inf'] = np.isinf(raw[features[0]])
    valid = raw.integrity_reason.eq('')
    audit = dict(
        analysis='Exploratory post-hoc association conditional on frozen predictions',
        protocol='P_capture', model='xgboost', feature_set='F1',
        masks_equal_all_raw=bool((masks[:, 0] == masks[:, 1]).all()),
        masks_disagree_all_raw=int((masks[:, 0] != masks[:, 1]).sum()),
        masks_disagree_integrity_valid=int(raw.loc[valid, 'mask_disagrees'].sum()),
        raw_source_rate_negative_inf=int(np.isneginf(raw[features[0]]).sum()),
        raw_destination_rate_nan=int(np.isnan(raw[features[1]]).sum()),
        raw_destination_rate_negative_inf=int(np.isneginf(raw[features[1]]).sum()),
        population='Benign source calibration and benign target test only',
        decision_rule='score > stored threshold',
        interpretation='Association, not a causal effect of missingness or median imputation; no refit or target-driven threshold selection.',
        runs=[])
    raw = raw[['row_id', 'integrity_reason', 'nonfinite_either_rate', 'mask_disagrees',
               'source_rate_nan', 'source_rate_inf']]
    rows = []
    for directory in run_directories:
        config = json.loads((directory / 'job.json').read_text(encoding='utf-8'))
        # The seed is in both the frozen directory convention and the job file.
        seed = int(directory.name.split('_')[-2])
        assert seed == config['spec']['seed']
        pred = pd.read_parquet(directory / 'predictions.parquet')
        assert pred.row_id.is_unique
        pred = pred.loc[pred.Label.eq(0) & pred.split.isin(['calibration', 'test'])]
        frame = pred.merge(raw, on='row_id', how='left', validate='one_to_one', indicator=True)
        assert frame._merge.eq('both').all()
        assert frame.integrity_reason.eq('').all()
        assert not frame.mask_disagrees.any()
        frame['stratum'] = np.select([frame.PROTOCOL.eq(6), frame.PROTOCOL.eq(17), frame.PROTOCOL.eq(1)],
                                     ['TCP', 'UDP', 'ICMP'], default='Other')
        stored = json.loads((directory / 'thresholds.json').read_text(encoding='utf-8'))
        entries = {entry['id']: entry for entry in stored['entries']}
        audit['runs'].append(dict(run=directory.name, seed=seed, joined_benign_rows=len(frame),
                                  calibration_benign=int(frame.split.eq('calibration').sum()),
                                  test_benign=int(frame.split.eq('test').sum())))
        for split, split_frame in frame.groupby('split', observed=True):
            for rule in ['T0', 'T1_alpha_0.001']:
                tau = entries[rule]['threshold']
                split_fp = int((split_frame.score > tau).sum())
                for stratum in ['All', 'TCP', 'UDP', 'ICMP', 'Other']:
                    selected = split_frame if stratum == 'All' else split_frame.loc[split_frame.stratum.eq(stratum)]
                    stratum_fp = int((selected.score > tau).sum())
                    condition_masks = dict(all=np.ones(len(selected), dtype=bool),
                                           finite=~selected.nonfinite_either_rate,
                                           nonfinite=selected.nonfinite_either_rate,
                                           source_rate_nan=selected.source_rate_nan,
                                           source_rate_inf=selected.source_rate_inf)
                    assert np.array_equal(selected.nonfinite_either_rate,
                                          selected.source_rate_nan | selected.source_rate_inf)
                    for condition, condition_mask in condition_masks.items():
                        group = selected.loc[condition_mask]
                        n = len(group)
                        fp = int((group.score > tau).sum())
                        rows.append(dict(seed=seed, split=split, rule=rule, threshold=tau,
                                         stratum=stratum, rate_condition=condition, n_benign=n,
                                         false_positives=fp, fpr=fp/n if n else np.nan,
                                         population_fraction=n/len(selected) if len(selected) else np.nan,
                                         fp_share_in_stratum=fp/stratum_fp if stratum_fp else np.nan,
                                         fp_share_in_split=fp/split_fp if split_fp else np.nan))
        previous = pd.read_csv(directory / 'decomposition.csv')
        for r in previous.loc[previous.threshold_id.isin(['T0', 'T1_alpha_0.001'])].itertuples():
            for split, n, fp in [('calibration', r.source_n_benign, r.source_fp),
                                  ('test', r.target_n_benign, r.target_fp)]:
                matched = [row for row in rows if row['seed'] == seed and row['split'] == split
                           and row['stratum'] == r.stratum and row['rule'] == r.threshold_id
                           and row['rate_condition'] == 'all']
                assert len(matched) == 1
                assert matched[0]['n_benign'] == n and matched[0]['false_positives'] == fp
    table = pd.DataFrame(rows)
    # Nested descriptive standardization: separate the changed prevalence of
    # nonfinite UDP rates from changed conditional false-positive rates.
    for decomposition_name, conditions in [
            ('udp_binary_missingness_decomposition', ['finite', 'nonfinite']),
            ('udp_original_rate_state_decomposition', ['finite', 'source_rate_nan', 'source_rate_inf'])]:
        audit[decomposition_name] = []
        for seed in sorted(table.seed.unique()):
            subset = table.loc[table.seed.eq(seed) & table.rule.eq('T1_alpha_0.001') &
                               table.stratum.eq('UDP') & table.rate_condition.isin(conditions)]
            src = subset.loc[subset.split.eq('calibration')].set_index('rate_condition')
            tgt = subset.loc[subset.split.eq('test')].set_index('rate_condition')
            ws, wt = src.population_fraction, tgt.population_fraction
            assert abs(ws.sum() - 1) < 1e-12 and abs(wt.sum() - 1) < 1e-12
            composition = float(((wt - ws) * src.fpr).sum())
            within = float((wt * (tgt.fpr - src.fpr)).sum())
            difference = float((wt * tgt.fpr).sum() - (ws * src.fpr).sum())
            assert abs(difference - composition - within) < 1e-12
            audit[decomposition_name].append(dict(
                seed=int(seed), delta_udp_fpr=difference, composition=composition,
                within_rate_condition=within, within_share_of_delta=within/difference,
                composition_share_of_delta=composition/difference,
                within_by_condition={k: float(wt.loc[k] * (tgt.fpr.loc[k] - src.fpr.loc[k])) for k in conditions},
                composition_by_condition={k: float((wt.loc[k] - ws.loc[k]) * src.fpr.loc[k]) for k in conditions}))
        records = audit[decomposition_name]
        audit[decomposition_name + '_summary'] = {
            key: float(np.mean([r[key] for r in records]))
            for key in ['delta_udp_fpr', 'composition', 'within_rate_condition',
                        'within_share_of_delta', 'composition_share_of_delta']}
        audit[decomposition_name + '_summary']['ratio_of_mean_composition_to_mean_delta'] = (
            audit[decomposition_name + '_summary']['composition'] /
            audit[decomposition_name + '_summary']['delta_udp_fpr'])
    final_hashes = {str(p.relative_to(workspace)): sha256(p) for p in input_paths}
    assert input_hashes == final_hashes, 'An input artifact changed during analysis'
    audit['input_sha256'] = input_hashes
    audit['input_hashes_unchanged_after_analysis'] = True
    table.to_csv(workspace / 'results/posthoc_missingness.csv', index=False)
    (workspace / 'results/posthoc_missingness.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    lines = ['# Post-hoc nonfinite-rate association', '',
             'This exploratory analysis joins raw-valued byte-rate features to existing frozen XGBoost/F1 predictions. No model, preprocessing, or threshold is modified. The source population is benign calibration; the target population is benign test under P_capture. Decisions use strict `score > threshold`.', '',
             f'The two directional rate features have identical nonfinite masks over all raw rows: {audit["masks_equal_all_raw"]}. Nonfinite means NaN or either infinity. These values were median-imputed by the previously frozen preprocessing pipeline. The finer `source_rate_nan` and `source_rate_inf` strata describe original source-to-destination values; both are mapped to missing before imputation, so the distinction is not an explicit flag seen by the model.', '',
             '## Representative seed 42', '',
             '| Split | Rule | Protocol | Rate values | Benign n | False positives | FPR | Share of protocol false positives |',
             '|---|---|---|---|---:|---:|---:|---:|']
    selected = table.loc[table.seed.eq(42) & table.stratum.isin(['All', 'TCP', 'UDP'])]
    for r in selected.itertuples():
        share = f'{r.fp_share_in_stratum:.4%}' if np.isfinite(r.fp_share_in_stratum) else 'N/A'
        lines.append(f'| {r.split} | {r.rule} | {r.stratum} | {r.rate_condition} | {r.n_benign:,} | {r.false_positives:,} | {r.fpr:.4%} | {share} |')
    lines += ['', '## Across three seeds', '',
              'The full CSV includes all three seeds and All/TCP/UDP/ICMP/Other strata. Counts identify supports; zero false positives yield an undefined share, and empty strata yield an undefined FPR.', '',
              '| Target T1, protocol/rate condition | Benign n | FP range | FPR range |',
              '|---|---:|---:|---:|']
    for (stratum, condition), group in table.loc[table.split.eq('test') & table.rule.eq('T1_alpha_0.001') & table.stratum.isin(['All', 'TCP', 'UDP'])].groupby(['stratum', 'rate_condition']):
        assert group.n_benign.nunique() == 1
        lines.append(f'| {stratum} / {condition} | {group.n_benign.iloc[0]:,} | {group.false_positives.min():,}--{group.false_positives.max():,} | {group.fpr.min():.4%}--{group.fpr.max():.4%} |')
    lines += ['', '## Nested UDP standardization', '',
              'Apply the same descriptive composition/conditional-rate identity inside UDP, using finite versus nonfinite as the two exhaustive strata. There is support in both source strata. Values below are percentage points of UDP FPR, and this is an algebraic localization, not a causal decomposition.', '',
              '| Seed | UDP FPR change (pp) | Missingness-composition term (pp) | Within-rate-condition term (pp) | Within share |',
              '|---:|---:|---:|---:|---:|']
    for r in audit['udp_binary_missingness_decomposition']:
        lines.append(f'| {r["seed"]} | {100*r["delta_udp_fpr"]:.6f} | {100*r["composition"]:.6f} | {100*r["within_rate_condition"]:.6f} | {r["within_share_of_delta"]:.4%} |')
    lines += ['', 'A finer, still exploratory three-state partition (finite / original source-rate NaN / original source-rate infinity) yields a different allocation. The model transforms NaN and infinity identically before imputation; this partition is an external diagnostic and not a model input flag.', '',
              '| Seed | UDP FPR change (pp) | Original-rate-state composition (pp) | Within-state term (pp) | Composition share |',
              '|---:|---:|---:|---:|---:|']
    for r in audit['udp_original_rate_state_decomposition']:
        lines.append(f'| {r["seed"]} | {100*r["delta_udp_fpr"]:.6f} | {100*r["composition"]:.6f} | {100*r["within_rate_condition"]:.6f} | {r["composition_share_of_delta"]:.4%} |')
    lines += ['', 'The representative seed-42 result is concentrated in the original source-rate NaN subgroup: all 41 source-calibration UDP members and all 11,560 target UDP members exceed T1, whereas no target member of either the original-infinity or NaN subgroup exceeds T0. The NaN subgroup share increases from 0.0552% to 4.4550% of benign UDP. Its stable 100% T1 subgroup rate and expanded prevalence show why the broad protocol decomposition cannot by itself distinguish conditional change from changes in finer traffic composition. The finer allocation is taxonomy-dependent, uses a source NaN support of only 41, and was discovered after observing results; it is a localization hypothesis for independent validation, not a validated causal mechanism.', '',
              'Across seeds 42/2026/3407, T0 flags 0/58/64 members of the target UDP NaN subgroup, respectively, compared with 11,560/11,558/11,560 under T1. The three-state composition term averages 4.399818 percentage points of a 4.512930-point UDP FPR increase (97.4936% using the ratio of means).', '',
              'Validation: all protocol-level supports and false-positive counts agree exactly with the earlier saved decomposition files. SHA256 values for the dataset and each run\'s predictions, threshold file, pipeline, job, and earlier decomposition are recorded in the JSON and were identical before and after this script.']
    lines += ['', '## Interpretation boundary', '',
              'These are descriptive conditional rates, not an intervention on missingness or imputation. Protocol, traffic duration, byte counts, application mix, and other correlated attributes can account for an association. No iid significance test is applied to temporally dependent flows. The post-hoc subgroup result must not be used to retune the reported frozen thresholds. A causal imputation or missingness-feature sensitivity claim would require a separate experiment.']
    (workspace / 'reports/POSTHOC_MISSINGNESS.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(table.loc[table.seed.eq(42) & table.stratum.isin(['All', 'TCP', 'UDP'])].to_string(index=False))


if __name__ == '__main__':
    main()
