"""Atomic task progress, append-only events, and heartbeats.

Both stage-two experiment scripts and stage-three writing workflows use this
module. It intentionally depends only on the Python standard library.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_STATUSES = {"queued", "running", "blocked", "failed", "success"}
TASK_STAGES = {"stage_two", "stage_three"}


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    """Write JSON through a same-directory temporary file and atomic replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


class TaskProgress:
    """Manage one observable stage-two or stage-three task."""

    def __init__(self, task_dir: Path) -> None:
        self.task_dir = task_dir.resolve()
        self.status_path = self.task_dir / "status.json"
        self.events_path = self.task_dir / "events.jsonl"
        self.heartbeat_path = self.task_dir / "heartbeat.json"

    def start(
        self,
        *,
        task_run_id: str,
        stage: str,
        task_kind: str,
        label: str,
        step: str,
        total: int | None = None,
        unit: str | None = None,
    ) -> dict[str, Any]:
        """Create a new task without overwriting an existing status."""

        if self.status_path.exists():
            raise FileExistsError(f"task status already exists: {self.status_path}")
        if stage not in TASK_STAGES:
            raise ValueError(f"unsupported task stage: {stage}")
        if total is not None and total < 0:
            raise ValueError("total must be non-negative")
        now = utc_now()
        status: dict[str, Any] = {
            "schema_version": 1,
            "task_run_id": task_run_id,
            "stage": stage,
            "task_kind": task_kind,
            "label": label,
            "status": "queued",
            "step": step,
            "completed": 0,
            "total": total,
            "unit": unit,
            "progress_percent": 0.0 if total else None,
            "started_at": now,
            "updated_at": now,
            "last_checkpoint": None,
            "blocked_reason": None,
            "resume_condition": None,
            "resources": {
                "api_calls": 0,
                "api_successes": 0,
                "api_failures": 0,
                "api_retries": 0,
                "api_rate_limits": 0,
                "estimated_cost": 0.0,
                "cost_currency": "CNY",
                "gpu_seconds": 0.0,
                "peak_vram_bytes": None,
            },
            "outputs": [],
        }
        self.task_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_json(self.status_path, status)
        self._append_event("queued", "task created", status)
        self.heartbeat(message="task created")
        return status

    def read(self) -> dict[str, Any]:
        """Read the current status object."""

        value = json.loads(self.status_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("status.json must contain an object")
        return value

    def update(
        self,
        *,
        status_name: str | None = None,
        step: str | None = None,
        completed: int | None = None,
        total: int | None = None,
        message: str = "progress updated",
        checkpoint: str | None = None,
        blocked_reason: str | None = None,
        resume_condition: str | None = None,
        resource_updates: dict[str, Any] | None = None,
        outputs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Atomically update progress and append an event."""

        current = self.read()
        next_status = status_name or str(current["status"])
        if next_status not in TASK_STATUSES:
            raise ValueError(f"unsupported task status: {next_status}")
        if next_status == "blocked" and (not blocked_reason or not resume_condition):
            raise ValueError("blocked tasks require blocked_reason and resume_condition")
        if next_status == "failed" and not blocked_reason:
            raise ValueError("failed tasks require blocked_reason")
        if completed is not None:
            if completed < 0:
                raise ValueError("completed must be non-negative")
            current["completed"] = completed
        if total is not None:
            if total < 0:
                raise ValueError("total must be non-negative")
            current["total"] = total
        current_total = current.get("total")
        current_completed = current.get("completed")
        if isinstance(current_total, int) and current_total > 0:
            if not isinstance(current_completed, int) or current_completed > current_total:
                raise ValueError("completed cannot exceed total")
            current["progress_percent"] = round(
                current_completed * 100.0 / current_total, 2
            )
        else:
            current["progress_percent"] = None
        if (
            next_status == "success"
            and isinstance(current_total, int)
            and current_total > 0
            and current_completed != current_total
        ):
            raise ValueError("successful task must complete its declared total")
        current["status"] = next_status
        if step is not None:
            current["step"] = step
        if checkpoint is not None:
            current["last_checkpoint"] = checkpoint
        current["blocked_reason"] = blocked_reason
        current["resume_condition"] = resume_condition
        if resource_updates:
            resources = current.setdefault("resources", {})
            resources.update(resource_updates)
        if outputs:
            merged = list(dict.fromkeys([*current.get("outputs", []), *outputs]))
            current["outputs"] = merged
        current["updated_at"] = utc_now()
        atomic_write_json(self.status_path, current)
        self._append_event(next_status, message, current)
        self.heartbeat(message=message)
        return current

    def heartbeat(self, *, message: str = "alive") -> None:
        """Atomically refresh the task heartbeat."""

        current = self.read()
        atomic_write_json(
            self.heartbeat_path,
            {
                "schema_version": 1,
                "task_run_id": current["task_run_id"],
                "heartbeat_at": utc_now(),
                "status": current["status"],
                "step": current["step"],
                "message": message,
            },
        )

    def archive(self, destination: Path) -> None:
        """Copy progress evidence into an existing or new evidence directory."""

        destination.mkdir(parents=True, exist_ok=True)
        for source in (self.status_path, self.events_path, self.heartbeat_path):
            target = destination / source.name
            if target.exists():
                raise FileExistsError(f"refusing to overwrite evidence: {target}")
            shutil.copy2(source, target)

    def _append_event(
        self, event_type: str, message: str, status: dict[str, Any]
    ) -> None:
        event = {
            "schema_version": 1,
            "event_at": utc_now(),
            "task_run_id": status["task_run_id"],
            "event_type": event_type,
            "stage": status["stage"],
            "step": status["step"],
            "completed": status.get("completed"),
            "total": status.get("total"),
            "message": message,
        }
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
