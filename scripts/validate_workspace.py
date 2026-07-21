"""Validate repository structure, workflow state, evidence, and safety boundaries.

This tool is read-only. It does not start Codex, load ``.env``, create registry
files, repair run records, or generate research content.

Run from the repository root with::

    uv run python scripts/validate_workspace.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


REQUIRED_PATHS = (
    "README.md",
    "AGENTS.md",
    "RESEARCH.md",
    "experiments/TODO.md",
    "paper/TODO.md",
    ".env.example",
    "docs/README.md",
    "docs/TEMPLATE_BOUNDARIES.md",
    "docs/WORKFLOW_GATES.md",
    "docs/SKILL_USAGE.md",
    "datasets/README.md",
    "models/README.md",
    "baselines/README.md",
    "scripts/README.md",
    "src/README.md",
    "experiments/README.md",
    "experiments/scripts/README.md",
    "experiments/runs/README.md",
    "paper/README.md",
    "paper/draft_zh.md",
    "paper/images/README.md",
    "patents/README.md",
)

VALID_PHASES = {
    "阶段一：调研与设计",
    "阶段二：实验与分析",
    "阶段三：论文写作",
}
VALID_PHASE_STATUSES = {"未开始", "进行中", "已暂停", "已完成"}
VALID_GATE_RESULTS = {"待检查", "未通过", "已通过", "不适用"}
STAGE_TODO_PATHS = {
    "阶段二：实验与分析": "experiments/TODO.md",
    "阶段三：论文写作": "paper/TODO.md",
}
STAGE_TODO_LINE_WARNING = 500

EXPECTED_TEMPLATE_SKILLS = {
    "docx",
    "paddleocr-doc-parsing",
    "paddleocr-text-recognition",
    "paper-skill-creater",
    "pdf",
    "pptx",
    "xlsx",
}

REGISTRY_RULES = {
    "datasets/registry.yaml": (
        "id",
        "name",
        "source",
        "version",
        "license",
        "checksum",
        "path",
        "classification",
        "external_api_allowed",
    ),
    "models/registry.yaml": (
        "id",
        "name",
        "source",
        "version",
        "license",
        "path",
    ),
    "baselines/registry.yaml": (
        "id",
        "name",
        "upstream",
        "revision",
        "license",
        "path",
    ),
    "experiments/registry.yaml": (
        "experiment_id",
        "status",
        "script",
        "runs",
    ),
}

SKIPPED_SCAN_PREFIXES = (
    ".agents/",
    ".git/",
    ".venv/",
)
SKIPPED_SCAN_NAMES = {".env"}
MAX_SCAN_BYTES = 2_000_000

SECRET_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "api-token",
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{16,}|"
            r"github_pat_[A-Za-z0-9_]{16,})\b"
        ),
    ),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:LLM_API_KEY|OPENAI_API_KEY|WANDB_API_KEY|API_KEY|TOKEN|PASSWORD)"
    r"\s*[:=]\s*['\"]?([^\s'\";#]+)"
)
DATABASE_CREDENTIAL = re.compile(
    r"(?i)\bDATABASE_URL\s*=\s*['\"]?[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@"
)


@dataclass(frozen=True)
class Finding:
    """One validation finding without sensitive content."""

    severity: str
    code: str
    path: str
    message: str


class WorkspaceValidator:
    """Run non-mutating validation checks against a research workspace."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.findings: list[Finding] = []
        self.run_experiment_ids: set[str] = set()

    def add(self, severity: str, code: str, path: str, message: str) -> None:
        """Add a sanitized finding."""

        self.findings.append(Finding(severity, code, path, message))

    def validate(self) -> list[Finding]:
        """Execute all checks and return findings in deterministic order."""

        self.check_required_paths()
        self.check_skill_layout()
        phase, status = self.check_stage_state()
        self.check_unresolved_todos(phase, status)
        self.check_registries()
        self.check_run_records()
        self.check_tracked_run_mutations()
        self.check_paper_traceability()
        self.check_suspected_secrets()
        return sorted(
            self.findings,
            key=lambda item: (item.severity != "ERROR", item.path, item.code),
        )

    def check_required_paths(self) -> None:
        """Check the stable documents required by the template."""

        for relative_path in REQUIRED_PATHS:
            if not (self.root / relative_path).is_file():
                self.add(
                    "ERROR",
                    "REQUIRED_PATH_MISSING",
                    relative_path,
                    "required template document is missing",
                )
        if (self.root / "TODO.md").exists():
            self.add(
                "ERROR",
                "LEGACY_ROOT_TODO",
                "TODO.md",
                "root TODO.md is obsolete; move phase-two and phase-three tasks to their stage directories",
            )

    def check_skill_layout(self) -> None:
        """Validate repository Skill discovery paths and basic metadata."""

        agents_root = self.root / ".agents"
        active_root = agents_root / "skills"
        usage_path = self.root / "docs/SKILL_USAGE.md"
        usage_text = (
            usage_path.read_text(encoding="utf-8") if usage_path.is_file() else ""
        )

        if not active_root.is_dir():
            self.add(
                "ERROR",
                "SKILL_ROOT_MISSING",
                ".agents/skills",
                "repository Skills must use the Codex discovery path",
            )
            return

        for child in sorted(agents_root.iterdir()):
            if (
                child.is_dir()
                and child.name not in {"skills", "skill-creator"}
                and (child / "SKILL.md").is_file()
            ):
                self.add(
                    "ERROR",
                    "SKILL_LEGACY_PATH",
                    child.relative_to(self.root).as_posix(),
                    "active repository Skill is outside .agents/skills",
                )

        discovered: set[str] = set()
        for skill_dir in sorted(path for path in active_root.iterdir() if path.is_dir()):
            relative = skill_dir.relative_to(self.root).as_posix()
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                self.add(
                    "ERROR",
                    "SKILL_FILE_MISSING",
                    relative,
                    "Skill directory is missing SKILL.md",
                )
                continue
            text = skill_file.read_text(encoding="utf-8")
            frontmatter = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
            if not frontmatter:
                self.add(
                    "ERROR",
                    "SKILL_FRONTMATTER_INVALID",
                    f"{relative}/SKILL.md",
                    "SKILL.md must start with YAML frontmatter",
                )
                continue
            header = frontmatter.group(1)
            name_match = re.search(r"(?m)^name:\s*['\"]?([a-z0-9-]+)", header)
            description_match = re.search(r"(?m)^description:\s*(?:.+|[>|]-?)$", header)
            if not name_match or not description_match:
                self.add(
                    "ERROR",
                    "SKILL_METADATA_MISSING",
                    f"{relative}/SKILL.md",
                    "Skill frontmatter must contain name and description",
                )
                continue
            name = name_match.group(1)
            if name != skill_dir.name:
                self.add(
                    "ERROR",
                    "SKILL_NAME_MISMATCH",
                    f"{relative}/SKILL.md",
                    "Skill name must match its directory name",
                )
            if name in discovered:
                self.add(
                    "ERROR",
                    "SKILL_NAME_DUPLICATE",
                    f"{relative}/SKILL.md",
                    "duplicate active repository Skill name",
                )
            discovered.add(name)
            if name not in EXPECTED_TEMPLATE_SKILLS and not name.startswith("paper-"):
                if f"`{name}`" not in usage_text:
                    self.add(
                        "WARN",
                        "SKILL_USAGE_UNDOCUMENTED",
                        f"{relative}/SKILL.md",
                        "new repository Skill is not documented in docs/SKILL_USAGE.md",
                    )

        for missing_name in sorted(EXPECTED_TEMPLATE_SKILLS - discovered):
            self.add(
                "ERROR",
                "TEMPLATE_SKILL_MISSING",
                f".agents/skills/{missing_name}",
                "expected template Skill is missing from the discovery path",
            )

    def check_stage_state(self) -> tuple[str | None, str | None]:
        """Validate the global workflow state in RESEARCH.md."""

        research_path = self.root / "RESEARCH.md"
        if not research_path.is_file():
            return None, None
        text = research_path.read_text(encoding="utf-8")
        phase = self.extract_field(text, "当前阶段")
        status = self.extract_field(text, "阶段状态")
        gate = self.extract_field(text, "阶段门禁")

        if phase not in VALID_PHASES:
            self.add(
                "ERROR",
                "INVALID_PHASE",
                "RESEARCH.md",
                f"current phase must be one of {sorted(VALID_PHASES)}",
            )
        if status not in VALID_PHASE_STATUSES:
            self.add(
                "ERROR",
                "INVALID_PHASE_STATUS",
                "RESEARCH.md",
                f"phase status must be one of {sorted(VALID_PHASE_STATUSES)}",
            )
        if gate not in VALID_GATE_RESULTS:
            self.add(
                "ERROR",
                "INVALID_GATE_RESULT",
                "RESEARCH.md",
                f"gate result must be one of {sorted(VALID_GATE_RESULTS)}",
            )
        if status in {"进行中", "已完成"} and gate != "已通过":
            self.add(
                "ERROR",
                "ACTIVE_PHASE_WITHOUT_GATE",
                "RESEARCH.md",
                "an in-progress or completed phase must have a passed gate",
            )
        if status == "已暂停":
            pause_reason = self.extract_field(text, "停止原因")
            resume_condition = self.extract_field(text, "恢复条件")
            if pause_reason in {None, "不适用", "TODO"}:
                self.add(
                    "ERROR",
                    "PAUSE_REASON_MISSING",
                    "RESEARCH.md",
                    "a paused phase must record a stop reason",
                )
            if resume_condition in {None, "不适用", "TODO"}:
                self.add(
                    "ERROR",
                    "RESUME_CONDITION_MISSING",
                    "RESEARCH.md",
                    "a paused phase must record a resume condition",
                )
        return phase, status

    @staticmethod
    def extract_field(text: str, label: str) -> str | None:
        """Extract a Chinese list field while ignoring the final full stop."""

        match = re.search(rf"^- {re.escape(label)}：(.+?)。?$", text, re.MULTILINE)
        return match.group(1).strip() if match else None

    def check_unresolved_todos(
        self, phase: str | None, status: str | None
    ) -> None:
        """Report unresolved placeholders when workflow progress makes them critical."""

        research_path = self.root / "RESEARCH.md"
        if not research_path.is_file():
            return
        research_count = len(re.findall(r"\bTODO\b", research_path.read_text("utf-8")))

        later_phase = phase in {"阶段二：实验与分析", "阶段三：论文写作"}
        if research_count and (later_phase or status == "已完成"):
            self.add(
                "ERROR",
                "CRITICAL_RESEARCH_TODO",
                "RESEARCH.md",
                f"{research_count} unresolved TODO marker(s) remain after stage-one intake",
            )
        elif research_count:
            self.add(
                "WARN" if status == "进行中" else "INFO",
                "RESEARCH_TODO",
                "RESEARCH.md",
                f"{research_count} TODO marker(s) remain and must be resolved or justified before transition",
            )
        for task_phase, relative_path in STAGE_TODO_PATHS.items():
            task_path = self.root / relative_path
            if not task_path.is_file():
                continue
            task_text = task_path.read_text(encoding="utf-8")
            task_count = len(re.findall(r"\bTODO\b", task_text))
            if task_count:
                is_current = phase == task_phase
                if is_current and status == "已完成":
                    severity = "ERROR"
                elif is_current and status == "进行中":
                    severity = "WARN"
                else:
                    severity = "INFO"
                self.add(
                    severity,
                    "TASK_TODO",
                    relative_path,
                    f"{task_count} TODO marker(s) remain in the stage task file",
                )
            line_count = len(task_text.splitlines())
            if line_count > STAGE_TODO_LINE_WARNING:
                self.add(
                    "WARN",
                    "STAGE_TODO_TOO_LARGE",
                    relative_path,
                    f"stage task file has {line_count} lines; compact completed work into summaries and evidence links",
                )

    def check_registries(self) -> None:
        """Require a registry only after its first concrete object appears."""

        object_locations = {
            "datasets/registry.yaml": self.directory_has_objects("datasets"),
            "models/registry.yaml": self.directory_has_objects("models"),
            "baselines/registry.yaml": self.directory_has_objects("baselines"),
            "experiments/registry.yaml": (
                self.directory_has_objects("experiments/scripts")
                or self.directory_has_run_objects()
            ),
        }
        for relative_path, required_keys in REGISTRY_RULES.items():
            path = self.root / relative_path
            if object_locations[relative_path] and not path.is_file():
                self.add(
                    "ERROR",
                    "REGISTRY_MISSING",
                    relative_path,
                    "create this registry when the first concrete object is added",
                )
                continue
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            active_text = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("#")
            ).strip()
            if not active_text:
                self.add(
                    "ERROR",
                    "REGISTRY_EMPTY",
                    relative_path,
                    "an existing registry must contain at least one real entry",
                )
                continue
            missing = [
                key
                for key in required_keys
                if not re.search(
                    rf"(?m)^\s*(?:-\s*)?{re.escape(key)}\s*:", active_text
                )
            ]
            if missing:
                self.add(
                    "WARN",
                    "REGISTRY_FIELDS_MISSING",
                    relative_path,
                    f"no occurrence found for required field name(s): {', '.join(missing)}",
                )

    def directory_has_objects(self, relative_directory: str) -> bool:
        """Return whether a registry-managed directory has a concrete object."""

        directory = self.root / relative_directory
        if not directory.is_dir():
            return False
        ignored_names = {
            "README.md",
            "registry.yaml",
            ".gitkeep",
            ".DS_Store",
            "__pycache__",
        }
        return any(
            path.name not in ignored_names and not path.name.startswith(".")
            for path in directory.iterdir()
        )

    def directory_has_run_objects(self) -> bool:
        """Return whether at least one concrete run directory exists."""

        runs = self.root / "experiments/runs"
        return runs.is_dir() and any(path.is_dir() for path in runs.iterdir())

    def check_run_records(self) -> None:
        """Validate the minimum evidence files and JSON in every run directory."""

        runs_root = self.root / "experiments/runs"
        if not runs_root.is_dir():
            return
        for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
            relative = run_dir.relative_to(self.root).as_posix()
            metadata_path = run_dir / "metadata.json"
            if not metadata_path.is_file():
                self.add(
                    "ERROR",
                    "RUN_METADATA_MISSING",
                    relative,
                    "run directory is missing metadata.json",
                )
                continue
            metadata = self.read_json(metadata_path, "RUN_METADATA_INVALID")
            if metadata is None:
                continue
            experiment_id = metadata.get("experiment_id")
            if isinstance(experiment_id, str) and re.fullmatch(r"exp-\d{3}", experiment_id):
                self.run_experiment_ids.add(experiment_id)
            else:
                self.add(
                    "ERROR",
                    "RUN_EXPERIMENT_ID_INVALID",
                    relative,
                    "metadata experiment_id must match exp-<nnn>",
                )
            status = metadata.get("status")
            if status not in {"success", "failed"}:
                self.add(
                    "ERROR",
                    "RUN_STATUS_INVALID",
                    relative,
                    "metadata status must be success or failed",
                )
                continue
            self.check_run_resources(metadata, relative)
            required = (
                ("command.txt", "config_snapshot.json", "metrics.json")
                if status == "success"
                else ("run.log",)
            )
            for filename in required:
                if not (run_dir / filename).is_file():
                    self.add(
                        "ERROR",
                        "RUN_EVIDENCE_MISSING",
                        relative,
                        f"{status} run is missing {filename}",
                    )
            if status == "failed" and not metadata.get("failure_reason"):
                self.add(
                    "ERROR",
                    "RUN_FAILURE_REASON_MISSING",
                    relative,
                    "failed run metadata must include failure_reason",
                )
            for filename in ("config_snapshot.json", "metrics.json"):
                path = run_dir / filename
                if path.is_file():
                    self.read_json(path, "RUN_JSON_INVALID")

    def check_run_resources(
        self, metadata: dict[str, object], relative: str
    ) -> None:
        """Validate API/GPU declarations without inspecting credential values."""

        forbidden_keys = {
            "api_key",
            "llm_api_key",
            "openai_api_key",
            "token",
            "password",
        }
        if any(key.lower() in forbidden_keys for key in self.nested_keys(metadata)):
            self.add(
                "ERROR",
                "RUN_SECRET_FIELD_FORBIDDEN",
                relative,
                "metadata contains a forbidden credential field; its value was not displayed",
            )

        resources = metadata.get("resources")
        if not isinstance(resources, dict):
            self.add(
                "ERROR",
                "RUN_RESOURCES_MISSING",
                relative,
                "metadata must declare resources.gpu and resources.api",
            )
            return

        enabled: dict[str, bool] = {}
        required_when_enabled = {
            "gpu": ("device", "framework", "purpose", "local_model"),
            "api": ("protocol", "model", "purpose", "key_environment_variable"),
        }
        for resource_name in ("gpu", "api"):
            resource = resources.get(resource_name)
            if not isinstance(resource, dict):
                self.add(
                    "ERROR",
                    "RUN_RESOURCE_DECLARATION_MISSING",
                    relative,
                    f"resources.{resource_name} must be an object with enabled true or false",
                )
                continue
            is_enabled = resource.get("enabled")
            if not isinstance(is_enabled, bool):
                self.add(
                    "ERROR",
                    "RUN_RESOURCE_ENABLED_INVALID",
                    relative,
                    f"resources.{resource_name}.enabled must be true or false",
                )
                continue
            enabled[resource_name] = is_enabled
            if is_enabled:
                missing = [
                    key
                    for key in required_when_enabled[resource_name]
                    if resource.get(key) is None
                    or resource.get(key) == ""
                    or resource.get(key) == "TODO"
                ]
                if missing:
                    self.add(
                        "ERROR",
                        "RUN_RESOURCE_FIELDS_MISSING",
                        relative,
                        f"enabled {resource_name} resource is missing: {', '.join(missing)}",
                    )
        api = resources.get("api")
        if isinstance(api, dict) and api.get("enabled") is True:
            if api.get("protocol") != "openai-compatible":
                self.add(
                    "ERROR",
                    "RUN_API_PROTOCOL_INVALID",
                    relative,
                    "enabled API resource must use the openai-compatible protocol",
                )
        if enabled.get("gpu") and enabled.get("api"):
            data_flow = resources.get("data_flow")
            if data_flow is None or data_flow == "" or data_flow == "TODO":
                self.add(
                    "ERROR",
                    "RUN_DATA_FLOW_MISSING",
                    relative,
                    "a joint API/GPU run must record resources.data_flow",
                )

    @classmethod
    def nested_keys(cls, value: object) -> set[str]:
        """Collect mapping keys recursively without returning any values."""

        keys: set[str] = set()
        if isinstance(value, dict):
            for key, child in value.items():
                keys.add(str(key))
                keys.update(cls.nested_keys(child))
        elif isinstance(value, list):
            for child in value:
                keys.update(cls.nested_keys(child))
        return keys

    def read_json(self, path: Path, code: str) -> dict[str, object] | None:
        """Read a JSON object and report syntax or top-level type errors."""

        relative = path.relative_to(self.root).as_posix()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            self.add("ERROR", code, relative, "file is not valid UTF-8 JSON")
            return None
        if not isinstance(value, dict):
            self.add("ERROR", code, relative, "top-level JSON value must be an object")
            return None
        return value

    def check_tracked_run_mutations(self) -> None:
        """Detect modifications to tracked historical run evidence using Git."""

        result = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--",
                "experiments/runs",
            ],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.add(
                "WARN",
                "GIT_RUN_CHECK_UNAVAILABLE",
                "experiments/runs",
                "could not inspect tracked run mutations with Git",
            )
            return
        historical_result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", "experiments/runs"],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        if historical_result.returncode != 0:
            self.add(
                "WARN",
                "GIT_RUN_CHECK_UNAVAILABLE",
                "experiments/runs",
                "could not identify historical run evidence from Git HEAD",
            )
            return
        historical_paths = set(historical_result.stdout.splitlines())
        for line in result.stdout.splitlines():
            changed_paths = {item.strip() for item in line[3:].split(" -> ")}
            historical_changed = sorted(
                path
                for path in changed_paths
                if path in historical_paths and path != "experiments/runs/README.md"
            )
            for path in historical_changed:
                self.add(
                    "ERROR",
                    "TRACKED_RUN_MUTATED",
                    path,
                    "tracked historical run evidence has been modified or deleted",
                )

    def check_paper_traceability(self) -> None:
        """Check that paper experiment IDs have corresponding run metadata."""

        for relative_path in ("paper/draft_zh.md", "paper/main.tex"):
            path = self.root / relative_path
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for experiment_id in sorted(set(re.findall(r"\bexp-\d{3}\b", text))):
                if experiment_id not in self.run_experiment_ids:
                    self.add(
                        "ERROR",
                        "PAPER_EXPERIMENT_UNRESOLVED",
                        relative_path,
                        f"{experiment_id} has no corresponding run metadata",
                    )

    def check_suspected_secrets(self) -> None:
        """Scan non-secret repository text files without reading ignored .env files."""

        for path in self.repository_text_files():
            relative = path.relative_to(self.root).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if any(pattern.search(line) for _, pattern in SECRET_PATTERNS):
                    self.add(
                        "ERROR",
                        "SUSPECTED_SECRET",
                        f"{relative}:{line_number}",
                        "line resembles a private key or access token; value is not displayed",
                    )
                assignment = SECRET_ASSIGNMENT.search(line)
                if assignment and not self.is_placeholder(assignment.group(1)):
                    self.add(
                        "ERROR",
                        "SUSPECTED_SECRET_ASSIGNMENT",
                        f"{relative}:{line_number}",
                        "sensitive variable appears to have a non-placeholder value",
                    )
                if DATABASE_CREDENTIAL.search(line):
                    self.add(
                        "ERROR",
                        "SUSPECTED_DATABASE_CREDENTIAL",
                        f"{relative}:{line_number}",
                        "database URL appears to contain embedded credentials",
                    )

    def repository_text_files(self) -> list[Path]:
        """List tracked and visible untracked files while respecting ignore rules."""

        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        paths: list[Path] = []
        for relative in sorted(set(result.stdout.splitlines())):
            if not relative:
                continue
            if Path(relative).name in SKIPPED_SCAN_NAMES:
                self.add(
                    "ERROR",
                    "SECRET_FILE_VISIBLE",
                    relative,
                    "a .env file is tracked or visible to Git; its contents were not read",
                )
                continue
            if relative.startswith(("datasets/", "models/")) and not relative.endswith(
                "/registry.yaml"
            ):
                continue
            if relative.startswith(SKIPPED_SCAN_PREFIXES):
                continue
            path = self.root / relative
            try:
                if not path.is_file() or path.stat().st_size > MAX_SCAN_BYTES:
                    continue
            except OSError:
                continue
            paths.append(path)
        return paths

    @staticmethod
    def is_placeholder(value: str) -> bool:
        """Return whether a configured-looking value is an obvious safe placeholder."""

        normalized = value.strip().lower()
        if not normalized:
            return True
        if normalized in {"todo", "changeme", "replace-me", "placeholder"}:
            return True
        if normalized.startswith(("<", "your-", "your_")):
            return True
        return re.fullmatch(r"(?:sk-)?x{3,}", normalized) is not None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Validate a Codex research workspace without modifying it."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help="repository root to validate (default: parent of scripts/)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return a non-zero status when warnings are present",
    )
    return parser.parse_args()


def main() -> int:
    """Run validation and return a shell-friendly status code."""

    args = parse_args()
    validator = WorkspaceValidator(args.root)
    findings = validator.validate()
    for finding in findings:
        print(
            f"[{finding.severity}] {finding.code} {finding.path}: {finding.message}"
        )
    errors = sum(item.severity == "ERROR" for item in findings)
    warnings = sum(item.severity == "WARN" for item in findings)
    infos = sum(item.severity == "INFO" for item in findings)
    print(
        f"Validation complete: {errors} error(s), {warnings} warning(s), "
        f"{infos} info message(s)."
    )
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
