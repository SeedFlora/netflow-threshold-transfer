"""Required evaluation gates, including ties, support and paired resampling."""
import json
import hashlib

import numpy as np
import pandas as pd
import pytest

from nids_lab.decomposition import bootstrap_draws, fpr_decomposition
from nids_lab.common import hash_object
from nids_lab.evaluate import compare_feature_runs, evaluate_run
from nids_lab.metrics import binary_metrics, ranking_metrics, window_metrics
from nids_lab.reporting import pareto_mask, report_experiments
from nids_lab.thresholds import fit_thresholds, pooled_threshold, temporal_blocks


def frame(scores, labels=None, protocols=None, start=0, capture="A"):
    n = len(scores)
    labels = np.zeros(n, dtype=np.int8) if labels is None else labels
    return pd.DataFrame({"row_id": np.arange(start, start+n, dtype=np.int64), "score": scores,
                         "Label": labels, "Attack": ["Benign" if x == 0 else "Exploits" for x in labels],
                         "PROTOCOL": protocols if protocols is not None else np.full(n, 6),
                         "FLOW_START_MILLISECONDS": np.arange(start, start+n, dtype=np.int64)*1800000,
                         "capture": capture, "group_id": np.arange(start, start+n)})


@pytest.mark.parametrize("scores", [[.2]*1000, [0, 0, 0, .1, .1, .8, .8, 1], [0, .1, .2, .3, .4, .5]])
@pytest.mark.parametrize("alpha", [0, .001, .01, .2, .5])
def test_quantile_strict_ties_and_smallest_observed_candidate(scores, alpha):
    tau = pooled_threshold(scores, alpha)
    candidates = sorted(set(scores))
    feasible = [x for x in candidates if np.mean(np.asarray(scores) > x) <= alpha]
    assert tau == feasible[0]
    assert np.mean(np.asarray(scores) > tau) <= alpha


def test_thresholds_use_only_benign_and_blocks_satisfy_constraint():
    rng = np.random.default_rng(7)
    source = frame(rng.random(50000))
    source.loc[::3, "FLOW_START_MILLISECONDS"] = source.loc[::3, "FLOW_START_MILLISECONDS"]//2
    source.loc[0, "Label"] = 1
    source.loc[0, "score"] = 1e8
    thresholds = fit_thresholds(source)
    for entry in thresholds["entries"]:
        if entry["rule"] == "T0":
            continue
        assert entry["eligible"]
        assert entry["threshold"] < 1
        assert entry["source_fpr"] <= entry["alpha"]
        assert all(x <= entry["alpha"] for x in entry.get("block_fprs", []))


def test_blocks_do_not_split_ties_and_merge_deterministically():
    timestamps = np.repeat([1, 2, 3, 4, 5], [12000, 3000, 15000, 9000, 3000])
    first = temporal_blocks(timestamps)
    second = temporal_blocks(timestamps[::-1])
    assert [sorted(timestamps[x]) for x in first] == [sorted(timestamps[::-1][x]) for x in second]
    assert all(len(x) >= 10000 for x in first)
    supports = [set(timestamps[x]) for x in first]
    assert all(not a & b for i, a in enumerate(supports) for b in supports[i+1:])
    assert sum(len(x) for x in first) == len(timestamps)


def test_t2_ineligible_small_or_single_timestamp():
    for data in (frame([.1]*19999), frame([.1]*45000).assign(FLOW_START_MILLISECONDS=3)):
        result = fit_thresholds(data)
        assert all(not x["eligible"] and x["threshold"] is None for x in result["entries"] if x["rule"] == "T2")
    with pytest.raises(ValueError):
        fit_thresholds(frame([.1, .5], [1, 1]))


def test_fpr_denominator_one_class_and_no_predictions():
    m = binary_metrics([0, 0, 0, 1], [.1, .7, .8, .9], .5, .01)
    assert m["fpr"] == pytest.approx(2/3)
    assert m["false_alarms_per_10000_benign"] == pytest.approx(20000/3)
    none = binary_metrics([0, 0], [.2, .3], .5)
    assert none["precision"] is None and none["recall"] is None and none["fpr"] == 0
    assert ranking_metrics([0, 0], [.2, .3])["average_precision"] is None
    assert ranking_metrics([1, 1], [.2, .3])["roc_auc"] is None
    assert binary_metrics([1, 1], [.2, .3], .5)["fpr"] is None
    assert binary_metrics([0, 1], [.5, .5], .5)["tp"] == 0


def test_decomposition_missing_source_and_missing_target_support():
    source = frame([.9, .1, .1], protocols=[6, 6, 17])
    target = frame([.9, .9, .1, .8], protocols=[6, 1, 1, 99], capture="B")
    summary, table = fpr_decomposition(source, target, .5)
    assert summary["delta_fpr"] == pytest.approx(.75-1/3)
    assert sum(summary[x] for x in ("composition", "within_stratum", "unsupported_target")) == pytest.approx(summary["delta_fpr"])
    assert summary["unsupported_target"] == .5
    assert np.isnan(table.set_index("stratum").loc["ICMP", "source_fpr"])
    assert np.isnan(table.set_index("stratum").loc["UDP", "target_fpr"])
    assert table.set_index("stratum").loc["UDP", "within_stratum"] == 0


