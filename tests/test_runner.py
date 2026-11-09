import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nids_lab.common import hash_object, write_json
from nids_lab.runner import completed_run, read_selected, run_id, run_specs, sampled_training_ids


def test_main_plan_has_24_core_and_six_support_runs():
    from nids_lab.common import load_config
    config = load_config(Path(__file__).parents[1] / "configs/main.yaml")
    specs = run_specs(config)
    assert len([s for s in specs if s["model"] in ["lr", "xgboost"]]) == 24
    assert len(specs) == 30


def test_training_sample_only_train_stratified_reused_features():
    frame = pd.DataFrame({"row_id": range(200), "Label": [0, 1] * 100,
                          "Attack": ["Benign", "Exploits"] * 100,
                          "P_capture": ["train"] * 160 + ["test"] * 40})
    ids = sampled_training_ids(frame, "P_capture", 50, 42)
    assert len(ids) == 50
    assert ids.max() < 160
    assert frame.set_index("row_id").loc[ids, "Label"].sum() == 25
    assert np.array_equal(ids, sampled_training_ids(frame, "P_capture", 50, 42))
    assert not np.array_equal(ids, sampled_training_ids(frame, "P_capture", 50, 2026))


def test_resume_rejects_config_and_split_mismatch(tmp_path):
    identity = {"config_hash": "a", "split_hash": "b"}
    write_json(tmp_path / "metadata.json", identity)
    write_json(tmp_path / "status.json", {"status": "completed"})
    for name in ["pipeline.joblib", "predictions.parquet", "thresholds.json"]:
        (tmp_path / name).touch()
    assert completed_run(tmp_path, identity)
    assert not completed_run(tmp_path, {**identity, "config_hash": "different"})
    assert not completed_run(tmp_path, {**identity, "split_hash": "different"})
    (tmp_path / "pipeline.joblib").unlink()
    assert not completed_run(tmp_path, identity)


def test_read_selected_chunked_preserves_exact_manifest_rows(tmp_path):
    path = tmp_path / "data.parquet"
    pd.DataFrame({"row_id": [3, 0, 8, 1], "value": [30, 0, 80, 10]}).to_parquet(path)
    out = read_selected(path, np.array([8, 0]), ["value"], chunk_size=2)
    assert out.row_id.tolist() == [0, 8]
    assert out.value.tolist() == [0, 80]
    with pytest.raises(RuntimeError):
        read_selected(path, np.array([0, 7]), ["value"], chunk_size=2)
