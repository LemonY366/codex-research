"""Create, update, inspect, and archive observable stage tasks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.runtime.progress import TaskProgress


def task_statuses(root: Path, stage: str) -> list[dict[str, object]]:
    """Return deduplicated task statuses, preferring immutable run archives."""

    statuses: dict[str, dict[str, object]] = {}
    roots = [root / "workflow/tasks"] if stage == "stage_two" else [root / "paper/sessions"]
    if stage == "stage_two":
        roots.append(root / "experiments/runs")
    for task_root in roots:
        if not task_root.is_dir():
            continue
        for task_dir in sorted(path for path in task_root.iterdir() if path.is_dir()):
            status_path = task_dir / "status.json"
            if not status_path.is_file():
                continue
            value = json.loads(status_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("stage") != stage:
                continue
            task_run_id = value.get("task_run_id")
            if isinstance(task_run_id, str):
                statuses[task_run_id] = value
    return list(statuses.values())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--task-run-id", required=True)
    start.add_argument("--stage", choices=("stage_two", "stage_three"), required=True)
    start.add_argument("--kind", required=True)
    start.add_argument("--label", required=True)
    start.add_argument("--step", required=True)
    start.add_argument("--total", type=int)
    start.add_argument("--unit")

    update = subparsers.add_parser("update")
    update.add_argument(
        "--status", choices=("queued", "running", "blocked", "failed", "success")
    )
    update.add_argument("--step")
    update.add_argument("--completed", type=int)
    update.add_argument("--total", type=int)
    update.add_argument("--message", default="progress updated")
    update.add_argument("--checkpoint")
    update.add_argument("--blocked-reason")
    update.add_argument("--resume-condition")
    update.add_argument("--output", action="append", default=[])
    update.add_argument("--api-calls", type=int)
    update.add_argument("--api-successes", type=int)
    update.add_argument("--api-failures", type=int)
    update.add_argument("--api-retries", type=int)
    update.add_argument("--api-rate-limits", type=int)
    update.add_argument("--estimated-cost", type=float)
    update.add_argument("--cost-currency")
    update.add_argument("--gpu-seconds", type=float)
    update.add_argument("--peak-vram-bytes", type=int)

    heartbeat = subparsers.add_parser("heartbeat")
    heartbeat.add_argument("--message", default="alive")

    subparsers.add_parser("show")

    archive = subparsers.add_parser("archive")
    archive.add_argument("--destination", type=Path, required=True)

    listing = subparsers.add_parser("list")
    listing.add_argument("--stage", choices=("stage_two", "stage_three", "all"), default="all")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "list":
        roots = []
        if args.stage in {"stage_two", "all"}:
            roots.append(args.root / "workflow/tasks")
        if args.stage in {"stage_three", "all"}:
            roots.append(args.root / "paper/sessions")
        result = []
        for root in roots:
            if not root.is_dir():
                continue
            for task_dir in sorted(path for path in root.iterdir() if path.is_dir()):
                progress = TaskProgress(task_dir)
                if not progress.status_path.is_file():
                    continue
                status = progress.read()
                if progress.heartbeat_path.is_file():
                    status["heartbeat"] = json.loads(
                        progress.heartbeat_path.read_text(encoding="utf-8")
                    )
                result.append(status)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.task_dir is None:
        raise SystemExit("--task-dir is required for this command")
    progress = TaskProgress(args.task_dir)
    if args.command == "start":
        result = progress.start(
            task_run_id=args.task_run_id,
            stage=args.stage,
            task_kind=args.kind,
            label=args.label,
            step=args.step,
            total=args.total,
            unit=args.unit,
        )
    elif args.command == "update":
        resources = {
            key: value
            for key, value in {
                "api_calls": args.api_calls,
                "api_successes": args.api_successes,
                "api_failures": args.api_failures,
                "api_retries": args.api_retries,
                "api_rate_limits": args.api_rate_limits,
                "estimated_cost": args.estimated_cost,
                "cost_currency": args.cost_currency,
                "gpu_seconds": args.gpu_seconds,
                "peak_vram_bytes": args.peak_vram_bytes,
            }.items()
            if value is not None
        }
        result = progress.update(
            status_name=args.status,
            step=args.step,
            completed=args.completed,
            total=args.total,
            message=args.message,
            checkpoint=args.checkpoint,
            blocked_reason=args.blocked_reason,
            resume_condition=args.resume_condition,
            resource_updates=resources,
            outputs=args.output,
        )
    elif args.command == "heartbeat":
        progress.heartbeat(message=args.message)
        result = progress.read()
    elif args.command == "archive":
        progress.archive(args.destination)
        result = progress.read()
    else:
        result = progress.read()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
