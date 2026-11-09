"""Verify all frozen main artifacts; no fitting or parameter selection."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from nids_lab.common import hash_file, hash_object, load_config, write_json
from nids_lab.runner import completed_run, experiment_identity, run_id, run_specs


def verify(workspace=Path('.')):
    workspace = Path(workspace).resolve()
    config = load_config(workspace / 'configs/main.yaml')
    identity = experiment_identity(config, workspace)
    frozen = json.loads((workspace / 'manifests/main_preregistered_experiment_plan.json').read_text())
    assert identity == frozen['identity'], 'Frozen plan identity changed'
    manifest = pd.read_parquet(workspace / 'manifests/split_manifest.parquet')
    records = []
    for spec in run_specs(config):
        directory = workspace / 'runs' / run_id(config, spec, identity)
        assert completed_run(directory, identity), f'Incomplete run: {directory.name}'
        meta = json.loads((directory / 'metadata.json').read_text())
        profile = json.loads((directory / 'profiling.json').read_text())
        thresholds = json.loads((directory / 'thresholds.json').read_text())
        assert hash_file(directory / 'thresholds.json') == meta['thresholds_hash_before_test_prediction']
        assert meta['training_rows'] == 200000
        assert meta['serialization_prediction_check']
        assert meta['raw_feature_count'] == (40 if spec['feature_set'] == 'F0' else 48)
        assert profile['inference_device'] == 'cpu' and profile['inference_batch_size'] == 4096
        fit_ids = pd.read_parquet(directory / 'fit_rows.parquet').row_id.to_numpy()
        assert hash_file(directory / 'fit_rows.parquet') == meta['training_rows_hash']
        source_train = manifest.loc[manifest[spec['protocol']].eq('train'), 'row_id'].to_numpy()
        assert np.isin(fit_ids, source_train).all()
        pred = pd.read_parquet(directory / 'predictions.parquet', columns=['row_id', 'split', 'Label', 'score'])
        assert not pred.row_id.duplicated().any()
        assert np.isfinite(pred.score).all()
        for split in ['calibration', 'test']:
            expected = manifest.loc[manifest[spec['protocol']].eq(split), ['row_id', 'Label']].sort_values('row_id')
            actual = pred.loc[pred.split.eq(split), ['row_id', 'Label']].sort_values('row_id')
            assert np.array_equal(expected.to_numpy(), actual.to_numpy()), f'Population mismatch: {directory.name}/{split}'
        calibration = pred.loc[pred.split.eq('calibration') & pred.Label.eq(0), 'score']
        for entry in thresholds['entries']:
            if entry['eligible'] and entry['alpha'] is not None:
                assert (calibration > entry['threshold']).mean() <= entry['alpha'] + 1e-12
        records.append({'run_id': directory.name, 'verified': True, 'training_warnings': profile['warnings'],
                        'test_rows': meta['test_rows'], 'encoded_feature_count': profile['encoded_feature_count'],
                        'training_device': profile['actual_training_device'],
                        'prediction_sha256': hash_file(directory / 'predictions.parquet'),
                        'pipeline_sha256': hash_file(directory / 'pipeline.joblib')})
    result = {'expected_main_runs': len(records), 'verified_main_runs': len(records),
              'all_complete': True, 'frozen_identity': identity, 'runs': records,
              'checks': ['frozen config/split/dataset/training-code hash', 'artifact completion',
                         'threshold pre-test hash', 'strict source FPR constraints', 'full matching evaluation rows and labels',
                         'finite scores', 'training subset membership', '200000 training rows',
                         '40/48 raw features', 'serialization check', 'common CPU inference batch',
                         'identical training-row artifact hash']}
    write_json(workspace / 'results/quality_gates.json', result)
    return {'verified_main_runs': len(records), 'warnings': sum(bool(x['training_warnings']) for x in records)}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
