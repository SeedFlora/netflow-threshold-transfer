from __future__ import annotations

import json
import time
import warnings

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits
from xgboost import XGBClassifier

from .features import make_preprocessor


def cuda_smoke(threads=4):
    """Check actual booster device, not just successful fit (which can fall back)."""
    rng = np.random.default_rng(812)
    x = rng.normal(size=(256, 6)).astype(np.float32)
    y = (x[:, 0] > 0).astype(int)
    try:
        with warnings.catch_warnings(record=True) as caught:
            model = XGBClassifier(n_estimators=2, max_depth=2, tree_method="hist", device="cuda", n_jobs=threads)
            model.fit(x, y)
        actual = json.loads(model.get_booster().save_config())["learner"]["generic_param"]["device"]
        return {"requested": "cuda", "actual": actual, "usable": actual.startswith("cuda"),
                "warnings": [str(item.message) for item in caught]}
    except Exception as error:
        return {"requested": "cuda", "actual": "cpu", "usable": False, "reason": repr(error)}


def fit_model(model_name, feature_cols, training, development, config, seed, device):
    threads = int(config.get("cpu_threads", 4))
    preprocessing = make_preprocessor(feature_cols)
    start = time.perf_counter()
    with threadpool_limits(limits=threads):
        x_train = preprocessing.fit_transform(training[feature_cols])
        x_dev = preprocessing.transform(development[feature_cols])
    preprocessing_seconds = time.perf_counter() - start
    y_train = training.Label.to_numpy(dtype=int)
    y_dev = development.Label.to_numpy(dtype=int)
    if len(np.unique(y_train)) != 2 and model_name != "dummy":
        raise ValueError("Training must contain both classes")
    if model_name == "lr":
        model = LogisticRegression(solver="lbfgs", random_state=seed, **config.get("lr", {}))
    elif model_name == "xgboost":
        model = XGBClassifier(tree_method="hist", device=device, objective="binary:logistic",
                              eval_metric="logloss", random_state=seed, n_jobs=threads,
                              **config.get("xgboost", {}))
    elif model_name == "rf":
        model = RandomForestClassifier(random_state=seed, n_jobs=threads, **config.get("rf", {}))
    elif model_name == "dummy":
        model = DummyClassifier(strategy="most_frequent", random_state=seed)
    else:
        raise ValueError(model_name)
    fit_start = time.perf_counter()
    fallback_reason = None
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=threads):
        warnings.simplefilter("always")
        if model_name == "xgboost":
            try:
                model.fit(x_train, y_train, eval_set=[(x_dev, y_dev)], verbose=False)
            except Exception as error:
                if not str(device).startswith("cuda"):
                    raise
                fallback_reason = repr(error)
                model.set_params(device="cpu")
                model.fit(x_train, y_train, eval_set=[(x_dev, y_dev)], verbose=False)
        else:
            model.fit(x_train, y_train)
    fit_seconds = time.perf_counter() - fit_start
    actual = "cpu"
    best_iteration = None
    if model_name == "xgboost":
        actual = json.loads(model.get_booster().save_config())["learner"]["generic_param"]["device"]
        best_iteration = int(model.best_iteration)
        # CPU inference for all models provides the same device and batch comparison.
        model.set_params(device="cpu")
    pipeline = Pipeline([("preprocessing", preprocessing), ("model", model)])
    profiling = {"training_wall_seconds": fit_seconds, "preprocessing_fit_seconds": preprocessing_seconds,
                 "encoded_feature_count": x_train.shape[1], "actual_training_device": actual,
                 "inference_device": "cpu", "fallback_reason": fallback_reason,
                 "best_iteration": best_iteration, "warnings": [str(item.message) for item in caught],
                 "lr_n_iter": getattr(model, "n_iter_", np.array([])).tolist(), "cpu_threads": threads}
    return pipeline, profiling


def attack_scores(pipeline, frame):
    probabilities = pipeline.predict_proba(frame)
    classes = pipeline.named_steps["model"].classes_
    locations = np.flatnonzero(classes == 1)
    return probabilities[:, locations[0]] if len(locations) else np.zeros(len(frame))


def benchmark_inference(pipeline, frame, config):
    batch_size = int(config.get("inference_batch_size", 4096))
    frame = frame.iloc[:batch_size]
    if len(frame) < batch_size:
        raise ValueError("Not enough development rows for fixed inference batch")
    repeats = int(config.get("benchmark_repeats", 5))
    transformer, model = pipeline.named_steps.values()
    threads = int(config.get("cpu_threads", 4))
    with threadpool_limits(limits=threads):
        transformed = transformer.transform(frame)
        model.predict_proba(transformed)
        pipeline.predict_proba(frame)
        model_times, full_times = [], []
        for _ in range(repeats):
            start = time.perf_counter()
            model.predict_proba(transformed)
            model_times.append(time.perf_counter() - start)
            start = time.perf_counter()
            pipeline.predict_proba(frame)
            full_times.append(time.perf_counter() - start)
    full = float(np.median(full_times))
    return {"inference_model_only_seconds_per_flow": float(np.median(model_times)) / len(frame),
            "inference_end_to_end_seconds_per_flow": full / len(frame),
            "inference_throughput_flows_per_second": len(frame) / full,
            "inference_batch_size": len(frame), "benchmark_repeats": repeats,
            "benchmark_warmup_batches": 1, "model_only_batch_seconds": model_times,
            "end_to_end_batch_seconds": full_times,
            "latency_scope": "amortized batch CPU preprocessing/prediction; excludes flow extraction"}
