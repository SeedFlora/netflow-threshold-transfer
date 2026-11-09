from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

import psutil


def gpu_snapshot():
    try:
        output = subprocess.check_output([
            "nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version",
            "--format=csv,noheader,nounits",
        ], text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        name, total, used, driver = output.strip().splitlines()[0].split(", ")
        return {"name": name, "total_mb": float(total), "used_mb": float(used), "driver": driver,
                "scope": "device-wide; includes other processes, not process-attributed"}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def doctor(workspace=Path(".")):
    memory = psutil.virtual_memory()
    dependencies = {}
    for name in ["numpy", "pandas", "pyarrow", "scikit-learn", "xgboost", "scipy", "pyyaml", "joblib", "psutil", "matplotlib", "pytest"]:
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    return {"timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "os": platform.platform(), "python": platform.python_version(),
            "cpu": platform.processor(), "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(), "ram_total_bytes": memory.total,
            "ram_available_bytes": memory.available, "disk_free_bytes": shutil.disk_usage(workspace).free,
            "gpu": gpu_snapshot(), "dependencies": dependencies}


def tree_rss(pid):
    try:
        parent = psutil.Process(pid)
        processes = [parent] + parent.children(recursive=True)
        total = 0
        for process in processes:
            try:
                total += process.memory_info().rss
            except psutil.Error:
                pass
        return total
    except psutil.Error:
        return 0
