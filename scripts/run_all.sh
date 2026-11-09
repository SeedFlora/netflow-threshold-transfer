#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${NIDS_PYTHON:-.venv/bin/python}"
CONFIG="${1:-configs/main.yaml}"
"$PYTHON" -m nids_lab doctor
"$PYTHON" -m nids_lab audit --data f7546561558c07c5_NFV3DATA-A11964_A11964.zip
"$PYTHON" -m nids_lab prepare --config "$CONFIG"
"$PYTHON" -m pytest -q
"$PYTHON" -m nids_lab freeze --config "$CONFIG"
"$PYTHON" -m nids_lab smoke --config configs/smoke.yaml --resume
"$PYTHON" -m nids_lab run --config "$CONFIG" --resume
"$PYTHON" -m nids_lab evaluate --config "$CONFIG"
"$PYTHON" -m nids_lab report --config "$CONFIG"
