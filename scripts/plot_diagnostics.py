"""Static diagnostic figures from completed frozen evaluation artifacts."""
from pathlib import Path
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot(workspace=Path('.')):
    workspace = Path(workspace)
    output = workspace / 'figures'
    summary = pd.read_csv(workspace / 'results/main_seed_summary.csv')
    capture = summary.loc[summary.protocol.eq('P_capture') & summary.model.isin(['lr', 'xgboost'])]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharey=True)
    colors = ['#365b88', '#d38139', '#6c9981']
    fields = ['composition_mean', 'within_stratum_mean', 'unsupported_target_mean']
    labels = ['Protocol composition', 'Within protocol', 'Unsupported target']
    for r, rule in enumerate(['T1', 'T2']):
        for c, alpha in enumerate([.001, .01]):
            ax = axes[r, c]
            part = capture.loc[capture.rule.eq(rule) & np.isclose(capture.alpha, alpha)].sort_values(['model', 'feature_set'])
            x = np.arange(len(part))
            positive = np.zeros(len(part))
            negative = np.zeros(len(part))
            for field, color, label in zip(fields, colors, labels):
                values = part[field].to_numpy() * 100
                bases = np.where(values >= 0, positive, negative)
                ax.bar(x, values, bottom=bases, color=color, label=label)
                positive += np.maximum(values, 0)
                negative += np.minimum(values, 0)
            ax.scatter(x, part.delta_fpr_mean * 100, marker='D', color='#171717', s=25, zorder=4, label='Total change')
            ax.axhline(0, color='#555555', linewidth=.6)
            ax.set_xticks(x, part.model.str.upper() + '/' + part.feature_set)
            ax.set_title(f'{rule}: source FPR budget {alpha:.1%}')
            if c == 0:
                ax.set_ylabel('Delta FPR (percentage points)')
            ax.grid(axis='y', alpha=.18)
    handles, legends = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, legends, loc='lower center', ncol=4, frameon=False)
    fig.suptitle('January to February: descriptive false-alarm decomposition\nMean across three seeds; signed components, not causal attribution', fontsize=13)
    fig.tight_layout(rect=[0, .07, 1, .93])
    fig.savefig(output / 'main_decomposition.png', dpi=180)
    fig.savefig(output / 'main_decomposition.svg')
    plt.close(fig)

    # Seed 42 fixed as a representative illustration, not selected by score.
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharey=True)
    for directory in sorted((workspace / 'runs').glob('main_P_capture_*_42_*')):
        meta = json.loads((directory / 'metadata.json').read_text())
        if meta['model'] not in ['lr', 'xgboost']:
            continue
        rows = pd.read_csv(directory / 'windows.csv')
        rows = rows.loc[rows.threshold_id.eq('T1_alpha_0.001')]
        for c, split in enumerate(['calibration', 'test']):
            data = rows.loc[rows.split.eq(split)].sort_values('window_start_ms')
            ax = axes[['lr', 'xgboost'].index(meta['model']), c]
            ax.plot(np.arange(len(data)), data.fpr*100, '.-', label=meta['feature_set'])
            ax.set_title(f"{meta['model'].upper()}: {'January calibration' if split == 'calibration' else 'February test'}")
            ax.set_xlabel('Consecutive observed 30-minute windows')
            ax.set_ylabel('Benign FPR (%)')
            ax.grid(alpha=.18)
            if meta['feature_set'] == 'F0' and (data.n_benign < 1000).any():
                small = data.loc[data.n_benign < 1000]
                ax.text(.98, .95, f"Smallest window: {int(small.n_benign.min())} benign flows",
                        transform=ax.transAxes, ha='right', va='top', fontsize=9,
                        bbox=dict(facecolor='white', edgecolor='none', alpha=.8))
    for ax in axes.flat:
        ax.axhline(.1, color='#666666', linestyle=':', label='0.1% budget')
        ax.set_yscale('symlog', linthresh=.03)
        ax.set_ylim(0, 110)
        ax.legend(frameon=False)
    fig.suptitle('Frozen pooled threshold, alpha = 0.001, seed 42\nWindows vary in benign support; no claim of independent flow observations', fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, .93])
    fig.savefig(output / 'main_window_fpr.png', dpi=180)
    fig.savefig(output / 'main_window_fpr.svg')
    plt.close(fig)
    print('Saved decomposition and window-FPR figures (PNG and SVG).')


if __name__ == '__main__':
    plot()
