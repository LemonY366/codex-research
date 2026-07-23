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
from scripts.validate_workspace import WorkspaceValidator


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


def phase_one_token_summary(root: Path) -> dict[str, object]:
    """Read the current phase-one resource snapshot through the flat-YAML parser."""

    validator = WorkspaceValidator(root)
    entries = validator.read_flat_yaml_registry(
        "research/resources.yaml", "snapshots", "resource_id"
    )
    current = (
        next((entry for entry in entries or [] if entry.get("status") == "当前"), None)
    )
    fields = (
        "brainstorm_input_tokens",
        "brainstorm_output_tokens",
        "brainstorm_total_tokens",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    )
    return {
        "recorded": current is not None,
        **{field: current.get(field) if current else None for field in fields},
        "unavailable_metrics": current.get("unavailable_metrics", []) if current else [],
    }


def task_token_summary(root: Path, stage: str) -> dict[str, object]:
    """Aggregate stage-two API or stage-three Codex tokens without mixing them."""

    statuses = task_statuses(root, stage)
    fields = (
        ("api_input_tokens", "api_output_tokens", "api_total_tokens")
        if stage == "stage_two"
        else ("input_tokens", "output_tokens", "total_tokens")
    )
    totals = {field: 0 for field in fields}
    unavailable: dict[str, list[str]] = {field: [] for field in fields}
    for status in statuses:
        task_run_id = str(status.get("task_run_id"))
        resources = status.get("resources")
        if not isinstance(resources, dict):
            for field in fields:
                unavailable[field].append(task_run_id)
            continue
        for field in fields:
            value = resources.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[field] += value
            elif stage == "stage_two" and resources.get("api_calls") == 0:
                continue
            else:
                unavailable[field].append(task_run_id)
    return {
        "record_count": len(statuses),
        **{
            field: value if statuses else None
            for field, value in totals.items()
        },
        "complete": bool(statuses) and not any(unavailable.values()),
        "unavailable_task_ids": unavailable,
    }


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
    update.add_argument("--input-tokens", type=int)
    update.add_argument("--output-tokens", type=int)
    update.add_argument("--total-tokens", type=int)
    update.add_argument("--api-input-tokens", type=int)
    update.add_argument("--api-output-tokens", type=int)
    update.add_argument("--api-total-tokens", type=int)
    update.add_argument(
        "--token-unavailable",
        action="append",
        default=[],
        metavar="FIELD:REASON",
    )
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

    token_summary = subparsers.add_parser("token-summary")
    token_summary.add_argument(
        "--stage",
        choices=("phase_one", "stage_two", "stage_three", "all"),
        default="all",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "token-summary":
        result: dict[str, object] = {}
        if args.stage in {"phase_one", "all"}:
            result["phase_one"] = phase_one_token_summary(args.root)
        if args.stage in {"stage_two", "all"}:
            result["stage_two_api"] = task_token_summary(args.root, "stage_two")
        if args.stage in {"stage_three", "all"}:
            result["stage_three_codex"] = task_token_summary(
                args.root, "stage_three"
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
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
                "input_tokens": args.input_tokens,
                "output_tokens": args.output_tokens,
                "total_tokens": args.total_tokens,
                "api_input_tokens": args.api_input_tokens,
                "api_output_tokens": args.api_output_tokens,
                "api_total_tokens": args.api_total_tokens,
                "token_unavailable_reasons": (
                    args.token_unavailable if args.token_unavailable else None
                ),
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
