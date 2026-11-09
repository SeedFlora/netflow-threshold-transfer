from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from .common import load_config, write_json


def main():
    parser = argparse.ArgumentParser(description="Capture-aware NetFlow experiment lab")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    audit = commands.add_parser("audit")
    audit.add_argument("--data", required=True)
    for name in ["prepare", "freeze", "smoke", "run", "evaluate", "report"]:
        child = commands.add_parser(name)
        child.add_argument("--config", required=True)
        if name in ["run", "smoke"]:
            child.add_argument("--resume", action="store_true")
    worker = commands.add_parser("_fit", help=argparse.SUPPRESS)
    worker.add_argument("--job", required=True)
    args = parser.parse_args()
    if args.command == "doctor":
        from .profiling import doctor
        result = doctor()
        write_json("reports/environment.json", result)
    elif args.command == "audit":
        from .audit import audit_dataset
        result = audit_dataset(args.data)
    elif args.command == "_fit":
        from .runner import execute_fit
        job = json.loads(Path(args.job).read_text(encoding="utf-8"))
        try:
            execute_fit(**job)
        except Exception as error:
            write_json(Path(job["run_dir"]) / "status.json", {"status": "failed", "reason": repr(error)})
            traceback.print_exc()
            raise SystemExit(1)
        return
    else:
        config = load_config(args.config)
        if args.command == "prepare":
            from .splits import prepare_splits
            result = prepare_splits(config)
        elif args.command == "freeze":
            from .runner import freeze_plan
            result = freeze_plan(config)
        elif args.command in ["run", "smoke"]:
            from .runner import run_experiments
            if args.command == "smoke" and config["profile"] != "smoke":
                raise ValueError("smoke command requires profile: smoke")
            result = run_experiments(config, resume=args.resume)
        elif args.command == "evaluate":
            from .evaluate import evaluate_run
            count = 0
            for directory in sorted(Path("runs").glob("*")):
                if not (directory / "metadata.json").exists() or not (directory / "status.json").exists():
                    continue
                metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
                status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
                if metadata.get("profile") == config["profile"] and status.get("status") == "completed":
                    print(f"Evaluating {directory.name}", flush=True)
                    evaluate_run(directory, config)
                    count += 1
            result = {"evaluated_runs": count}
        elif args.command == "report":
            from .reporting import report_experiments
            result = report_experiments(config, Path("."))
    print(json.dumps(result, default=str, indent=2, ensure_ascii=False))
    if args.command in ["run", "smoke"] and (result.get("failed", 0) or result.get("not_run", 0)):
        raise SystemExit(2)
