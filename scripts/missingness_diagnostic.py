"""Post-freeze descriptive audit of nonfinite rate features; no model changes."""
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from nids_lab.decomposition import protocol_strata


def diagnostic(workspace=Path('.')):
    workspace = Path(workspace)
    features = ['SRC_TO_DST_SECOND_BYTES', 'DST_TO_SRC_SECOND_BYTES']
    totals = defaultdict(lambda: np.zeros(4, dtype=np.int64))
    cols = features + ['capture', 'PROTOCOL', 'Label', 'integrity_reason']
    for batch in pq.ParquetFile(workspace / 'data/processed/dataset.parquet').iter_batches(batch_size=100000, columns=cols):
        frame = batch.to_pandas()
        frame = frame.loc[frame.integrity_reason.eq('')].copy()
        frame['stratum'] = protocol_strata(frame.PROTOCOL)
        for (capture, stratum, label), group in frame.groupby(['capture', 'stratum', 'Label'], observed=True):
            for feature in features:
                values = group[feature].to_numpy()
                totals[capture, stratum, label, feature] += [len(values), np.isnan(values).sum(), np.isinf(values).sum(), (~np.isfinite(values)).sum()]
    rows = []
    for (capture, stratum, label, feature), (n, missing, inf, invalid) in sorted(totals.items()):
        rows.append(dict(capture=capture, stratum=stratum, Label=label, feature=feature,
                         n=int(n), missing=int(missing), inf=int(inf), nonfinite=int(invalid), nonfinite_fraction=invalid/n))
    table = pd.DataFrame(rows)
    table.to_csv(workspace / 'results/missingness_by_capture_protocol.csv', index=False)
    overall = table.groupby(['capture', 'feature'])[['n', 'missing', 'inf', 'nonfinite']].sum().reset_index()
    text = ['# Post-freeze missingness diagnostic', '',
            'Exploratory descriptive analysis performed after the model/split plan was frozen. It did not change preprocessing, features, models or thresholds.', '',
            'Population: integrity-valid flows, before the P_capture temporal purge. Source/target labels are descriptive strata here, never calibration inputs from the target.', '',
            '| Capture | Feature | Flows | NaN | Inf | Nonfinite fraction |', '|---|---|---:|---:|---:|---:|']
    for row in overall.itertuples():
        text.append(f'| {row.capture} | {row.feature} | {row.n:,} | {row.missing:,} | {row.inf:,} | {row.nonfinite/row.n:.4%} |')
    text += ['', 'Detailed benign/attack and TCP/UDP/ICMP/Other counts: `results/missingness_by_capture_protocol.csv`.', '',
             'Nonfinite values are replaced with NaN, then imputed using training medians within each saved pipeline. A capture-dependent missingness pattern is a potential environment proxy; this audit does not establish its causal effect on false alarms. A missingness-feature sensitivity study would be a separate follow-up experiment.']
    (workspace / 'reports/MISSINGNESS_DIAGNOSTIC.md').write_text('\n'.join(text)+'\n', encoding='utf-8')
    print(overall.to_string(index=False))


if __name__ == '__main__':
    diagnostic()
