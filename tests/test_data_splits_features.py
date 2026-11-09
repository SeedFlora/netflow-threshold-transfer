import pickle
from pathlib import Path
import stat
import zipfile

import numpy as np
import pandas as pd
import pytest

from nids_lab.data import START, END
from nids_lab.features import RAW_FEATURES, IAT_FEATURES, feature_columns, make_preprocessor
from nids_lab.splits import build_split_manifest, sessionize, stable_hash, verify_manifest


def frame_for_splits(n=500):
    starts = 1_000_000 + np.arange(n, dtype=np.int64) * 10_000
    capture = np.where(np.arange(n) < int(.6*n), "A", "B")
    starts[capture == "B"] += 100_000_000
    labels = (np.arange(n) % 10 == 0).astype(np.int64)
    return pd.DataFrame({"row_id":np.arange(n,dtype=np.int64), "group_id":np.arange(n,dtype=np.uint64),
                         "event_hash":np.arange(n,dtype=np.uint64), "capture":capture,
                         START:starts, END:starts+100, "Label":labels,
                         "Attack":np.where(labels,"Exploits","Benign"), "integrity_reason":""})


def test_raw_feature_allowlist_counts_and_order():
    columns = ["Label","Attack","FLOW_START_MILLISECONDS","FLOW_END_MILLISECONDS","IPV4_SRC_ADDR",
               "IPV4_DST_ADDR","DNS_QUERY_ID","row_id","group_id","capture","P_capture","source_filename"] + RAW_FEATURES
    assert feature_columns(columns,"F1") == RAW_FEATURES
    assert len(feature_columns(columns,"F0")) == 40
    assert len(feature_columns(columns,"F1")) == 48
    assert not set(IAT_FEATURES) & set(feature_columns(columns,"F0"))
    assert feature_columns(columns[::-1],"F1") == RAW_FEATURES
    assert "FLOW_DURATION_MILLISECONDS" in feature_columns(columns,"F0")
    with pytest.raises(ValueError, match="missing"):
        feature_columns(RAW_FEATURES[:-1],"F1")


def test_preprocessor_training_statistics_unknown_categories_and_serialization():
    train = pd.DataFrame({"IN_BYTES":[0.,10.,np.nan,30.], "PROTOCOL":[6.,6.,17.,17.], "L7_PROTO":[5.,5.,7.,7.]})
    model = make_preprocessor(list(train.columns))
    train_result = model.fit_transform(train)
    numeric = model.named_steps["columns"].named_transformers_["numeric"]
    assert numeric.named_steps["impute"].statistics_[0] == 10
    previous_mean = numeric.named_steps["scale"].mean_.copy()
    target = pd.DataFrame({"IN_BYTES":[np.inf,1e9],"PROTOCOL":[250.,6.],"L7_PROTO":[99.,5.]})
    result = model.transform(target)
    assert result.shape[1] == train_result.shape[1]
    assert np.isfinite(result).all()
    assert result.dtype == np.float32
    np.testing.assert_array_equal(numeric.named_steps["scale"].mean_,previous_mean)
    np.testing.assert_allclose(result[0,1:],0)  # Both protocol categories unknown.
    restored = pickle.loads(pickle.dumps(model))
    np.testing.assert_array_equal(restored.transform(target),result)
    np.testing.assert_array_equal(model.transform(target[list(target.columns)[::-1]]),result)
    with pytest.raises(ValueError,match="forbidden"):
        make_preprocessor(["Label"])


def test_sessionization_bidirectional_and_running_interval_end():
    # The long first interval keeps short nested flows in one session. The
    # fourth starts 60,001ms beyond the running interval end and is separate.
    frame = pd.DataFrame({"IPV4_SRC_ADDR":["a","b","a","a"], "IPV4_DST_ADDR":["b","a","b","b"],
                          "L4_SRC_PORT":[1,2,1,1],"L4_DST_PORT":[2,1,2,2],"PROTOCOL":[6]*4,
                          START:[0,10_000,100_000,160_001],END:[100_000,10_100,100_000,160_100],
                          "row_id":np.arange(4,dtype=np.int64)})
    ids = sessionize(frame)
    assert ids[0] == ids[1] == ids[2]
    assert ids[3] != ids[2]
    reordered = frame.iloc[[3,1,0,2]]
    result = sessionize(reordered)
    np.testing.assert_array_equal(result,ids[[3,1,0,2]])


def test_event_hash_stable_across_index_and_rebatching():
    frame = pd.DataFrame({"time":np.array([1420000000000,1420000000001],dtype=np.int64),"ip":["a","b"],"value":[0.,1.]})
    np.testing.assert_array_equal(stable_hash(frame),np.concatenate([stable_hash(frame.iloc[:1]),stable_hash(frame.iloc[1:])]))
    reindexed = frame.copy()
    reindexed.index = [100,200]
    np.testing.assert_array_equal(stable_hash(frame),stable_hash(reindexed))


def test_capture_purge_full_crossing_group_temporal_ties_and_integrity():
    frame = frame_for_splits()
    # Include an early and late source flow in one session so every member
    # must be removed even when its own interval is outside the embargo.
    frame.loc[205,"group_id"] = frame.loc[0,"group_id"]
    frame.loc[205,END] = frame.loc[220,START]
    frame.loc[211,START] = frame.loc[210,START]  # timestamp tie at cutoff
    frame.loc[5,"integrity_reason"] = "duplicate_event"
    result,report = build_split_manifest(frame,{"split_seed":42})
    cutoff = report["cutoff_epoch_milliseconds"]
    assert result.loc[0,"P_capture"] == "excluded"
    assert result.loc[205,"P_capture"] == "excluded"
    assert result.loc[5,["P_capture","P_random"]].eq("excluded").all()
    assert result.loc[210,"P_capture"] == result.loc[211,"P_capture"]
    source = result.P_capture.isin(["train","development"])
    calibration = result.P_capture.eq("calibration")
    assert frame.loc[source,END].lt(cutoff-60_000).all()
    assert frame.loc[calibration,START].gt(cutoff+60_000).all()
    assert result.loc[result.capture.eq("B"),"P_capture"].eq("test").all()
    verify_manifest(result,cutoff)
    again,_ = build_split_manifest(frame,{"split_seed":42})
    pd.testing.assert_frame_equal(again,result)


def test_session_and_event_overlap_are_rejected():
    frame = frame_for_splits()
    manifest,_ = build_split_manifest(frame,{"split_seed":42})
    train_id = manifest.index[manifest.P_random.eq("train")][0]
    test_id = manifest.index[manifest.P_random.eq("test")][0]
    for identifier in ("event_hash","group_id"):
        corrupted = manifest.copy()
        corrupted.loc[test_id,identifier] = corrupted.loc[train_id,identifier]
        with pytest.raises(AssertionError,match="overlaps"):
            verify_manifest(corrupted)


@pytest.mark.parametrize("member_name,symlink",[("../escape.csv",False),("C:/escape.csv",False),("data/link",True)])
def test_unsafe_zip_members_rejected_before_extraction(tmp_path,monkeypatch,member_name,symlink):
    from nids_lab import data
    archive_path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive_path,"w") as archive:
        member = zipfile.ZipInfo(member_name)
        if symlink:
            member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member,"../outside")
    monkeypatch.setattr(data,"EXPECTED_ZIP_SHA256",data.file_hash(archive_path))
    with pytest.raises(ValueError,match="Unsafe archive"):
        data.resolve_dataset(archive_path,tmp_path)
    assert not (tmp_path.parent / "escape.csv").exists()