def test_decomposition_requires_benign_support():
    source = frame([.9], labels=[1])
    target = frame([.9])
    summary, _ = fpr_decomposition(source, target, .5)
    assert summary["delta_fpr"] is None
    assert summary["composition"] is None


def test_bootstrap_preserves_capture_blocks_and_is_paired():
    source = pd.concat([frame([.1, .8, .2], start=0), frame([.4, .6], start=10, capture="B")], ignore_index=True)
    target = frame([.2, .9, .6, .7], labels=[0, 0, 1, 1], start=20, capture="C")
    one, meta = bootstrap_draws(source, target, .5, n_resamples=40, seed=3)
    reordered, _ = bootstrap_draws(source.iloc[::-1], target.iloc[::-1], .5, n_resamples=40, seed=3)
    pd.testing.assert_frame_equal(one, reordered)
    assert meta["source_blocks_per_capture"] == {"A": 3, "B": 2}
    assert one["delta_recall"].isna().all()
    assert np.allclose(one["delta_fpr"], one[["composition", "within_stratum", "unsupported_target"]].sum(axis=1, min_count=3), equal_nan=True)
    windows = window_metrics(pd.concat([source, target]), .5)
    assert len(windows) == 9  # Empty weeks between captures are not manufactured.


def test_pareto_retains_zero_recall_and_excludes_missing_cost():
    values = pd.DataFrame({"recall": [0, .8, .7, .9], "fpr": [0, .01, .02, .03],
                           "inference_cost_seconds_per_flow": [.1, .2, .3, np.nan]})
    assert pareto_mask(values).tolist() == [True, True, False, False]


def test_evaluate_report_and_identical_row_feature_pairing(tmp_path):
    runs = []
    config = {"profile": "main", "evaluation": {"bootstrap_resamples": 20}}
    for feature in ("F0", "F1"):
        run = tmp_path / "runs" / feature
        run.mkdir(parents=True)
        source = frame([.1, .2, .3, .4]).assign(split="calibration")
        target = frame([.1, .6, .2, .9, .3, .8], [0, 0, 0, 1, 1, 1], start=10, capture="B").assign(split="test")
        pd.concat([source, target]).to_parquet(run / "predictions.parquet", index=False)
        (run / "metadata.json").write_text(json.dumps({"profile": "main", "feature_set": feature, "protocol": "P_capture", "model": "LR", "seed": 42, "split_hash": "abc", "config_hash": hash_object(config), "training_rows_hash": "matching-training-fixture"}))
        (run / "status.json").write_text(json.dumps({"status": "completed"}))
        (run / "profiling.json").write_text(json.dumps({"inference_end_to_end_seconds_per_flow": .001, "inference_device": "cpu", "inference_batch_size": 1024}))
        result = evaluate_run(run, config)
        assert result["ranking"]["calibration"]["average_precision"] is None
        assert (run / "decomposition.csv").exists()
        runs.append(run)
    paired = compare_feature_runs(*runs)
    assert paired.loc[paired["metric"].eq("test_fpr"), "estimate"].eq(0).all()
    assert paired.loc[paired["metric"].eq("test_recall"), "lower_95"].eq(0).all()
    report = report_experiments(config, tmp_path)
    assert report["evaluated_runs"] == 2 and not report["pairing_errors"]
    assert (tmp_path / "figures" / "main_recall_fpr.png").exists()
    changed = json.loads((runs[1] / "metrics.json").read_text())
    changed["row_signatures"]["test"] = "different"
    (runs[1] / "metrics.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="identical"):
        compare_feature_runs(*runs)
    with pytest.raises(ValueError, match="config hash"):
        evaluate_run(runs[0], {**config, "profile": "altered"})
    metadata_path = runs[0] / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["thresholds_hash_before_test_prediction"] = hashlib.sha256((runs[0] / "thresholds.json").read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(metadata))
    with (runs[0] / "thresholds.json").open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="pre-test freeze"):
        evaluate_run(runs[0], config)


def test_bootstrap_does_not_change_original_source_support():
    source = frame([.1, .8], protocols=[6, 17])
    target = frame([.2, .9], protocols=[6, 17], start=10, capture="B")
    draws, meta = bootstrap_draws(source, target, .5, n_resamples=100, seed=8)
    valid_components = draws["composition"].notna()
    assert 0 < valid_components.sum() < 100
    assert draws["delta_fpr"].notna().all()
    assert meta["resamples_preserving_source_stratum_support"] == int(valid_components.sum())
    assert np.allclose(draws.loc[valid_components, "delta_fpr"], draws.loc[valid_components, ["composition", "within_stratum", "unsupported_target"]].sum(axis=1))
