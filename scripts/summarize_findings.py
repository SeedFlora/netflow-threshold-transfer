"""Compact measured findings and cost table, derived from completed main runs."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from nids_lab.common import write_json


def summarize(workspace=Path('.')):
    workspace = Path(workspace)
    metrics = pd.read_csv(workspace / 'results/main_metrics.csv')
    core = metrics.loc[metrics.protocol.eq('P_capture') & metrics.model.isin(['lr', 'xgboost']) & metrics.rule.isin(['T1', 'T2'])].copy()
    core['violates_budget'] = core.fpr > core.alpha
    pairs = core.loc[core.rule.eq('T2')].merge(core.loc[core.rule.eq('T1')],
               on=['model', 'feature_set', 'seed', 'alpha'], suffixes=('_T2', '_T1'))
    base = metrics.loc[metrics.rule.eq('T0')].copy()
    costs = base.groupby(['protocol', 'model', 'feature_set'])[[
        'training_wall_seconds', 'preprocessing_fit_seconds', 'inference_model_only_seconds_per_flow',
        'inference_end_to_end_seconds_per_flow', 'inference_throughput_flows_per_second',
        'peak_process_tree_rss_bytes', 'peak_gpu_device_used_mb', 'artifact_bytes']].agg(['mean', 'std', 'min', 'max'])
    costs.columns = ['_'.join(x) for x in costs.columns]
    costs.reset_index().to_csv(workspace / 'results/main_cost_summary.csv', index=False)
    candidates = [
        directory for directory in (workspace / 'runs').glob('main_P_capture_xgboost_F1_42_*')
        if (directory / 'status.json').is_file()
        and json.loads((directory / 'status.json').read_text(encoding='utf-8')).get('status') == 'completed'
    ]
    if len(candidates) != 1:
        raise RuntimeError(f'Expected one completed main P_capture XGBoost/F1 seed-42 run, found {candidates}')
    representative = candidates[0]
    bootstrap = pd.read_csv(representative / 'bootstrap.csv')
    decomposition = pd.read_csv(representative / 'decomposition.csv')
    windows = pd.read_csv(representative / 'windows.csv')
    report = {
        'representative_seed_note': 'Seed 42 is an illustration; all three seeds are reported and none was selected for model decisions.',
        'core_capture_budget_violations': int(core.violates_budget.sum()),
        'core_capture_operating_points': len(core),
        'violations_by_rule_alpha': core.groupby(['rule', 'alpha']).violates_budget.agg(['sum', 'count']).reset_index().to_dict('records'),
        'T2_pairs': len(pairs), 'T2_threshold_identical_to_T1': int(pairs.threshold_T1.eq(pairs.threshold_T2).sum()),
        'T2_target_fpr_reduced_pairs': int(pairs.fpr_T2.lt(pairs.fpr_T1).sum()),
        'T2_max_recall_loss': float((pairs.recall_T1-pairs.recall_T2).max()),
        'max_sampled_process_tree_rss_bytes': int(base.peak_process_tree_rss_bytes.max()),
        'max_sampled_gpu_device_used_mb': float(base.peak_gpu_device_used_mb.max()),
        'total_main_worker_seconds': sum(json.loads(p.read_text())['parent_measured_wall_seconds'] for p in (workspace / 'runs').glob('main*/profiling.json')),
        'training_warnings': {p.parent.name: json.loads(p.read_text())['warnings'] for p in (workspace / 'runs').glob('main*/profiling.json') if json.loads(p.read_text())['warnings']},
        'representative_xgb_F1_T1_0_001_intervals': bootstrap.loc[bootstrap.threshold_id.eq('T1_alpha_0.001')].to_dict('records'),
        'representative_protocol_decomposition': decomposition.loc[decomposition.threshold_id.eq('T1_alpha_0.001')].to_dict('records'),
        'representative_window_min_benign': int(windows.loc[windows.split.eq('test')].n_benign.min()),
        'random_T1_0_001_mean': metrics.loc[metrics.protocol.eq('P_random') & metrics.rule.eq('T1') & np.isclose(metrics.alpha, .001)].groupby(['model', 'feature_set'])[['fpr', 'recall', 'average_precision']].mean().reset_index().to_dict('records')}
    write_json(workspace / 'results/findings_summary.json', report)
    print(json.dumps({k: v for k, v in report.items() if not k.startswith('representative_')}, indent=2))


if __name__ == '__main__':
    summarize()
