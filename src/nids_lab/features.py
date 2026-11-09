"""Frozen raw-feature schema and training-only preprocessing."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

IAT_FEATURES = [f"{direction}_IAT_{statistic}" for direction in ("SRC_TO_DST", "DST_TO_SRC")
                for statistic in ("MIN", "MAX", "AVG", "STDDEV")]
EXCLUDED_FEATURES = {"Label", "Attack", "FLOW_START_MILLISECONDS", "FLOW_END_MILLISECONDS",
                     "IPV4_SRC_ADDR", "IPV4_DST_ADDR", "DNS_QUERY_ID"}
RAW_FEATURES = ["L4_SRC_PORT", "L4_DST_PORT", "PROTOCOL", "L7_PROTO", "IN_BYTES", "IN_PKTS",
                "OUT_BYTES", "OUT_PKTS", "TCP_FLAGS", "CLIENT_TCP_FLAGS", "SERVER_TCP_FLAGS",
                "FLOW_DURATION_MILLISECONDS", "DURATION_IN", "DURATION_OUT", "MIN_TTL", "MAX_TTL",
                "LONGEST_FLOW_PKT", "SHORTEST_FLOW_PKT", "MIN_IP_PKT_LEN", "MAX_IP_PKT_LEN",
                "SRC_TO_DST_SECOND_BYTES", "DST_TO_SRC_SECOND_BYTES", "RETRANSMITTED_IN_BYTES",
                "RETRANSMITTED_IN_PKTS", "RETRANSMITTED_OUT_BYTES", "RETRANSMITTED_OUT_PKTS",
                "SRC_TO_DST_AVG_THROUGHPUT", "DST_TO_SRC_AVG_THROUGHPUT", "NUM_PKTS_UP_TO_128_BYTES",
                "NUM_PKTS_128_TO_256_BYTES", "NUM_PKTS_256_TO_512_BYTES", "NUM_PKTS_512_TO_1024_BYTES",
                "NUM_PKTS_1024_TO_1514_BYTES", "TCP_WIN_MAX_IN", "TCP_WIN_MAX_OUT", "ICMP_TYPE",
                "ICMP_IPV4_TYPE", "DNS_QUERY_TYPE", "DNS_TTL_ANSWER", "FTP_COMMAND_RET_CODE"] + IAT_FEATURES


def feature_columns(frame_or_columns, feature_set: str = "F1") -> list[str]:
    columns = list(frame_or_columns.columns if hasattr(frame_or_columns, "columns") else frame_or_columns)
    if feature_set not in {"F0", "F1", "F2"}:
        raise ValueError(f"Unknown feature set: {feature_set}")
    missing = set(RAW_FEATURES) - set(columns)
    if missing:
        raise ValueError(f"Dataset raw schema missing: {sorted(missing)}")
    selected = [column for column in RAW_FEATURES if feature_set != "F0" or column not in IAT_FEATURES]
    if feature_set == "F2":
        selected = [c for c in selected if c not in {"L4_SRC_PORT", "L4_DST_PORT", "MIN_TTL", "MAX_TTL", "TCP_WIN_MAX_IN", "TCP_WIN_MAX_OUT"}]
    expected = {"F0": 40, "F1": 48, "F2": 42}[feature_set]
    if len(selected) != expected:
        raise AssertionError(f"{feature_set} has {len(selected)} raw features, expected {expected}")
    return selected


def _finite_frame(frame, columns=None):
    if isinstance(frame, pd.DataFrame):
        if columns is not None:
            frame = frame.loc[:, columns]
        return frame.replace([np.inf, -np.inf], np.nan).astype(np.float32)
    values = np.asarray(frame, dtype=np.float32).copy()
    values[~np.isfinite(values)] = np.nan
    return values


def _float32(values):
    return np.asarray(values, dtype=np.float32)


def _selected_names(transformer, input_features=None):
    return np.asarray(transformer.kw_args["columns"], dtype=object)


def _signed_log1p(values):
    values = np.asarray(values, dtype=np.float32)
    return np.sign(values) * np.log1p(np.abs(values))


def make_preprocessor(feature_cols: list[str]) -> Pipeline:
    """Return an unfitted, serializable transformer. Ports remain scaled numeric.

    Protocols are nominal; unknown categories map to an all-zero encoded block.
    Every learned statistic (median, scale, categories) is fitted on train only.
    """
    if not set(feature_cols).issubset(RAW_FEATURES):
        raise ValueError("Predictor list contains forbidden metadata or unknown features")
    categories = [c for c in ("PROTOCOL", "L7_PROTO") if c in feature_cols]
    numeric = [c for c in feature_cols if c not in categories]
    numeric_pipe = Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                             ("log1p", FunctionTransformer(_signed_log1p, feature_names_out="one-to-one")),
                             ("scale", StandardScaler())])
    category_pipe = Pipeline([("impute", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
                              ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float32))])
    columns = ColumnTransformer([("numeric", numeric_pipe, numeric), ("categorical", category_pipe, categories)],
                                remainder="drop", sparse_threshold=0, verbose_feature_names_out=True)
    return Pipeline([("finite", FunctionTransformer(_finite_frame, validate=False, kw_args={"columns":list(feature_cols)}, feature_names_out=_selected_names)),
                     ("columns", columns), ("float32", FunctionTransformer(_float32, feature_names_out="one-to-one"))])
