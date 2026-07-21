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
from datetime import date, datetime, timezone
from pathlib import Path


REQUIRED_PATHS = (
    "README.md",
    "AGENTS.md",
    "RESEARCH.md",
    "research/README.md",
    "research/search_log.jsonl",
    "research/sources.yaml",
    "research/claims.yaml",
    "research/decisions.yaml",
    "research/summaries/README.md",
    "experiments/TODO.md",
    "paper/TODO.md",
    ".env.example",
    "docs/README.md",
    "docs/TEMPLATE_BOUNDARIES.md",
    "docs/WORKFLOW_GATES.md",
    "docs/PHASE_ONE_PROTOCOL.md",
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
    "tests/README.md",
    "tests/test_validate_workspace.py",
)

VALID_PHASES = {
    "阶段一：调研与设计",
    "阶段二：实验与分析",
    "阶段三：论文写作",
}
VALID_PHASE_STATUSES = {"未开始", "进行中", "已暂停", "已完成"}
VALID_GATE_RESULTS = {"待检查", "未通过", "已通过", "不适用"}
VALID_PHASE_ONE_STATES = {
    "INTAKE",
    "DIVERGE",
    "SEARCH",
    "COMPARE",
    "DRAFT",
    "CONFIRM",
    "GATE_CHECK",
}
VALID_CONFIRMATION_STATUSES = {
    "已确认",
    "暂定",
    "待确认",
    "存在冲突",
    "不适用",
}
BLOCKING_CONFIRMATION_STATUSES = {"暂定", "待确认", "存在冲突"}
REQUIRED_CONTRACT_FIELDS = {
    "研究目标",
    "研究问题",
    "成功标准",
    "数据、baseline 与评测",
    "数据与隐私边界",
    "计算与外部服务",
    "约束与预算",
    "Skills、依赖与授权",
    "范围外事项",
}
PLACEHOLDER_CELLS = {"", "-", "TODO", "待分配"}
RESEARCH_ID_DEFINITIONS = (
    ("未决问题 ID", "问题", re.compile(r"OPEN-\d{3}")),
    ("研究问题 ID", "当前值", re.compile(r"RQ-\d{3}")),
    ("贡献 ID", "当前值", re.compile(r"CONTRIB-\d{3}")),
    ("成功标准 ID", "当前值", re.compile(r"SC-\d{3}")),
    ("数据 ID", "来源、版本与许可证", re.compile(r"DATA-\d{3}")),
    ("baseline ID", "上游版本或 revision", re.compile(r"BASE-\d{3}")),
    ("指标 ID", "当前值与统计口径", re.compile(r"METRIC-\d{3}")),
    ("授权 ID", "授权事项", re.compile(r"AUTH-\d{3}")),
    ("主张 ID", "摘要", re.compile(r"CLM-\d{3}")),
    ("来源 ID", "最小引用信息或 URL", re.compile(r"SRC-\d{3}")),
    ("决策 ID", "决策", re.compile(r"DEC-\d{3}")),
    ("切换 ID", "原阶段", re.compile(r"TRANS-\d{3}")),
)
EVIDENCE_REQUIRED_FIELDS = {
    "sources": {
        "source_id",
        "title",
        "creators",
        "url",
        "doi_or_identifier",
        "published_at",
        "accessed_at",
        "source_type",
        "provenance_level",
        "version",
        "license",
        "data_classification",
        "contains_restricted_content",
        "external_transfer_allowed",
        "accessibility_status",
        "update_retraction_conflict_status",
        "notes",
    },
    "claims": {
        "claim_id",
        "claim",
        "research_question_ids",
        "source_ids",
        "evidence_locations",
        "support_level",
        "source_independence",
        "temporal_status",
        "conflict_status",
        "verification_status",
        "eligible_for_research_contract",
    },
    "decisions": {
        "decision_id",
        "decision",
        "user_input_source",
        "supporting_claim_ids",
        "alternatives",
        "rejection_reasons",
        "user_confirmation_status",
        "affected_contract_fields",
        "triggers_phase_rollback",
        "decided_at",
    },
}
SEARCH_LOG_REQUIRED_FIELDS = {
    "query_id",
    "research_question_ids",
    "query",
    "language",
    "platform",
    "searched_at",
    "filters",
    "result_count",
    "included_source_ids",
    "exclusions",
    "counterevidence_search",
}
VALID_SUPPORT_LEVELS = {
    "直接支持",
    "部分支持",
    "间接推论",
    "不支持",
    "来源冲突",
}
VALID_PROVENANCE_LEVELS = {"原始来源", "二手来源"}
VALID_ACCESSIBILITY_STATUSES = {"可访问", "部分可访问", "不可访问", "待复查"}
VALID_SOURCE_LIFECYCLE_STATUSES = {
    "无已知问题",
    "存在更新",
    "已撤回",
    "存在冲突",
    "待复查",
}
VALID_DATA_CLASSIFICATIONS = {"公开", "内部", "受限", "个人信息", "混合"}
VALID_SOURCE_INDEPENDENCE = {"独立", "部分独立", "同源", "待核验"}
VALID_TEMPORAL_STATUSES = {"当前有效", "可能过期", "已过期", "待核验"}
VALID_CONFLICT_STATUSES = {"无已知冲突", "存在冲突", "待核验"}
VALID_VERIFICATION_STATUSES = {"已核验", "部分核验", "待核验", "无法核验"}
STAGE_TODO_PATHS = {
    "阶段二：实验与分析": "experiments/TODO.md",
    "阶段三：论文写作": "paper/TODO.md",
}
STAGE_TODO_LINE_WARNING = 500
RESEARCH_LINE_WARNING = 600
RESEARCH_BYTE_WARNING = 100_000
SEARCH_STALE_DAYS = 180
CODEX_TENTATIVE_RATIO_WARNING = 0.5
FORBIDDEN_EVIDENCE_FIELD_NAMES = {
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}
FORBIDDEN_EVIDENCE_CONTENT_FIELDS = {
    "document_content",
    "full_text",
    "ocr_fulltext",
    "personal_data",
    "prompt_content",
    "raw_content",
    "raw_sample",
    "response_content",
    "sensitive_sample",
    "transcript",
}
EVIDENCE_TEXT_LIMITS = {
    "claim": 1_500,
    "decision": 2_000,
    "notes": 2_000,
    "query": 1_000,
    "title": 500,
    "user_input_source": 500,
}
MAX_EVIDENCE_STRING_LENGTH = 4_000
PERSONAL_DATA_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
)

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
        "research_question_ids",
        "success_criterion_ids",
        "decision_ids",
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
        self.check_research_contract(phase, status)
        self.check_phase_one_evidence(phase, status)
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
        phase_one_state = self.extract_field(text, "阶段一子状态")
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
        if phase_one_state not in VALID_PHASE_ONE_STATES:
            self.add(
                "ERROR",
                "INVALID_PHASE_ONE_STATE",
                "RESEARCH.md",
                f"phase-one state must be one of {sorted(VALID_PHASE_ONE_STATES)}",
            )
        if (
            phase in {"阶段二：实验与分析", "阶段三：论文写作"}
            or (phase == "阶段一：调研与设计" and status == "已完成")
        ) and phase_one_state != "GATE_CHECK":
            self.add(
                "ERROR",
                "PHASE_ONE_STATE_NOT_GATE_CHECK",
                "RESEARCH.md",
                "stage one must reach GATE_CHECK before completion or transition",
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
        research_count = self.count_todo_markers(research_path.read_text("utf-8"))

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
            task_count = self.count_todo_markers(task_text)
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

    @staticmethod
    def count_todo_markers(text: str) -> int:
        """Count standalone placeholders without treating paths such as TODO.md as gaps."""

        return len(re.findall(r"(?<![/\.\w])TODO(?![/\.\w])", text))

    def check_research_contract(
        self, phase: str | None, status: str | None
    ) -> None:
        """Validate phase-one confirmation, stable IDs, and contract relations."""

        path = self.root / "RESEARCH.md"
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        tables = self.parse_markdown_tables(text)
        transition_ready = phase in {
            "阶段二：实验与分析",
            "阶段三：论文写作",
        } or status == "已完成"

        prohibited_headings = re.findall(
            r"(?m)^#{2,6}\s+(搜索流水账|网页全文|论文全文|命令输出|调试日志|实验日志)\s*$",
            text,
        )
        for heading in prohibited_headings:
            self.add(
                "ERROR",
                "RESEARCH_DETAIL_SECTION_FORBIDDEN",
                "RESEARCH.md",
                f"detailed {heading} content must not be stored in the research contract",
            )

        contract_table = next(
            (
                rows
                for headers, rows in tables
                if "合同字段" in headers and "确认状态" in headers
            ),
            None,
        )
        if contract_table is None:
            self.add(
                "ERROR",
                "RESEARCH_CONTRACT_STATUS_MISSING",
                "RESEARCH.md",
                "research contract must contain a field-level confirmation table",
            )
        else:
            present_fields = {
                row.get("合同字段", "")
                for row in contract_table
                if row.get("合同字段", "") not in PLACEHOLDER_CELLS
            }
            missing_fields = sorted(REQUIRED_CONTRACT_FIELDS - present_fields)
            if missing_fields:
                self.add(
                    "ERROR",
                    "RESEARCH_CONTRACT_FIELDS_MISSING",
                    "RESEARCH.md",
                    f"contract status table is missing: {', '.join(missing_fields)}",
                )
            for row in contract_table:
                field = row.get("合同字段", "")
                confirmation = row.get("确认状态", "")
                current_value = row.get("当前值或引用", "")
                if confirmation not in VALID_CONFIRMATION_STATUSES:
                    self.add(
                        "ERROR",
                        "RESEARCH_CONFIRMATION_STATUS_INVALID",
                        "RESEARCH.md",
                        f"{field or 'contract field'} has an invalid confirmation status",
                    )
                if transition_ready and confirmation in BLOCKING_CONFIRMATION_STATUSES:
                    self.add(
                        "ERROR",
                        "RESEARCH_CONFIRMATION_BLOCKING",
                        "RESEARCH.md",
                        f"{field} remains {confirmation} after phase-one intake",
                    )
                if transition_ready and row.get("当前值或引用", "") in PLACEHOLDER_CELLS:
                    self.add(
                        "ERROR",
                        "RESEARCH_CONTRACT_VALUE_MISSING",
                        "RESEARCH.md",
                        f"{field} has no current value or stable-ID reference",
                    )
                if confirmation == "已确认":
                    confirmed_at = row.get("最近确认日期或轮次", "")
                    decision_id = row.get("决策 ID", "")
                    if confirmed_at in PLACEHOLDER_CELLS:
                        self.add(
                            "ERROR",
                            "RESEARCH_CONFIRMATION_DATE_MISSING",
                            "RESEARCH.md",
                            f"{field} is confirmed without a date or conversation turn",
                        )
                    if not re.search(r"DEC-\d{3}", decision_id):
                        self.add(
                            "ERROR",
                            "RESEARCH_CONFIRMATION_DECISION_MISSING",
                            "RESEARCH.md",
                            f"{field} is confirmed without a DEC-<nnn> reference",
                        )
                if confirmation == "不适用" and not self.has_not_applicable_reason(
                    current_value
                ):
                    self.add(
                        "ERROR",
                        "RESEARCH_NOT_APPLICABLE_REASON_MISSING",
                        "RESEARCH.md",
                        f"{field} is not applicable but has no explicit reason",
                    )

            tentative_codex = [
                row
                for row in contract_table
                if "Codex" in row.get("信息来源", "")
                and row.get("确认状态") in {"暂定", "待确认"}
            ]
            meaningful_rows = [
                row
                for row in contract_table
                if row.get("合同字段", "") not in PLACEHOLDER_CELLS
            ]
            if (
                len(tentative_codex) >= 3
                and meaningful_rows
                and len(tentative_codex) / len(meaningful_rows)
                >= CODEX_TENTATIVE_RATIO_WARNING
            ):
                self.add(
                    "WARN",
                    "RESEARCH_CODEX_TENTATIVE_RATIO_HIGH",
                    "RESEARCH.md",
                    "a high proportion of contract fields remain tentative Codex proposals",
                )

        for headers, rows in tables:
            for status_column in ("确认状态", "用户确认状态", "关系状态"):
                if status_column not in headers:
                    continue
                for row in rows:
                    value = row.get(status_column, "")
                    if value not in VALID_CONFIRMATION_STATUSES:
                        self.add(
                            "ERROR",
                            "RESEARCH_CONFIRMATION_STATUS_INVALID",
                            "RESEARCH.md",
                            f"{status_column} contains an unsupported value",
                        )
                    if (
                        transition_ready
                        and "合同字段" not in headers
                        and value in BLOCKING_CONFIRMATION_STATUSES
                    ):
                        self.add(
                            "ERROR",
                            "RESEARCH_CONFIRMATION_BLOCKING",
                            "RESEARCH.md",
                            f"a detailed contract row remains {value} after phase-one intake",
                        )
                    if value == "已确认" and "最近确认日期或轮次" in headers:
                        if row.get("最近确认日期或轮次", "") in PLACEHOLDER_CELLS:
                            self.add(
                                "ERROR",
                                "RESEARCH_CONFIRMATION_DATE_MISSING",
                                "RESEARCH.md",
                                "a confirmed detailed contract row lacks a date or conversation turn",
                            )
                        if "决策 ID" in headers and not re.search(
                            r"DEC-\d{3}", row.get("决策 ID", "")
                        ):
                            self.add(
                                "ERROR",
                                "RESEARCH_CONFIRMATION_DECISION_MISSING",
                                "RESEARCH.md",
                                "a confirmed detailed contract row lacks a DEC-<nnn> reference",
                            )

            if {"授权 ID", "状态", "用户确认日期或轮次"}.issubset(headers):
                for row in rows:
                    auth_id = row.get("授权 ID", "")
                    auth_status = row.get("状态", "")
                    if auth_id in PLACEHOLDER_CELLS:
                        if transition_ready and auth_status in BLOCKING_CONFIRMATION_STATUSES:
                            self.add(
                                "ERROR",
                                "RESEARCH_AUTHORIZATION_BLOCKING",
                                "RESEARCH.md",
                                "authorization requirements remain unresolved at stage transition",
                            )
                        continue
                    if not re.fullmatch(r"AUTH-\d{3}", auth_id):
                        self.add(
                            "ERROR",
                            "RESEARCH_AUTHORIZATION_ID_INVALID",
                            "RESEARCH.md",
                            "authorization ID must match AUTH-<nnn>",
                        )
                    if auth_status not in VALID_CONFIRMATION_STATUSES:
                        self.add(
                            "ERROR",
                            "RESEARCH_AUTHORIZATION_STATUS_INVALID",
                            "RESEARCH.md",
                            "authorization status is unsupported",
                        )
                    elif transition_ready and auth_status in BLOCKING_CONFIRMATION_STATUSES:
                        self.add(
                            "ERROR",
                            "RESEARCH_AUTHORIZATION_BLOCKING",
                            "RESEARCH.md",
                            f"{auth_id} remains {auth_status} at stage transition",
                        )
                    if auth_status == "已确认":
                        if row.get("用户确认日期或轮次", "") in PLACEHOLDER_CELLS:
                            self.add(
                                "ERROR",
                                "RESEARCH_AUTHORIZATION_DATE_MISSING",
                                "RESEARCH.md",
                                f"{auth_id} is confirmed without a date or conversation turn",
                            )
                        if not re.search(r"DEC-\d{3}", row.get("关联决策 ID", "")):
                            self.add(
                                "ERROR",
                                "RESEARCH_AUTHORIZATION_DECISION_MISSING",
                                "RESEARCH.md",
                                f"{auth_id} is confirmed without an associated decision",
                            )

        self.check_research_recovery(text, phase, status, transition_ready)
        self.check_research_contract_quality(text, tables, transition_ready)

        definitions: dict[str, set[str]] = {}
        for id_column, signature_column, pattern in RESEARCH_ID_DEFINITIONS:
            matching_rows = [
                row
                for headers, rows in tables
                if id_column in headers and signature_column in headers
                for row in rows
            ]
            seen: set[str] = set()
            definitions[id_column] = seen
            for row in matching_rows:
                value = row.get(id_column, "")
                if value in PLACEHOLDER_CELLS or value == "不适用":
                    continue
                if not pattern.fullmatch(value):
                    self.add(
                        "ERROR",
                        "RESEARCH_ID_INVALID",
                        "RESEARCH.md",
                        f"{id_column} value must match {pattern.pattern}",
                    )
                    continue
                if value in seen:
                    self.add(
                        "ERROR",
                        "RESEARCH_ID_DUPLICATE",
                        "RESEARCH.md",
                        f"{value} is defined more than once",
                    )
                seen.add(value)

        if transition_ready:
            self.check_contract_relations(tables, definitions)
            self.check_experiment_task_relations(definitions)

    @staticmethod
    def has_not_applicable_reason(value: str) -> bool:
        """Return whether an N/A value includes a human-readable reason."""

        normalized = value.strip()
        return bool(
            re.match(r"^不适用\s*[：:(（]", normalized)
            and len(re.sub(r"^不适用\s*[：:(（]\s*", "", normalized).strip("）) "))
            >= 2
        )

    def check_research_recovery(
        self,
        text: str,
        phase: str | None,
        status: str | None,
        transition_ready: bool,
    ) -> None:
        """Check that a new session can resume without the chat transcript."""

        labels = (
            "最近交接日期或轮次",
            "本轮已确认事项",
            "本轮否决方案",
            "当前暂定假设",
            "新增证据",
            "未解决问题",
            "下一轮首要任务",
            "不应重新采用的旧方案",
        )
        missing = [
            label
            for label in labels
            if self.extract_field(text, label) in {None, "", "TODO"}
            or str(self.extract_field(text, label)).startswith("TODO（")
        ]
        if not missing:
            return
        if transition_ready:
            severity = "ERROR"
        elif phase == "阶段一：调研与设计" and status in {"进行中", "已暂停"}:
            severity = "WARN"
        else:
            severity = "INFO"
        self.add(
            severity,
            "RESEARCH_RECOVERY_INCOMPLETE",
            "RESEARCH.md",
            f"session recovery summary is incomplete: {', '.join(missing)}",
        )

    def check_research_contract_quality(
        self,
        text: str,
        tables: list[tuple[list[str], list[dict[str, str]]]],
        transition_ready: bool,
    ) -> None:
        """Check structural quality that can be assessed without scientific judgment."""

        line_count = len(text.splitlines())
        byte_count = len(text.encode("utf-8"))
        if line_count > RESEARCH_LINE_WARNING or byte_count > RESEARCH_BYTE_WARNING:
            self.add(
                "WARN",
                "RESEARCH_CONTRACT_TOO_LARGE",
                "RESEARCH.md",
                f"research contract is large ({line_count} lines, {byte_count} bytes); move detailed process into research/",
            )

        external_api = self.extract_field(text, "外部模型 API") or ""
        transfer = self.extract_field(text, "外部 API 传输") or ""
        external_api_is_explicit = (
            external_api not in PLACEHOLDER_CELLS
            and not external_api.startswith(("TODO", "不适用"))
        )
        transfer_is_allowed = "允许" in transfer and "不允许" not in transfer
        if external_api_is_explicit and transfer_is_allowed:
            confirmed_external_authorization = any(
                row.get("状态") == "已确认"
                and re.fullmatch(r"AUTH-\d{3}", row.get("授权 ID", ""))
                and any(
                    term in f"{row.get('授权事项', '')} {row.get('范围', '')}"
                    for term in ("外发", "外部 API", "传输")
                )
                for headers, rows in tables
                if {"授权 ID", "授权事项", "范围", "状态"}.issubset(headers)
                for row in rows
            )
            if not confirmed_external_authorization:
                self.add(
                    "ERROR",
                    "RESEARCH_API_TRANSFER_AUTHORIZATION_MISSING",
                    "RESEARCH.md",
                    "allowed external API transfer requires a scoped confirmed AUTH-<nnn>",
                )

        if not transition_ready:
            return

        baseline_rows = [
            row
            for headers, rows in tables
            if "baseline ID" in headers and "当前值" in headers
            for row in rows
            if re.fullmatch(r"BASE-\d{3}", row.get("baseline ID", ""))
        ]
        if not baseline_rows or any(
            row.get("当前值", "") in PLACEHOLDER_CELLS for row in baseline_rows
        ):
            self.add(
                "ERROR",
                "RESEARCH_BASELINE_MISSING",
                "RESEARCH.md",
                "confirmed research questions require a non-empty baseline definition",
            )

        vague_success = {"较好", "提升", "有效", "达到预期", "显著提升", "性能提升"}
        success_rows = [
            row
            for headers, rows in tables
            if "成功标准 ID" in headers and "当前值" in headers
            for row in rows
            if re.fullmatch(r"SC-\d{3}", row.get("成功标准 ID", ""))
        ]
        for row in success_rows:
            value = row.get("当前值", "").strip()
            if value in vague_success or len(value) < 8:
                self.add(
                    "WARN",
                    "RESEARCH_SUCCESS_CRITERION_VAGUE",
                    "RESEARCH.md",
                    f"{row.get('成功标准 ID')} may not define a verifiable rule or threshold",
                )

        for label in (
            "最大 GPU 时间",
            "最大 API 调用次数",
            "最大外部 API 预算",
            "截止日期",
        ):
            value = self.extract_field(text, label)
            if value is None or value in PLACEHOLDER_CELLS or value.startswith("TODO"):
                self.add(
                    "ERROR",
                    "RESEARCH_BUDGET_FIELD_MISSING",
                    "RESEARCH.md",
                    f"{label} must be explicit before stage two",
                )
            elif value.startswith("不适用") and not self.has_not_applicable_reason(value):
                self.add(
                    "ERROR",
                    "RESEARCH_NOT_APPLICABLE_REASON_MISSING",
                    "RESEARCH.md",
                    f"{label} is not applicable but has no explicit reason",
                )

        if external_api.startswith("不适用"):
            if not self.has_not_applicable_reason(external_api):
                self.add(
                    "ERROR",
                    "RESEARCH_NOT_APPLICABLE_REASON_MISSING",
                    "RESEARCH.md",
                    "external API is not applicable but has no explicit reason",
                )
        else:
            for label in ("API 用途", "API 模型", "API 与 GPU 分工及数据流"):
                value = self.extract_field(text, label)
                if value is None or value in PLACEHOLDER_CELLS or value.startswith("TODO"):
                    self.add(
                        "ERROR",
                        "RESEARCH_API_FLOW_FIELD_MISSING",
                        "RESEARCH.md",
                        f"{label} must be explicit when an external API is planned",
                    )
            if not any(word in transfer for word in ("允许", "不允许")):
                self.add(
                    "ERROR",
                    "RESEARCH_API_TRANSFER_UNCLEAR",
                    "RESEARCH.md",
                    "external API transfer must explicitly state allowed or not allowed",
                )

        gpu_purpose = self.extract_field(text, "GPU 用途") or ""
        if gpu_purpose.startswith("不适用"):
            if not self.has_not_applicable_reason(gpu_purpose):
                self.add(
                    "ERROR",
                    "RESEARCH_NOT_APPLICABLE_REASON_MISSING",
                    "RESEARCH.md",
                    "GPU use is not applicable but has no explicit reason",
                )
        else:
            local_resources = self.extract_field(text, "本地计算资源") or ""
            if (
                gpu_purpose in PLACEHOLDER_CELLS
                or gpu_purpose.startswith("TODO")
                or local_resources in PLACEHOLDER_CELLS
                or local_resources.startswith("TODO")
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_GPU_FLOW_FIELD_MISSING",
                    "RESEARCH.md",
                    "GPU purpose and local resource details must be explicit when GPU use is planned",
                )

    def check_contract_relations(
        self,
        tables: list[tuple[list[str], list[dict[str, str]]]],
        definitions: dict[str, set[str]],
    ) -> None:
        """Require complete RQ-to-experiment mappings after phase one."""

        relation_rows = [
            row
            for headers, rows in tables
            if {
                "研究问题 ID",
                "数据 ID",
                "baseline ID",
                "指标 ID",
                "成功标准 ID",
                "阶段二实验 ID",
                "关系状态",
            }.issubset(headers)
            for row in rows
        ]
        if not relation_rows:
            self.add(
                "ERROR",
                "RESEARCH_RELATION_MISSING",
                "RESEARCH.md",
                "at least one confirmed research-question relation is required",
            )
            return

        relation_patterns = {
            "研究问题 ID": re.compile(r"RQ-\d{3}"),
            "数据 ID": re.compile(r"DATA-\d{3}"),
            "baseline ID": re.compile(r"BASE-\d{3}"),
            "指标 ID": re.compile(r"METRIC-\d{3}"),
            "成功标准 ID": re.compile(r"SC-\d{3}"),
            "阶段二实验 ID": re.compile(r"exp-\d{3}"),
        }
        definition_columns = {
            "研究问题 ID": "研究问题 ID",
            "数据 ID": "数据 ID",
            "baseline ID": "baseline ID",
            "指标 ID": "指标 ID",
            "成功标准 ID": "成功标准 ID",
        }
        mapped_rqs: set[str] = set()
        mapped_metrics: set[str] = set()
        mapped_success_criteria: set[str] = set()
        for row in relation_rows:
            if row.get("关系状态") != "已确认":
                self.add(
                    "ERROR",
                    "RESEARCH_RELATION_UNCONFIRMED",
                    "RESEARCH.md",
                    "all phase-two research relations must be confirmed",
                )
            for column, pattern in relation_patterns.items():
                value = row.get(column, "")
                if not pattern.fullmatch(value):
                    self.add(
                        "ERROR",
                        "RESEARCH_RELATION_ID_INVALID",
                        "RESEARCH.md",
                        f"{column} must match {pattern.pattern}",
                    )
                    continue
                definition_column = definition_columns.get(column)
                if definition_column and value not in definitions.get(
                    definition_column, set()
                ):
                    self.add(
                        "ERROR",
                        "RESEARCH_RELATION_TARGET_MISSING",
                        "RESEARCH.md",
                        f"{value} has no definition in the current contract",
                    )
            rq_id = row.get("研究问题 ID", "")
            if re.fullmatch(r"RQ-\d{3}", rq_id):
                mapped_rqs.add(rq_id)
            metric_id = row.get("指标 ID", "")
            if re.fullmatch(r"METRIC-\d{3}", metric_id):
                mapped_metrics.add(metric_id)
            success_id = row.get("成功标准 ID", "")
            if re.fullmatch(r"SC-\d{3}", success_id):
                mapped_success_criteria.add(success_id)

        for rq_id in sorted(definitions.get("研究问题 ID", set()) - mapped_rqs):
            self.add(
                "ERROR",
                "RESEARCH_QUESTION_UNMAPPED",
                "RESEARCH.md",
                f"{rq_id} has no data-baseline-metric-success-experiment relation",
            )
        for metric_id in sorted(definitions.get("指标 ID", set()) - mapped_metrics):
            self.add(
                "ERROR",
                "RESEARCH_METRIC_UNMAPPED",
                "RESEARCH.md",
                f"{metric_id} is not connected to a planned experiment relation",
            )
        for success_id in sorted(
            definitions.get("成功标准 ID", set()) - mapped_success_criteria
        ):
            self.add(
                "ERROR",
                "RESEARCH_SUCCESS_CRITERION_UNMAPPED",
                "RESEARCH.md",
                f"{success_id} is not connected to a planned experiment",
            )

        data_ids = definitions.get("数据 ID", set())
        metric_rows = [
            row
            for headers, rows in tables
            if "指标 ID" in headers and "所需数据 ID" in headers
            for row in rows
        ]
        for row in metric_rows:
            metric_id = row.get("指标 ID", "")
            if metric_id in PLACEHOLDER_CELLS:
                continue
            required_data_id = row.get("所需数据 ID", "")
            if required_data_id not in data_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_METRIC_DATA_MISSING",
                    "RESEARCH.md",
                    f"{metric_id} does not reference defined required data",
                )

        rq_ids = definitions.get("研究问题 ID", set())
        success_rows = [
            row
            for headers, rows in tables
            if "成功标准 ID" in headers and "关联研究问题 ID" in headers
            for row in rows
        ]
        for row in success_rows:
            success_id = row.get("成功标准 ID", "")
            if success_id in PLACEHOLDER_CELLS:
                continue
            rq_id = row.get("关联研究问题 ID", "")
            if rq_id not in rq_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_SUCCESS_QUESTION_MISSING",
                    "RESEARCH.md",
                    f"{success_id} does not reference a defined research question",
                )

        baseline_ids = definitions.get("baseline ID", set())
        contribution_rows = [
            row
            for headers, rows in tables
            if "贡献 ID" in headers and "比较 baseline ID" in headers
            for row in rows
        ]
        for row in contribution_rows:
            contribution_id = row.get("贡献 ID", "")
            if contribution_id in PLACEHOLDER_CELLS:
                continue
            baseline_id = row.get("比较 baseline ID", "")
            if baseline_id not in baseline_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_CONTRIBUTION_BASELINE_MISSING",
                    "RESEARCH.md",
                    f"{contribution_id} does not reference a defined baseline",
                )

    def check_experiment_task_relations(
        self, definitions: dict[str, set[str]]
    ) -> None:
        """Check that stage-two task rows reference confirmed contract IDs."""

        path = self.root / "experiments/TODO.md"
        if not path.is_file():
            return
        tables = self.parse_markdown_tables(path.read_text(encoding="utf-8"))
        rows = [
            row
            for headers, table_rows in tables
            if {"实验 ID", "研究问题 ID", "成功标准 ID"}.issubset(headers)
            for row in table_rows
        ]
        if not rows:
            self.add(
                "ERROR",
                "EXPERIMENT_CONTRACT_LINK_MISSING",
                "experiments/TODO.md",
                "stage-two tasks must reference research questions and success criteria",
            )
            return
        rq_ids = definitions.get("研究问题 ID", set())
        success_ids = definitions.get("成功标准 ID", set())
        for row in rows:
            experiment_id = row.get("实验 ID", "")
            if not re.fullmatch(r"exp-\d{3}", experiment_id):
                self.add(
                    "ERROR",
                    "EXPERIMENT_ID_INVALID",
                    "experiments/TODO.md",
                    "experiment ID must match exp-<nnn>",
                )
            if row.get("研究问题 ID", "") not in rq_ids:
                self.add(
                    "ERROR",
                    "EXPERIMENT_RESEARCH_QUESTION_MISSING",
                    "experiments/TODO.md",
                    "stage-two task references an undefined research question",
                )
            if row.get("成功标准 ID", "") not in success_ids:
                self.add(
                    "ERROR",
                    "EXPERIMENT_SUCCESS_CRITERION_MISSING",
                    "experiments/TODO.md",
                    "stage-two task references an undefined success criterion",
                )

    @staticmethod
    def parse_markdown_tables(
        text: str,
    ) -> list[tuple[list[str], list[dict[str, str]]]]:
        """Parse simple pipe-delimited Markdown tables without external packages."""

        lines = text.splitlines()
        tables: list[tuple[list[str], list[dict[str, str]]]] = []
        index = 0
        separator = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$")
        while index + 1 < len(lines):
            header_line = lines[index].strip()
            if not header_line.startswith("|") or not separator.match(
                lines[index + 1]
            ):
                index += 1
                continue
            headers = [cell.strip() for cell in header_line.strip("|").split("|")]
            index += 2
            rows: list[dict[str, str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [
                    cell.strip()
                    for cell in lines[index].strip().strip("|").split("|")
                ]
                if len(cells) == len(headers):
                    rows.append(dict(zip(headers, cells)))
                index += 1
            tables.append((headers, rows))
        return tables

    def check_phase_one_evidence(
        self, phase: str | None, status: str | None
    ) -> None:
        """Validate phase-one search, source, claim, and decision evidence."""

        transition_ready = phase in {
            "阶段二：实验与分析",
            "阶段三：论文写作",
        } or status == "已完成"
        research_path = self.root / "RESEARCH.md"
        research_text = (
            research_path.read_text(encoding="utf-8")
            if research_path.is_file()
            else ""
        )
        research_tables = self.parse_markdown_tables(research_text)
        contract_ids = self.collect_research_definition_ids(research_tables)

        sources = self.read_flat_yaml_registry(
            "research/sources.yaml", "sources", "source_id"
        )
        claims = self.read_flat_yaml_registry(
            "research/claims.yaml", "claims", "claim_id"
        )
        decisions = self.read_flat_yaml_registry(
            "research/decisions.yaml", "decisions", "decision_id"
        )
        if sources is None or claims is None or decisions is None:
            return

        source_ids = self.validate_source_evidence(sources)
        claim_ids, eligible_claim_ids = self.validate_claim_evidence(
            claims,
            source_ids,
            contract_ids.get("研究问题 ID", set()),
            transition_ready,
        )
        decision_ids = self.validate_decision_evidence(
            decisions,
            claim_ids,
            transition_ready,
        )
        search_entries = self.validate_search_log(
            source_ids,
            contract_ids.get("研究问题 ID", set()),
            transition_ready,
        )
        self.check_phase_one_evidence_quality(
            sources,
            claims,
            search_entries,
            phase,
            status,
            transition_ready,
        )

        if transition_ready:
            registry_sets = {
                "来源 ID": source_ids,
                "主张 ID": claim_ids,
                "决策 ID": decision_ids,
            }
            for definition_column, registry_ids in registry_sets.items():
                for stable_id in sorted(
                    contract_ids.get(definition_column, set()) - registry_ids
                ):
                    self.add(
                        "ERROR",
                        "RESEARCH_EVIDENCE_DEFINITION_UNRESOLVED",
                        "RESEARCH.md",
                        f"{stable_id} has no detailed entry in research evidence",
                    )
            for claim_id in sorted(
                contract_ids.get("主张 ID", set()) - eligible_claim_ids
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_CONTRACT_CLAIM_INELIGIBLE",
                    "RESEARCH.md",
                    f"{claim_id} is not verified and eligible for the research contract",
                )
            self.validate_contract_evidence_references(
                research_tables, source_ids, claim_ids, decision_ids
            )

    @staticmethod
    def collect_research_definition_ids(
        tables: list[tuple[list[str], list[dict[str, str]]]],
    ) -> dict[str, set[str]]:
        """Collect well-formed stable IDs from RESEARCH.md definition tables."""

        collected: dict[str, set[str]] = {}
        for id_column, signature_column, pattern in RESEARCH_ID_DEFINITIONS:
            collected[id_column] = {
                row.get(id_column, "")
                for headers, rows in tables
                if id_column in headers and signature_column in headers
                for row in rows
                if pattern.fullmatch(row.get(id_column, ""))
            }
        return collected

    def read_flat_yaml_registry(
        self, relative_path: str, collection: str, id_field: str
    ) -> list[dict[str, object]] | None:
        """Read the documented flat, JSON-scalar YAML subset without dependencies."""

        path = self.root / relative_path
        if not path.is_file():
            return None
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_YAML_INVALID",
                relative_path,
                "evidence registry is not valid UTF-8 text",
            )
            return None
        if not any(re.fullmatch(r"\s*schema_version:\s*1\s*", line) for line in lines):
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_SCHEMA_VERSION_MISSING",
                relative_path,
                "evidence registry must declare schema_version: 1",
            )
        empty_collection = re.compile(rf"\s*{re.escape(collection)}:\s*\[\]\s*")
        if any(empty_collection.fullmatch(line) for line in lines):
            return []
        collection_index = next(
            (
                index
                for index, line in enumerate(lines)
                if re.fullmatch(rf"\s*{re.escape(collection)}:\s*", line)
            ),
            None,
        )
        if collection_index is None:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_COLLECTION_MISSING",
                relative_path,
                f"evidence registry must contain {collection}",
            )
            return None

        entries: list[dict[str, object]] = []
        current: dict[str, object] | None = None
        field_pattern = re.compile(r"^\s{4}([a-z][a-z0-9_]*)\s*:\s*(.*)$")
        first_field_pattern = re.compile(
            rf"^\s{{2}}-\s+({re.escape(id_field)})\s*:\s*(.*)$"
        )
        for line_number, line in enumerate(
            lines[collection_index + 1 :], start=collection_index + 2
        ):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            first_match = first_field_pattern.fullmatch(line)
            if first_match:
                if current is not None:
                    entries.append(current)
                current = {
                    first_match.group(1): self.decode_yaml_scalar(
                        first_match.group(2)
                    )
                }
                continue
            field_match = field_pattern.fullmatch(line)
            if field_match and current is not None:
                key = field_match.group(1)
                if key in current:
                    self.add(
                        "ERROR",
                        "RESEARCH_EVIDENCE_FIELD_DUPLICATE",
                        relative_path,
                        f"line {line_number} repeats field {key}",
                    )
                current[key] = self.decode_yaml_scalar(field_match.group(2))
                continue
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_YAML_UNSUPPORTED",
                relative_path,
                f"line {line_number} is outside the documented flat YAML subset",
            )
        if current is not None:
            entries.append(current)
        return entries

    @staticmethod
    def decode_yaml_scalar(value: str) -> object:
        """Decode JSON-compatible YAML scalars and preserve plain strings."""

        stripped = value.strip()
        if stripped == "":
            return ""
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped.strip("'\"")

    def validate_source_evidence(
        self, entries: list[dict[str, object]]
    ) -> set[str]:
        """Validate source metadata and return unique source IDs."""

        relative = "research/sources.yaml"
        source_ids: set[str] = set()
        for entry in entries:
            self.require_evidence_fields(relative, "sources", entry)
            self.reject_credential_fields(relative, entry)
            self.validate_evidence_minimal_disclosure(relative, entry)
            source_id = entry.get("source_id")
            if not isinstance(source_id, str) or not re.fullmatch(
                r"SRC-\d{3}", source_id
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_SOURCE_ID_INVALID",
                    relative,
                    "source_id must match SRC-<nnn>",
                )
                continue
            if source_id in source_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_SOURCE_ID_DUPLICATE",
                    relative,
                    f"{source_id} is defined more than once",
                )
            source_ids.add(source_id)
            self.require_nonempty_string_fields(
                relative,
                source_id,
                entry,
                ("title", "accessed_at", "source_type", "version", "license"),
            )
            if not entry.get("url") and not entry.get("doi_or_identifier"):
                self.add(
                    "ERROR",
                    "RESEARCH_SOURCE_LOCATOR_MISSING",
                    relative,
                    f"{source_id} must provide a URL or stable identifier",
                )
            self.require_string_list(
                relative, source_id, entry, "creators", allow_empty=False
            )
            self.require_boolean_fields(
                relative,
                source_id,
                entry,
                ("contains_restricted_content", "external_transfer_allowed"),
            )
            self.require_enum(
                relative,
                source_id,
                entry,
                "data_classification",
                VALID_DATA_CLASSIFICATIONS,
            )
            self.require_enum(
                relative,
                source_id,
                entry,
                "provenance_level",
                VALID_PROVENANCE_LEVELS,
            )
            self.require_enum(
                relative,
                source_id,
                entry,
                "accessibility_status",
                VALID_ACCESSIBILITY_STATUSES,
            )
            self.require_enum(
                relative,
                source_id,
                entry,
                "update_retraction_conflict_status",
                VALID_SOURCE_LIFECYCLE_STATUSES,
            )
            if (
                entry.get("contains_restricted_content") is True
                and entry.get("data_classification")
                not in {"内部", "受限", "个人信息", "混合"}
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_RESTRICTED_SOURCE_CLASSIFICATION_MISSING",
                    relative,
                    f"{source_id} contains restricted content without a restricted classification",
                )
        return source_ids

    def validate_claim_evidence(
        self,
        entries: list[dict[str, object]],
        source_ids: set[str],
        rq_ids: set[str],
        transition_ready: bool,
    ) -> tuple[set[str], set[str]]:
        """Validate claims and return all and contract-eligible claim IDs."""

        relative = "research/claims.yaml"
        claim_ids: set[str] = set()
        eligible_claim_ids: set[str] = set()
        for entry in entries:
            self.require_evidence_fields(relative, "claims", entry)
            self.reject_credential_fields(relative, entry)
            self.validate_evidence_minimal_disclosure(relative, entry)
            claim_id = entry.get("claim_id")
            if not isinstance(claim_id, str) or not re.fullmatch(
                r"CLM-\d{3}", claim_id
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_CLAIM_ID_INVALID",
                    relative,
                    "claim_id must match CLM-<nnn>",
                )
                continue
            if claim_id in claim_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_CLAIM_ID_DUPLICATE",
                    relative,
                    f"{claim_id} is defined more than once",
                )
            claim_ids.add(claim_id)
            self.require_nonempty_string_fields(
                relative, claim_id, entry, ("claim",)
            )
            claim_rqs = self.require_id_list(
                relative,
                claim_id,
                entry,
                "research_question_ids",
                re.compile(r"RQ-\d{3}"),
                allow_empty=False,
            )
            claim_sources = self.require_id_list(
                relative,
                claim_id,
                entry,
                "source_ids",
                re.compile(r"SRC-\d{3}"),
                allow_empty=False,
            )
            self.require_string_list(
                relative,
                claim_id,
                entry,
                "evidence_locations",
                allow_empty=False,
            )
            for rq_id in sorted(claim_rqs - rq_ids):
                if transition_ready:
                    self.add(
                        "ERROR",
                        "RESEARCH_CLAIM_QUESTION_UNRESOLVED",
                        relative,
                        f"{claim_id} references undefined {rq_id}",
                    )
            for source_id in sorted(claim_sources - source_ids):
                self.add(
                    "ERROR",
                    "RESEARCH_CLAIM_SOURCE_UNRESOLVED",
                    relative,
                    f"{claim_id} references undefined {source_id}",
                )
            self.require_enum(
                relative,
                claim_id,
                entry,
                "support_level",
                VALID_SUPPORT_LEVELS,
            )
            self.require_enum(
                relative,
                claim_id,
                entry,
                "source_independence",
                VALID_SOURCE_INDEPENDENCE,
            )
            self.require_enum(
                relative,
                claim_id,
                entry,
                "temporal_status",
                VALID_TEMPORAL_STATUSES,
            )
            self.require_enum(
                relative,
                claim_id,
                entry,
                "conflict_status",
                VALID_CONFLICT_STATUSES,
            )
            self.require_enum(
                relative,
                claim_id,
                entry,
                "verification_status",
                VALID_VERIFICATION_STATUSES,
            )
            eligible = entry.get("eligible_for_research_contract")
            if not isinstance(eligible, bool):
                self.add(
                    "ERROR",
                    "RESEARCH_CLAIM_ELIGIBILITY_INVALID",
                    relative,
                    f"{claim_id} eligibility must be boolean",
                )
            elif eligible:
                eligible_claim_ids.add(claim_id)
                if entry.get("verification_status") != "已核验":
                    self.add(
                        "ERROR",
                        "RESEARCH_CLAIM_ELIGIBILITY_UNVERIFIED",
                        relative,
                        f"{claim_id} cannot support the contract before verification",
                    )
                if entry.get("conflict_status") == "存在冲突":
                    self.add(
                        "ERROR" if transition_ready else "WARN",
                        "RESEARCH_CLAIM_CONFLICT_UNRESOLVED",
                        relative,
                        f"{claim_id} is contract-eligible but has an unresolved source conflict",
                    )
        return claim_ids, eligible_claim_ids

    def validate_decision_evidence(
        self,
        entries: list[dict[str, object]],
        claim_ids: set[str],
        transition_ready: bool,
    ) -> set[str]:
        """Validate durable research decisions and their claim references."""

        relative = "research/decisions.yaml"
        decision_ids: set[str] = set()
        pending_supersedes: list[tuple[str, object]] = []
        for entry in entries:
            self.require_evidence_fields(relative, "decisions", entry)
            self.reject_credential_fields(relative, entry)
            self.validate_evidence_minimal_disclosure(relative, entry)
            decision_id = entry.get("decision_id")
            if not isinstance(decision_id, str) or not re.fullmatch(
                r"DEC-\d{3}", decision_id
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_ID_INVALID",
                    relative,
                    "decision_id must match DEC-<nnn>",
                )
                continue
            if decision_id in decision_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_ID_DUPLICATE",
                    relative,
                    f"{decision_id} is defined more than once",
                )
            decision_ids.add(decision_id)
            self.require_nonempty_string_fields(
                relative,
                decision_id,
                entry,
                ("decision", "user_input_source"),
            )
            supporting_claims = self.require_id_list(
                relative,
                decision_id,
                entry,
                "supporting_claim_ids",
                re.compile(r"CLM-\d{3}"),
            )
            for claim_id in sorted(supporting_claims - claim_ids):
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_CLAIM_UNRESOLVED",
                    relative,
                    f"{decision_id} references undefined {claim_id}",
                )
            alternatives = self.require_string_list(
                relative, decision_id, entry, "alternatives"
            )
            rejection_reasons = self.require_string_list(
                relative, decision_id, entry, "rejection_reasons"
            )
            if len(alternatives) != len(rejection_reasons):
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_ALTERNATIVES_MISMATCH",
                    relative,
                    f"{decision_id} alternatives and rejection reasons must align",
                )
            affected_fields = self.require_string_list(
                relative,
                decision_id,
                entry,
                "affected_contract_fields",
                allow_empty=False,
            )
            for field in sorted(affected_fields - REQUIRED_CONTRACT_FIELDS):
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_FIELD_INVALID",
                    relative,
                    f"{decision_id} references unknown contract field {field}",
                )
            self.require_boolean_fields(
                relative,
                decision_id,
                entry,
                ("triggers_phase_rollback",),
            )
            confirmation = entry.get("user_confirmation_status")
            if confirmation not in VALID_CONFIRMATION_STATUSES:
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_CONFIRMATION_INVALID",
                    relative,
                    f"{decision_id} has an invalid user confirmation status",
                )
            elif transition_ready and confirmation in BLOCKING_CONFIRMATION_STATUSES:
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_CONFIRMATION_BLOCKING",
                    relative,
                    f"{decision_id} remains {confirmation} after phase one",
                )
            if confirmation == "已确认" and not entry.get("decided_at"):
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_DATE_MISSING",
                    relative,
                    f"{decision_id} is confirmed without decided_at",
                )
            if "supersedes_decision_id" in entry:
                pending_supersedes.append(
                    (decision_id, entry.get("supersedes_decision_id"))
                )
        for decision_id, superseded in pending_supersedes:
            if superseded not in decision_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_DECISION_SUPERSEDES_UNRESOLVED",
                    relative,
                    f"{decision_id} supersedes an undefined decision",
                )
        return decision_ids

    def validate_search_log(
        self,
        source_ids: set[str],
        rq_ids: set[str],
        transition_ready: bool,
    ) -> list[dict[str, object]]:
        """Validate append-only JSONL query provenance and references."""

        relative = "research/search_log.jsonl"
        path = self.root / relative
        if not path.is_file():
            return []
        query_ids: set[str] = set()
        parsed_entries: list[dict[str, object]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            self.add(
                "ERROR",
                "RESEARCH_SEARCH_LOG_INVALID",
                relative,
                "search log is not valid UTF-8 text",
            )
            return []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_LOG_JSON_INVALID",
                    relative,
                    f"line {line_number} is not one complete JSON object",
                )
                continue
            if not isinstance(entry, dict):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_LOG_ENTRY_INVALID",
                    relative,
                    f"line {line_number} must contain a JSON object",
                )
                continue
            parsed_entries.append(entry)
            self.reject_credential_fields(relative, entry)
            self.validate_evidence_minimal_disclosure(relative, entry)
            missing = sorted(SEARCH_LOG_REQUIRED_FIELDS - entry.keys())
            if missing:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_LOG_FIELDS_MISSING",
                    relative,
                    f"line {line_number} is missing: {', '.join(missing)}",
                )
            query_id = entry.get("query_id")
            if not isinstance(query_id, str) or not re.fullmatch(
                r"QRY-\d{3}", query_id
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_ID_INVALID",
                    relative,
                    f"line {line_number} query_id must match QRY-<nnn>",
                )
                continue
            if query_id in query_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_ID_DUPLICATE",
                    relative,
                    f"{query_id} is defined more than once",
                )
            query_ids.add(query_id)
            self.require_nonempty_string_fields(
                relative,
                query_id,
                entry,
                ("query", "language", "platform", "searched_at"),
            )
            query_rqs = self.require_id_list(
                relative,
                query_id,
                entry,
                "research_question_ids",
                re.compile(r"RQ-\d{3}"),
            )
            included_sources = self.require_id_list(
                relative,
                query_id,
                entry,
                "included_source_ids",
                re.compile(r"SRC-\d{3}"),
            )
            for rq_id in sorted(query_rqs - rq_ids):
                if transition_ready:
                    self.add(
                        "ERROR",
                        "RESEARCH_QUERY_QUESTION_UNRESOLVED",
                        relative,
                        f"{query_id} references undefined {rq_id}",
                    )
            for source_id in sorted(included_sources - source_ids):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_SOURCE_UNRESOLVED",
                    relative,
                    f"{query_id} includes undefined {source_id}",
                )
            if not isinstance(entry.get("filters"), dict):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_FILTERS_INVALID",
                    relative,
                    f"{query_id} filters must be an object",
                )
            result_count = entry.get("result_count")
            if result_count is not None and (
                not isinstance(result_count, int)
                or isinstance(result_count, bool)
                or result_count < 0
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_RESULT_COUNT_INVALID",
                    relative,
                    f"{query_id} result_count must be a non-negative integer or null",
                )
            exclusions = entry.get("exclusions")
            if not isinstance(exclusions, list):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_EXCLUSIONS_INVALID",
                    relative,
                    f"{query_id} exclusions must be an array",
                )
            else:
                for exclusion in exclusions:
                    if (
                        not isinstance(exclusion, dict)
                        or not isinstance(exclusion.get("reason"), str)
                        or not exclusion.get("reason", "").strip()
                    ):
                        self.add(
                            "ERROR",
                            "RESEARCH_QUERY_EXCLUSION_REASON_MISSING",
                            relative,
                            f"{query_id} exclusions must record a non-empty reason",
                        )
            if not isinstance(entry.get("counterevidence_search"), bool):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_COUNTEREVIDENCE_INVALID",
                    relative,
                    f"{query_id} counterevidence_search must be boolean",
                )
            superseded = entry.get("supersedes_query_id")
            if superseded is not None and not re.fullmatch(
                r"QRY-\d{3}", str(superseded)
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_SUPERSEDES_INVALID",
                    relative,
                    f"{query_id} has an invalid supersedes_query_id",
                )
        return parsed_entries

    def check_phase_one_evidence_quality(
        self,
        sources: list[dict[str, object]],
        claims: list[dict[str, object]],
        search_entries: list[dict[str, object]],
        phase: str | None,
        status: str | None,
        transition_ready: bool,
    ) -> None:
        """Emit bounded quality warnings without pretending to judge research merit."""

        research_active = (
            phase == "阶段一：调研与设计" and status in {"进行中", "已完成"}
        ) or phase in {"阶段二：实验与分析", "阶段三：论文写作"}
        if research_active and not search_entries:
            self.add(
                "WARN",
                "RESEARCH_SEARCH_LOG_EMPTY",
                "research/search_log.jsonl",
                "stage-one research is active but no reproducible search query is recorded",
            )

        source_types = {
            str(entry.get("source_type"))
            for entry in sources
            if entry.get("source_type")
        }
        if len(sources) >= 2 and len(source_types) == 1:
            self.add(
                "WARN",
                "RESEARCH_SOURCE_TYPE_SINGLE",
                "research/sources.yaml",
                "all registered sources use one source type; document why this is sufficient",
            )

        for entry in claims:
            claim_id = str(entry.get("claim_id", "claim"))
            if (
                entry.get("eligible_for_research_contract") is True
                and entry.get("support_level") != "直接支持"
            ):
                self.add(
                    "WARN",
                    "RESEARCH_KEY_CLAIM_LACKS_DIRECT_SUPPORT",
                    "research/claims.yaml",
                    f"{claim_id} is contract-eligible without direct source support",
                )

        for entry in sources:
            if entry.get("update_retraction_conflict_status") in {
                "已撤回",
                "存在冲突",
            }:
                self.add(
                    "WARN",
                    "RESEARCH_SOURCE_LIFECYCLE_UNRESOLVED",
                    "research/sources.yaml",
                    f"{entry.get('source_id', 'source')} has an unresolved lifecycle or conflict status",
                )

        today = datetime.now(timezone.utc).date()
        for entry in search_entries:
            searched_at = entry.get("searched_at")
            searched_date = self.parse_iso_date(searched_at)
            if searched_date is None:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_DATE_INVALID",
                    "research/search_log.jsonl",
                    f"{entry.get('query_id', 'query')} searched_at must be an ISO date or datetime",
                )
            elif (today - searched_date).days > SEARCH_STALE_DAYS:
                self.add(
                    "WARN",
                    "RESEARCH_SEARCH_STALE",
                    "research/search_log.jsonl",
                    f"{entry.get('query_id', 'query')} was searched more than {SEARCH_STALE_DAYS} days ago",
                )

        if transition_ready and any(
            entry.get("eligible_for_research_contract") is True
            and entry.get("conflict_status") == "存在冲突"
            for entry in claims
        ):
            # The detailed claim validator emits the specific blocking error.
            return

    @staticmethod
    def parse_iso_date(value: object) -> date | None:
        """Parse a date or ISO-8601 datetime without third-party dependencies."""

        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            try:
                return date.fromisoformat(normalized)
            except ValueError:
                return None

    def reject_credential_fields(
        self, relative: str, entry: dict[str, object]
    ) -> None:
        """Reject credential-bearing field names even when values look harmless."""

        forbidden = {
            key.lower()
            for key in self.nested_keys(entry)
            if key.lower() in FORBIDDEN_EVIDENCE_FIELD_NAMES
            or key.lower().endswith(("_api_key", "_password", "_secret", "_token"))
        }
        if forbidden:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_CREDENTIAL_FIELD_FORBIDDEN",
                relative,
                f"credential fields are forbidden in phase-one evidence: {', '.join(sorted(forbidden))}",
            )

    def validate_evidence_minimal_disclosure(
        self, relative: str, entry: dict[str, object]
    ) -> None:
        """Reject full-text fields, excessive payloads, and common personal data."""

        content_fields = {
            key.lower()
            for key in self.nested_keys(entry)
            if key.lower() in FORBIDDEN_EVIDENCE_CONTENT_FIELDS
            or key.lower().endswith(("_full_text", "_raw_content", "_raw_sample"))
        }
        if content_fields:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_FULLTEXT_FIELD_FORBIDDEN",
                relative,
                f"full-text or sensitive-content fields are forbidden: {', '.join(sorted(content_fields))}",
            )

        oversized_fields: set[str] = set()
        personal_data_fields: set[str] = set()
        for field, value in self.nested_string_items(entry):
            limit = EVIDENCE_TEXT_LIMITS.get(field.lower(), MAX_EVIDENCE_STRING_LENGTH)
            if len(value) > limit:
                oversized_fields.add(field)
            if any(pattern.search(value) for pattern in PERSONAL_DATA_PATTERNS):
                personal_data_fields.add(field)
        if oversized_fields:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_MINIMAL_DISCLOSURE_EXCEEDED",
                relative,
                f"evidence text exceeds minimal-disclosure limits in: {', '.join(sorted(oversized_fields))}",
            )
        if personal_data_fields:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_PERSONAL_DATA_FORBIDDEN",
                relative,
                f"possible personal data appears in evidence fields: {', '.join(sorted(personal_data_fields))}",
            )

    @classmethod
    def nested_string_items(cls, value: object) -> list[tuple[str, str]]:
        """Collect leaf string values with their nearest mapping field name."""

        items: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str):
                    items.append((str(key), child))
                elif isinstance(child, list):
                    for list_child in child:
                        if isinstance(list_child, str):
                            items.append((str(key), list_child))
                        else:
                            items.extend(cls.nested_string_items(list_child))
                else:
                    items.extend(cls.nested_string_items(child))
        elif isinstance(value, list):
            for child in value:
                items.extend(cls.nested_string_items(child))
        return items

    def validate_contract_evidence_references(
        self,
        tables: list[tuple[list[str], list[dict[str, str]]]],
        source_ids: set[str],
        claim_ids: set[str],
        decision_ids: set[str],
    ) -> None:
        """Resolve contract decision and evidence cells against detailed registries."""

        for headers, rows in tables:
            for row in rows:
                if "决策 ID" in headers:
                    cell = row.get("决策 ID", "")
                    if cell not in PLACEHOLDER_CELLS and cell != "不适用":
                        refs = set(re.findall(r"DEC-\d{3}", cell))
                        if not refs:
                            self.add(
                                "ERROR",
                                "RESEARCH_DECISION_REFERENCE_INVALID",
                                "RESEARCH.md",
                                "decision reference cell must use DEC-<nnn>",
                            )
                        for ref in sorted(refs - decision_ids):
                            self.add(
                                "ERROR",
                                "RESEARCH_DECISION_REFERENCE_UNRESOLVED",
                                "RESEARCH.md",
                                f"{ref} has no entry in research/decisions.yaml",
                            )
                if "证据 ID" in headers:
                    cell = row.get("证据 ID", "")
                    if cell in PLACEHOLDER_CELLS or cell == "不适用":
                        continue
                    refs = set(re.findall(r"(?:CLM|SRC)-\d{3}", cell))
                    if not refs:
                        self.add(
                            "ERROR",
                            "RESEARCH_EVIDENCE_REFERENCE_INVALID",
                            "RESEARCH.md",
                            "evidence reference cell must use CLM-<nnn> or SRC-<nnn>",
                        )
                    for ref in sorted(refs):
                        registry = claim_ids if ref.startswith("CLM-") else source_ids
                        if ref not in registry:
                            self.add(
                                "ERROR",
                                "RESEARCH_EVIDENCE_REFERENCE_UNRESOLVED",
                                "RESEARCH.md",
                                f"{ref} has no detailed phase-one evidence entry",
                            )

    def require_evidence_fields(
        self, relative: str, collection: str, entry: dict[str, object]
    ) -> None:
        """Report missing required fields for one evidence entry."""

        missing = sorted(EVIDENCE_REQUIRED_FIELDS[collection] - entry.keys())
        if missing:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_FIELDS_MISSING",
                relative,
                f"{collection} entry is missing: {', '.join(missing)}",
            )

    def require_id_list(
        self,
        relative: str,
        object_id: str,
        entry: dict[str, object],
        field: str,
        pattern: re.Pattern[str],
        allow_empty: bool = True,
    ) -> set[str]:
        """Validate a list of stable IDs and return its valid values."""

        value = entry.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_ID_LIST_INVALID",
                relative,
                f"{object_id} {field} must be an array of strings",
            )
            return set()
        if not value and not allow_empty:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_ID_LIST_EMPTY",
                relative,
                f"{object_id} {field} must not be empty",
            )
        valid: set[str] = set()
        for item in value:
            if not pattern.fullmatch(item):
                self.add(
                    "ERROR",
                    "RESEARCH_EVIDENCE_REFERENCE_FORMAT_INVALID",
                    relative,
                    f"{object_id} {field} contains an invalid stable ID",
                )
            else:
                valid.add(item)
        return valid

    def require_string_list(
        self,
        relative: str,
        object_id: str,
        entry: dict[str, object],
        field: str,
        allow_empty: bool = True,
    ) -> set[str]:
        """Validate a list of strings and return its values."""

        value = entry.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_STRING_LIST_INVALID",
                relative,
                f"{object_id} {field} must be an array of strings",
            )
            return set()
        if not value and not allow_empty:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_STRING_LIST_EMPTY",
                relative,
                f"{object_id} {field} must not be empty",
            )
        return set(value)

    def require_nonempty_string_fields(
        self,
        relative: str,
        object_id: str,
        entry: dict[str, object],
        fields: tuple[str, ...],
    ) -> None:
        """Validate required non-empty string fields."""

        for field in fields:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                self.add(
                    "ERROR",
                    "RESEARCH_EVIDENCE_STRING_INVALID",
                    relative,
                    f"{object_id} {field} must be a non-empty string",
                )

    def require_boolean_fields(
        self,
        relative: str,
        object_id: str,
        entry: dict[str, object],
        fields: tuple[str, ...],
    ) -> None:
        """Validate boolean evidence fields."""

        for field in fields:
            if not isinstance(entry.get(field), bool):
                self.add(
                    "ERROR",
                    "RESEARCH_EVIDENCE_BOOLEAN_INVALID",
                    relative,
                    f"{object_id} {field} must be boolean",
                )

    def require_enum(
        self,
        relative: str,
        object_id: str,
        entry: dict[str, object],
        field: str,
        allowed: set[str],
    ) -> None:
        """Validate a string enum in an evidence entry."""

        if entry.get(field) not in allowed:
            self.add(
                "ERROR",
                "RESEARCH_EVIDENCE_ENUM_INVALID",
                relative,
                f"{object_id} {field} must be one of {sorted(allowed)}",
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
