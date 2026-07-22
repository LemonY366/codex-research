"""Transactionally advance or roll back the research workflow.

This is the only supported writer for the machine workflow state and the
projected state fields in RESEARCH.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.validate_workspace import WorkspaceValidator  # noqa: E402


PHASE_ONE_NODES = (
    "INTAKE",
    "DIVERGE",
    "SEARCH",
    "COMPARE",
    "DRAFT",
    "CONFIRM",
    "GATE_CHECK",
)
NODES = (*PHASE_ONE_NODES, "阶段二：实验与分析", "阶段三：论文写作")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_text(
        path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


class WorkflowLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.descriptor: int | None = None

    def __enter__(self) -> "WorkflowLock":
        try:
            self.descriptor = os.open(
                self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError as exc:
            raise RuntimeError("another workflow transition is active") from exc
        os.write(self.descriptor, f"pid={os.getpid()}\n".encode())
        return self

    def __exit__(self, *_: object) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
        self.path.unlink(missing_ok=True)


def read_state(root: Path) -> dict[str, Any]:
    value = json.loads((root / "workflow/state.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("workflow/state.json must contain an object")
    return value


def current_node(state: dict[str, Any]) -> str:
    if state["current_phase"] == "阶段一：调研与设计":
        return str(state["phase_one_substate"])
    return str(state["current_phase"])


def target_projection(target: str, status: str) -> dict[str, str]:
    if target in PHASE_ONE_NODES:
        return {
            "current_phase": "阶段一：调研与设计",
            "phase_one_substate": target,
            "phase_status": status,
            "gate_result": "已通过" if status != "未开始" else "待检查",
        }
    return {
        "current_phase": target,
        "phase_one_substate": "GATE_CHECK",
        "phase_status": status,
        "gate_result": "已通过",
    }


def validate_target(
    root: Path,
    target: str,
    status: str,
    *,
    is_rollback: bool = False,
    is_pause: bool = False,
) -> list[str]:
    if is_pause:
        pause_validator = WorkspaceValidator(root)
        pause_validator.check_stage_state()
        pause_validator.check_machine_workflow_state()
        return [
            f"{item.code}: {item.path}: {item.message}"
            for item in pause_validator.findings
            if item.severity == "ERROR"
        ]
    current = WorkspaceValidator(root)
    findings = current.validate()
    blockers = [
        f"{item.code}: {item.path}: {item.message}"
        for item in findings
        if item.severity == "ERROR"
    ]
    if blockers and not is_rollback:
        return blockers

    target_validator = WorkspaceValidator(root)
    if target in PHASE_ONE_NODES:
        target_validator.check_research_contract(
            "阶段一：调研与设计",
            status,
            phase_one_state_override=target,
            preflight_transition=True,
        )
        target_validator.check_phase_one_evidence(
            "阶段一：调研与设计", status, phase_one_state_override=target
        )
    else:
        target_validator.check_research_contract(
            target,
            status,
            phase_one_state_override="GATE_CHECK",
            preflight_transition=True,
        )
        target_validator.check_phase_one_evidence(
            target, status, phase_one_state_override="GATE_CHECK"
        )
        target_validator.check_unresolved_todos(target, status)
        if target == "阶段三：论文写作" or (
            target == "阶段二：实验与分析" and status == "已完成"
        ):
            target_validator.check_stage_two_handoff(required=True)
        target_validator.check_stage_three_session_completion(target, status)
    boundary = not is_rollback and target in {
        "GATE_CHECK",
        "阶段二：实验与分析",
        "阶段三：论文写作",
    }
    return [
        f"{item.code}: {item.path}: {item.message}"
        for item in target_validator.findings
        if item.severity == "ERROR" or (boundary and item.severity == "WARN")
    ]


def replace_list_field(text: str, label: str, value: str) -> str:
    pattern = rf"(?m)^- {re.escape(label)}：.*$"
    replacement = f"- {label}：{value}。"
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise ValueError(f"RESEARCH.md is missing field: {label}")
    return updated


def append_markdown_transition(
    text: str,
    *,
    transition_id: str,
    occurred_at: str,
    source: str,
    target: str,
    reason: str,
    decision_ids: list[str],
) -> str:
    row = (
        f"| {transition_id} | {occurred_at} | {source} | {target} | 已通过 | "
        f"{reason} | {', '.join(decision_ids) if decision_ids else '不适用'} |"
    )
    placeholder = "| 待分配 | TODO | TODO | TODO | TODO | TODO | 待分配 |"
    if placeholder in text:
        return text.replace(placeholder, row, 1)
    marker = "\n\n记录必须连续；最新真实 `TRANS`"
    if marker not in text:
        raise ValueError("RESEARCH.md transition table marker is missing")
    return text.replace(marker, f"\n{row}{marker}", 1)


def recover_transaction(root: Path) -> None:
    journal_path = root / "workflow/transaction.json"
    if not journal_path.is_file():
        return
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    atomic_write_text(root / "RESEARCH.md", journal["research_text"])
    atomic_write_json(root / "workflow/state.json", journal["state"])
    atomic_write_text(
        root / "workflow/transitions.jsonl", journal["transitions_text"]
    )
    journal_path.unlink()


def commit_transaction(
    root: Path,
    *,
    research_text: str,
    state: dict[str, Any],
    transitions_text: str,
) -> None:
    journal_path = root / "workflow/transaction.json"
    atomic_write_json(
        journal_path,
        {
            "schema_version": 1,
            "prepared_at": utc_now(),
            "research_text": research_text,
            "state": state,
            "transitions_text": transitions_text,
        },
    )
    recover_transaction(root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--to", choices=NODES, required=True)
    parser.add_argument("--status", choices=("未开始", "进行中", "已暂停", "已完成"), default="进行中")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--resume-condition")
    parser.add_argument("--decision-id", action="append", default=[])
    parser.add_argument("--authorization-id", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.status == "已暂停" and not args.resume_condition:
        raise SystemExit("--resume-condition is required when status is 已暂停")
    root = args.root.resolve()
    lock_path = root / "workflow/transition.lock"
    with WorkflowLock(lock_path):
        recover_transaction(root)
        state = read_state(root)
        source = current_node(state)
        source_index = NODES.index(source)
        target_index = NODES.index(args.to)
        if target_index > source_index + 1:
            raise SystemExit(f"refusing to skip workflow states: {source} -> {args.to}")
        blockers = validate_target(
            root,
            args.to,
            args.status,
            is_rollback=target_index < source_index,
            is_pause=args.status == "已暂停",
        )
        if blockers:
            print("Transition rejected; no state was changed:", file=sys.stderr)
            for blocker in blockers:
                print(f"- {blocker}", file=sys.stderr)
            return 2

        revision = int(state["revision"]) + 1
        transition_id = f"TRANS-{revision:03d}"
        occurred_at = utc_now()
        projection = target_projection(args.to, args.status)
        next_state = {
            "schema_version": 1,
            "revision": revision,
            **projection,
            "last_transition_id": transition_id,
            "updated_at": occurred_at,
        }
        event = {
            "schema_version": 1,
            "transition_id": transition_id,
            "revision": revision,
            "occurred_at": occurred_at,
            "from_node": source,
            "to_node": args.to,
            "from_phase": state["current_phase"],
            "to_phase": projection["current_phase"],
            "reason": args.reason,
            "decision_ids": args.decision_id,
            "authorization_ids": args.authorization_id,
            "gate_result": projection["gate_result"],
            "validation": "no blocking findings",
        }
        transitions_path = root / "workflow/transitions.jsonl"
        transitions_text = transitions_path.read_text(encoding="utf-8")
        transitions_text += json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"

        research_text = (root / "RESEARCH.md").read_text(encoding="utf-8")
        research_text = replace_list_field(
            research_text, "当前阶段", projection["current_phase"]
        )
        research_text = replace_list_field(
            research_text, "阶段一子状态", projection["phase_one_substate"]
        )
        research_text = replace_list_field(
            research_text, "阶段状态", projection["phase_status"]
        )
        research_text = replace_list_field(
            research_text, "阶段门禁", projection["gate_result"]
        )
        research_text = replace_list_field(
            research_text,
            "停止原因",
            args.reason if args.status == "已暂停" else "不适用",
        )
        research_text = replace_list_field(
            research_text,
            "恢复条件",
            args.resume_condition if args.status == "已暂停" else "不适用",
        )
        research_text = replace_list_field(
            research_text, "当前全局阶段", projection["current_phase"]
        )
        research_text = replace_list_field(
            research_text, "当前阶段一子状态", projection["phase_one_substate"]
        )
        research_text = append_markdown_transition(
            research_text,
            transition_id=transition_id,
            occurred_at=occurred_at,
            source=source,
            target=args.to,
            reason=args.reason,
            decision_ids=args.decision_id,
        )
        commit_transaction(
            root,
            research_text=research_text,
            state=next_state,
            transitions_text=transitions_text,
        )
        print(f"Committed {transition_id}: {source} -> {args.to}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
