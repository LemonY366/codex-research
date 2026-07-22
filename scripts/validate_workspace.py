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
    "workflow/README.md",
    "workflow/state.json",
    "workflow/transitions.jsonl",
    "research/README.md",
    "research/search_log.jsonl",
    "research/search_coverage.yaml",
    "research/sources.yaml",
    "research/claims.yaml",
    "research/decisions.yaml",
    "research/resources.yaml",
    "research/archive/README.md",
    "research/summaries/README.md",
    "experiments/TODO.md",
    "paper/TODO.md",
    ".env.example",
    "docs/README.md",
    "docs/TEMPLATE_BOUNDARIES.md",
    "docs/WORKFLOW_GATES.md",
    "docs/PHASE_ONE_PROTOCOL.md",
    "docs/SEARCH_PROTOCOL.md",
    "docs/SKILL_USAGE.md",
    "datasets/README.md",
    "models/README.md",
    "baselines/README.md",
    "scripts/README.md",
    "scripts/transition_workflow.py",
    "scripts/manage_task_progress.py",
    "src/README.md",
    "src/runtime/progress.py",
    "experiments/README.md",
    "experiments/scripts/README.md",
    "experiments/runs/README.md",
    "paper/README.md",
    "paper/sessions/README.md",
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
PHASE_ONE_STATE_ORDER = (
    "INTAKE",
    "DIVERGE",
    "SEARCH",
    "COMPARE",
    "DRAFT",
    "CONFIRM",
    "GATE_CHECK",
)
WORKFLOW_NODE_ORDER = (
    *PHASE_ONE_STATE_ORDER,
    "阶段二：实验与分析",
    "阶段三：论文写作",
)
REQUIRED_INTAKE_FIELDS = (
    "用户研究意图",
    "研究对象",
    "核心问题",
    "预期贡献",
    "成功标准",
    "数据条件",
    "baseline",
    "指标",
    "API/GPU",
    "数据许可和隐私",
    "范围外事项",
)
VALID_INTAKE_STATUSES = {"已澄清", "暂定", "待澄清", "明确未知", "不适用"}
VALID_DIRECTION_STATUSES = {"候选", "已选定", "已否决"}
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
    "阶段二执行约束与资源方案",
    "Skills、依赖与授权",
    "范围外事项",
}
PLACEHOLDER_CELLS = {"", "-", "TODO", "待分配"}
RESEARCH_ID_DEFINITIONS = (
    ("未决问题 ID", "问题", re.compile(r"OPEN-\d{3}")),
    ("候选方向 ID", "核心问题", re.compile(r"DIR-\d{3}")),
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
        "quality_level",
        "provenance_level",
        "primary_source_id",
        "independence_group",
        "usage_role",
        "version",
        "license",
        "data_classification",
        "contains_restricted_content",
        "external_transfer_allowed",
        "accessibility_status",
        "locator_exists",
        "locator_verified_at",
        "locator_verification_method",
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
        "citation_support_verified",
        "numeric_details_verified",
        "scope_match_verified",
        "causality_checked",
        "model_inference_status",
        "conflict_type",
        "conflict_reason",
        "uncertainty_notes",
        "adverse_evidence_retained",
        "verification_notes",
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
    "direction_ids",
    "research_question_ids",
    "search_categories",
    "query",
    "language",
    "keyword_variants",
    "platform",
    "searched_at",
    "filters",
    "result_count",
    "included_source_ids",
    "exclusions",
    "counterevidence_search",
    "citation_tracking",
    "returned_content_size",
    "returned_content_unit",
    "page_count",
    "external_tool_calls",
}
SEARCH_COVERAGE_REQUIRED_FIELDS = {
    "direction_id",
    "research_question_ids",
    "query_ids",
    "coverage",
    "coverage_notes",
    "chinese_keywords",
    "english_keywords",
    "citation_tracking_source_ids",
    "planned_languages",
    "covered_languages",
    "planned_platforms",
    "covered_platforms",
    "planned_date_range",
    "covered_date_range",
    "independent_source_yield_history",
    "new_method_categories_history",
    "key_questions_covered",
    "counterevidence_completed",
    "citation_tracking_completed",
    "uncovered_scope",
    "stop_reason",
    "stop_status",
    "last_updated_at",
}
RESOURCE_REQUIRED_FIELDS = {
    "resource_id",
    "recorded_at",
    "status",
    "input_tokens",
    "output_tokens",
    "search_return_size",
    "search_return_unit",
    "search_queries",
    "search_pages",
    "external_tool_calls",
    "api_calls",
    "elapsed_seconds",
    "estimated_cost",
    "cost_currency",
    "evidence_file_bytes",
    "claim_count",
    "context_compactions",
    "unavailable_metrics",
}
REQUIRED_SEARCH_CATEGORIES = {
    "背景",
    "现有方法",
    "baseline",
    "研究空白",
    "失败和负面结果",
    "数据集与指标",
    "许可与可行性",
    "相似工作",
}
VALID_COVERAGE_STATUSES = {"已覆盖", "部分覆盖", "未覆盖", "不适用"}
VALID_SEARCH_STOP_STATUSES = {"未开始", "进行中", "可停止", "已停止"}
VALID_RETURN_SIZE_UNITS = {"tokens", "characters", "unavailable"}
VALID_RESOURCE_STATUSES = {"当前", "已归档"}
VALID_SOURCE_USAGE_ROLES = {"关键证据", "补充证据", "检索线索"}
VALID_LOCATOR_METHODS = {"人工打开", "DOI解析", "官方登记", "工具检查", "未核验"}
VALID_MODEL_INFERENCE_STATUSES = {"非模型推论", "已明确标注", "未明确标注"}
VALID_CLAIM_CONFLICT_TYPES = {
    "无",
    "事实冲突",
    "定义差异",
    "版本差异",
    "场景差异",
    "多重差异",
    "待判定",
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
SEARCH_LOG_LINE_WARNING = 5_000
SEARCH_LOG_BYTE_WARNING = 2 * 1024 * 1024
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
        self.check_machine_workflow_state()
        self.check_research_contract(phase, status)
        self.check_phase_one_evidence(phase, status)
        self.check_unresolved_todos(phase, status)
        self.check_registries()
        self.check_run_records()
        self.check_experiment_reconciliation()
        self.check_task_progress()
        handoff_required = phase == "阶段三：论文写作" or (
            phase == "阶段二：实验与分析" and status == "已完成"
        )
        self.check_stage_two_handoff(required=handoff_required)
        self.check_stage_three_session_completion(phase, status)
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

    def check_machine_workflow_state(self) -> None:
        """Cross-check machine state, Markdown projection, and transition ledger."""

        state_path = self.root / "workflow/state.json"
        transitions_path = self.root / "workflow/transitions.jsonl"
        research_path = self.root / "RESEARCH.md"
        if not state_path.is_file() or not transitions_path.is_file() or not research_path.is_file():
            return
        state = self.read_json(state_path, "WORKFLOW_STATE_INVALID")
        if state is None:
            return
        required = {
            "schema_version",
            "revision",
            "current_phase",
            "phase_one_substate",
            "phase_status",
            "gate_result",
            "last_transition_id",
            "updated_at",
        }
        missing = sorted(required - state.keys())
        if missing:
            self.add(
                "ERROR",
                "WORKFLOW_STATE_FIELDS_MISSING",
                "workflow/state.json",
                f"machine workflow state is missing: {', '.join(missing)}",
            )
        if state.get("schema_version") != 1:
            self.add(
                "ERROR",
                "WORKFLOW_STATE_SCHEMA_INVALID",
                "workflow/state.json",
                "workflow state schema_version must be 1",
            )
        if state.get("current_phase") not in VALID_PHASES:
            self.add("ERROR", "WORKFLOW_STATE_PHASE_INVALID", "workflow/state.json", "invalid current_phase")
        if state.get("phase_one_substate") not in VALID_PHASE_ONE_STATES:
            self.add("ERROR", "WORKFLOW_STATE_SUBSTATE_INVALID", "workflow/state.json", "invalid phase_one_substate")
        if state.get("phase_status") not in VALID_PHASE_STATUSES:
            self.add("ERROR", "WORKFLOW_STATE_STATUS_INVALID", "workflow/state.json", "invalid phase_status")
        if state.get("gate_result") not in VALID_GATE_RESULTS:
            self.add("ERROR", "WORKFLOW_STATE_GATE_INVALID", "workflow/state.json", "invalid gate_result")
        revision = state.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            self.add("ERROR", "WORKFLOW_STATE_REVISION_INVALID", "workflow/state.json", "revision must be a non-negative integer")

        research_text = research_path.read_text(encoding="utf-8")
        projections = {
            "current_phase": self.extract_field(research_text, "当前阶段"),
            "phase_one_substate": self.extract_field(research_text, "阶段一子状态"),
            "phase_status": self.extract_field(research_text, "阶段状态"),
            "gate_result": self.extract_field(research_text, "阶段门禁"),
        }
        for field, projected in projections.items():
            if state.get(field) != projected:
                self.add(
                    "ERROR",
                    "WORKFLOW_STATE_PROJECTION_MISMATCH",
                    "RESEARCH.md",
                    f"{field} differs from workflow/state.json; use transition_workflow.py",
                )

        entries: list[dict[str, object]] = []
        for line_number, line in enumerate(
            transitions_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                self.add(
                    "ERROR",
                    "WORKFLOW_TRANSITION_JSON_INVALID",
                    "workflow/transitions.jsonl",
                    f"line {line_number} is not valid JSON",
                )
                continue
            if not isinstance(entry, dict):
                self.add(
                    "ERROR",
                    "WORKFLOW_TRANSITION_OBJECT_INVALID",
                    "workflow/transitions.jsonl",
                    f"line {line_number} must contain an object",
                )
                continue
            entries.append(entry)
        previous_target: object = None
        for index, entry in enumerate(entries, start=1):
            expected_id = f"TRANS-{index:03d}"
            if entry.get("transition_id") != expected_id or entry.get("revision") != index:
                self.add(
                    "ERROR",
                    "WORKFLOW_TRANSITION_SEQUENCE_INVALID",
                    "workflow/transitions.jsonl",
                    f"entry {index} must use {expected_id} and revision {index}",
                )
            source = entry.get("from_node")
            target = entry.get("to_node")
            if source not in WORKFLOW_NODE_ORDER or target not in WORKFLOW_NODE_ORDER:
                self.add(
                    "ERROR",
                    "WORKFLOW_TRANSITION_NODE_INVALID",
                    "workflow/transitions.jsonl",
                    f"{expected_id} contains an invalid workflow node",
                )
            elif WORKFLOW_NODE_ORDER.index(target) > WORKFLOW_NODE_ORDER.index(source) + 1:
                self.add(
                    "ERROR",
                    "WORKFLOW_TRANSITION_SKIPPED_STATE",
                    "workflow/transitions.jsonl",
                    f"{expected_id} skips a required workflow node",
                )
            if previous_target is not None and entry.get("from_node") != previous_target:
                self.add(
                    "ERROR",
                    "WORKFLOW_TRANSITION_CHAIN_BROKEN",
                    "workflow/transitions.jsonl",
                    f"{expected_id} does not continue from the previous target",
                )
            previous_target = entry.get("to_node")
        expected_last = entries[-1].get("transition_id") if entries else None
        if state.get("last_transition_id") != expected_last or revision != len(entries):
            self.add(
                "ERROR",
                "WORKFLOW_STATE_LEDGER_MISMATCH",
                "workflow/state.json",
                "state revision or last_transition_id differs from the transition ledger",
            )
        state_node = (
            state.get("phase_one_substate")
            if state.get("current_phase") == "阶段一：调研与设计"
            else state.get("current_phase")
        )
        ledger_node = entries[-1].get("to_node") if entries else "INTAKE"
        if state_node != ledger_node:
            self.add(
                "ERROR",
                "WORKFLOW_STATE_TARGET_MISMATCH",
                "workflow/state.json",
                "machine state does not match the latest transition target",
            )
        if revision and self.parse_iso_datetime(state.get("updated_at")) is None:
            self.add(
                "ERROR",
                "WORKFLOW_STATE_TIME_INVALID",
                "workflow/state.json",
                "updated_at must be a timezone-aware ISO timestamp after a transition",
            )

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
        self,
        phase: str | None,
        status: str | None,
        phase_one_state_override: str | None = None,
        preflight_transition: bool = False,
    ) -> None:
        """Validate phase-one confirmation, stable IDs, and contract relations."""

        path = self.root / "RESEARCH.md"
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        tables = self.parse_markdown_tables(text)
        phase_one_state = phase_one_state_override or self.extract_field(
            text, "阶段一子状态"
        )
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

        if not preflight_transition:
            self.check_research_recovery(text, phase, status, transition_ready)
        self.check_research_contract_quality(text, tables, transition_ready)
        self.check_requirement_intake(tables, phase_one_state, transition_ready)
        self.check_brainstorm(tables, text, phase_one_state, transition_ready)
        if not preflight_transition:
            self.check_transition_history(
                tables, phase, phase_one_state, status, transition_ready
            )

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

        self.check_candidate_directions(
            tables, phase_one_state, transition_ready, definitions
        )

        if transition_ready:
            self.check_contract_relations(tables, definitions)
            self.check_experiment_task_relations(definitions)

    def check_requirement_intake(
        self,
        tables: list[tuple[list[str], list[dict[str, str]]]],
        phase_one_state: str | None,
        transition_ready: bool,
    ) -> None:
        """Validate progressive intake without front-loading execution details."""

        rows = next(
            (
                table_rows
                for headers, table_rows in tables
                if {"顺序", "需求字段", "获取状态"}.issubset(headers)
            ),
            None,
        )
        if rows is None:
            self.add(
                "ERROR",
                "RESEARCH_INTAKE_TABLE_MISSING",
                "RESEARCH.md",
                "research contract must add the progressive eleven-field intake table",
            )
            return

        actual_fields = tuple(row.get("需求字段", "") for row in rows)
        if actual_fields != REQUIRED_INTAKE_FIELDS:
            self.add(
                "ERROR",
                "RESEARCH_INTAKE_ORDER_INVALID",
                "RESEARCH.md",
                "requirement-intake rows must contain the eleven required fields in order",
            )

        for expected_index, row in enumerate(rows, start=1):
            if row.get("顺序") != str(expected_index):
                self.add(
                    "ERROR",
                    "RESEARCH_INTAKE_SEQUENCE_INVALID",
                    "RESEARCH.md",
                    "requirement-intake sequence numbers must be consecutive from 1 to 12",
                )
                break
            field = row.get("需求字段", "requirement")
            intake_status = row.get("获取状态", "")
            if intake_status not in VALID_INTAKE_STATUSES:
                self.add(
                    "ERROR",
                    "RESEARCH_INTAKE_STATUS_INVALID",
                    "RESEARCH.md",
                    f"{field} has an unsupported intake status",
                )
                continue
            summary = row.get("当前摘要或引用", "")
            if intake_status != "待澄清" and (
                summary in PLACEHOLDER_CELLS or summary.startswith("TODO")
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_INTAKE_VALUE_MISSING",
                    "RESEARCH.md",
                    f"{field} is {intake_status} without a usable summary",
                )
            if intake_status == "明确未知" and not re.search(
                r"OPEN-\d{3}", row.get("未决问题 ID", "")
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_INTAKE_OPEN_QUESTION_MISSING",
                    "RESEARCH.md",
                    f"{field} is explicitly unknown without an OPEN-<nnn>",
                )
            if intake_status == "不适用" and not self.has_not_applicable_reason(
                summary
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_NOT_APPLICABLE_REASON_MISSING",
                    "RESEARCH.md",
                    f"{field} is not applicable but has no explicit reason",
                )

        if phase_one_state not in VALID_PHASE_ONE_STATES:
            return
        state_index = PHASE_ONE_STATE_ORDER.index(phase_one_state)
        row_by_field = {row.get("需求字段", ""): row for row in rows}
        if state_index >= PHASE_ONE_STATE_ORDER.index("DIVERGE"):
            field = REQUIRED_INTAKE_FIELDS[0]
            if row_by_field.get(field, {}).get("获取状态") == "待澄清":
                self.add(
                    "ERROR",
                    "RESEARCH_INTAKE_SEED_MISSING",
                    "RESEARCH.md",
                    "a usable research-intent seed is required before DIVERGE",
                )
        if state_index >= PHASE_ONE_STATE_ORDER.index("SEARCH"):
            pending = [
                field
                for field in REQUIRED_INTAKE_FIELDS[:4]
                if row_by_field.get(field, {}).get("获取状态") == "待澄清"
            ]
            if pending:
                self.add(
                    "ERROR",
                    "RESEARCH_INTAKE_INCOMPLETE_FOR_SEARCH",
                    "RESEARCH.md",
                    f"direction-level intake must be addressed before SEARCH: {', '.join(pending)}",
                )
        if state_index >= PHASE_ONE_STATE_ORDER.index("DRAFT") or transition_ready:
            unresolved = [
                field
                for field in REQUIRED_INTAKE_FIELDS
                if row_by_field.get(field, {}).get("获取状态")
                not in {"已澄清", "不适用"}
            ]
            if unresolved:
                self.add(
                    "ERROR",
                    "RESEARCH_INTAKE_INCOMPLETE_FOR_DRAFT",
                    "RESEARCH.md",
                    f"final contract cannot be drafted from unresolved intake fields: {', '.join(unresolved)}",
                )

    def check_brainstorm(
        self,
        tables: list[tuple[list[str], list[dict[str, str]]]],
        text: str,
        phase_one_state: str | None,
        transition_ready: bool,
    ) -> None:
        """Require a Codex-led divergence record before search begins."""

        required_columns = {
            "轮次",
            "Codex 主动问题焦点",
            "用户回答摘要",
            "新增差异维度",
            "关联候选方向",
            "趋同判断",
        }
        rows = next(
            (
                table_rows
                for headers, table_rows in tables
                if required_columns.issubset(headers)
            ),
            None,
        )
        if rows is None:
            self.add(
                "ERROR",
                "RESEARCH_BRAINSTORM_TABLE_MISSING",
                "RESEARCH.md",
                "research contract must contain the Codex-led brainstorming table",
            )
            return
        if phase_one_state not in VALID_PHASE_ONE_STATES:
            return
        search_started = (
            PHASE_ONE_STATE_ORDER.index(phase_one_state)
            >= PHASE_ONE_STATE_ORDER.index("SEARCH")
        ) or transition_ready
        if not search_started:
            return
        real_rows = [
            row
            for row in rows
            if row.get("轮次", "") not in PLACEHOLDER_CELLS
            and not row.get("轮次", "").startswith("TODO")
        ]
        if not real_rows:
            self.add(
                "ERROR",
                "RESEARCH_BRAINSTORM_RECORD_MISSING",
                "RESEARCH.md",
                "SEARCH requires at least one recorded Codex-led brainstorming round",
            )
        for row in real_rows:
            missing = [
                column
                for column in required_columns - {"轮次"}
                if row.get(column, "") in PLACEHOLDER_CELLS
                or row.get(column, "").startswith("TODO")
            ]
            if missing:
                self.add(
                    "ERROR",
                    "RESEARCH_BRAINSTORM_RECORD_INCOMPLETE",
                    "RESEARCH.md",
                    f"brainstorm round is missing: {', '.join(sorted(missing))}",
                )
            if row.get("趋同判断") not in {"有新差异", "趋同"}:
                self.add(
                    "ERROR",
                    "RESEARCH_BRAINSTORM_CONVERGENCE_INVALID",
                    "RESEARCH.md",
                    "brainstorm convergence must be 有新差异 or 趋同",
                )
        conclusion = self.extract_field(text, "发散结论") or ""
        more_ideas = self.extract_field(text, "用户是否还有更多想法") or ""
        if conclusion in PLACEHOLDER_CELLS or conclusion.startswith("TODO"):
            self.add(
                "ERROR",
                "RESEARCH_BRAINSTORM_CONCLUSION_MISSING",
                "RESEARCH.md",
                "SEARCH requires a recorded divergence conclusion",
            )
        if not more_ideas.startswith("暂无"):
            self.add(
                "ERROR",
                "RESEARCH_BRAINSTORM_USER_EXIT_MISSING",
                "RESEARCH.md",
                "SEARCH requires the user to indicate there are temporarily no more ideas",
            )

    def check_candidate_directions(
        self,
        tables: list[tuple[list[str], list[dict[str, str]]]],
        phase_one_state: str | None,
        transition_ready: bool,
        definitions: dict[str, set[str]],
    ) -> None:
        """Require multiple compared candidates and one final direction."""

        required_columns = {
            "候选方向 ID",
            "核心问题",
            "研究价值",
            "创新性风险",
            "数据需求",
            "计算成本",
            "验证难度",
            "预计交付物",
            "关联研究问题 ID",
            "状态",
            "选择或否决理由",
            "决策 ID",
        }
        rows = next(
            (
                table_rows
                for headers, table_rows in tables
                if required_columns.issubset(headers)
            ),
            None,
        )
        if rows is None:
            self.add(
                "ERROR",
                "RESEARCH_DIRECTION_TABLE_MISSING",
                "RESEARCH.md",
                "legacy contract must add the multi-candidate direction comparison table",
            )
            return

        real_rows = [
            row
            for row in rows
            if re.fullmatch(r"DIR-\d{3}", row.get("候选方向 ID", ""))
        ]
        for row in real_rows:
            direction_id = row.get("候选方向 ID", "direction")
            direction_status = row.get("状态", "")
            if direction_status not in VALID_DIRECTION_STATUSES:
                self.add(
                    "ERROR",
                    "RESEARCH_DIRECTION_STATUS_INVALID",
                    "RESEARCH.md",
                    f"{direction_id} has an unsupported direction status",
                )

        if phase_one_state not in VALID_PHASE_ONE_STATES:
            return
        state_index = PHASE_ONE_STATE_ORDER.index(phase_one_state)
        comparison_required = (
            state_index >= PHASE_ONE_STATE_ORDER.index("SEARCH")
            or transition_ready
        )
        if not comparison_required:
            return
        if len(real_rows) < 2:
            self.add(
                "ERROR",
                "RESEARCH_DIRECTION_CANDIDATES_INSUFFICIENT",
                "RESEARCH.md",
                "at least two substantively different candidate directions are required before SEARCH",
            )

        comparison_columns = (
            "核心问题",
            "研究价值",
            "创新性风险",
            "数据需求",
            "计算成本",
            "验证难度",
            "预计交付物",
        )
        signatures: set[tuple[str, ...]] = set()
        for row in real_rows:
            direction_id = row.get("候选方向 ID", "direction")
            missing = [
                column
                for column in comparison_columns
                if row.get(column, "") in PLACEHOLDER_CELLS
                or row.get(column, "").startswith("TODO")
            ]
            if missing:
                self.add(
                    "ERROR",
                    "RESEARCH_DIRECTION_COMPARISON_INCOMPLETE",
                    "RESEARCH.md",
                    f"{direction_id} is missing comparison fields: {', '.join(missing)}",
                )
            signature = tuple(row.get(column, "").strip() for column in comparison_columns)
            if signature in signatures:
                self.add(
                    "ERROR",
                    "RESEARCH_DIRECTION_NOT_SUBSTANTIVELY_DIFFERENT",
                    "RESEARCH.md",
                    f"{direction_id} duplicates another candidate across all comparison dimensions",
                )
            signatures.add(signature)

        final_selection_required = (
            state_index >= PHASE_ONE_STATE_ORDER.index("DRAFT")
            or transition_ready
        )
        if not final_selection_required:
            return
        selected = [row for row in real_rows if row.get("状态") == "已选定"]
        if len(selected) != 1:
            self.add(
                "ERROR",
                "RESEARCH_DIRECTION_FINAL_NOT_UNIQUE",
                "RESEARCH.md",
                "exactly one candidate direction must be selected before DRAFT and stage two",
            )
        for row in real_rows:
            direction_id = row.get("候选方向 ID", "direction")
            if row.get("状态") not in {"已选定", "已否决"}:
                self.add(
                    "ERROR",
                    "RESEARCH_DIRECTION_UNRESOLVED",
                    "RESEARCH.md",
                    f"{direction_id} remains a candidate after final direction selection",
                )
            reason = row.get("选择或否决理由", "")
            if reason in PLACEHOLDER_CELLS or reason.startswith("TODO"):
                self.add(
                    "ERROR",
                    "RESEARCH_DIRECTION_REASON_MISSING",
                    "RESEARCH.md",
                    f"{direction_id} has no selection or rejection reason",
                )
            if not re.search(r"DEC-\d{3}", row.get("决策 ID", "")):
                self.add(
                    "ERROR",
                    "RESEARCH_DIRECTION_DECISION_MISSING",
                    "RESEARCH.md",
                    f"{direction_id} has no DEC-<nnn> decision reference",
                )
        if selected:
            rq_id = selected[0].get("关联研究问题 ID", "")
            if rq_id not in definitions.get("研究问题 ID", set()):
                self.add(
                    "ERROR",
                    "RESEARCH_DIRECTION_QUESTION_MISSING",
                    "RESEARCH.md",
                    "the selected direction must reference a defined research question",
                )

    def check_transition_history(
        self,
        tables: list[tuple[list[str], list[dict[str, str]]]],
        phase: str | None,
        phase_one_state: str | None,
        status: str | None,
        transition_ready: bool,
    ) -> None:
        """Require a continuous, state-consistent workflow transition ledger."""

        required_columns = {
            "切换 ID",
            "日期",
            "原阶段",
            "新阶段",
            "门禁结果",
            "原因或授权",
            "决策 ID",
        }
        rows = next(
            (
                table_rows
                for headers, table_rows in tables
                if required_columns.issubset(headers)
            ),
            None,
        )
        if rows is None:
            self.add(
                "ERROR",
                "RESEARCH_TRANSITION_TABLE_MISSING",
                "RESEARCH.md",
                "research contract must contain a workflow transition table",
            )
            return
        real_rows = [
            row
            for row in rows
            if re.fullmatch(r"TRANS-\d{3}", row.get("切换 ID", ""))
        ]
        if not real_rows:
            if transition_ready or phase_one_state not in {None, "INTAKE"}:
                self.add(
                    "ERROR",
                    "RESEARCH_TRANSITION_HISTORY_MISSING",
                    "RESEARCH.md",
                    "workflow progress requires a recorded transition history",
                )
            return

        nodes = (*PHASE_ONE_STATE_ORDER, "阶段二：实验与分析", "阶段三：论文写作")
        node_index = {node: index for index, node in enumerate(nodes)}
        previous_target: str | None = None
        for row in real_rows:
            transition_id = row.get("切换 ID", "transition")
            source = row.get("原阶段", "")
            target = row.get("新阶段", "")
            if source not in node_index or target not in node_index:
                self.add(
                    "ERROR",
                    "RESEARCH_TRANSITION_NODE_INVALID",
                    "RESEARCH.md",
                    f"{transition_id} references an unsupported workflow node",
                )
                continue
            if previous_target is not None and source != previous_target:
                self.add(
                    "ERROR",
                    "RESEARCH_TRANSITION_CHAIN_BROKEN",
                    "RESEARCH.md",
                    f"{transition_id} does not continue from the previous transition",
                )
            if node_index[target] > node_index[source] + 1:
                self.add(
                    "ERROR",
                    "RESEARCH_TRANSITION_STEP_SKIPPED",
                    "RESEARCH.md",
                    f"{transition_id} skips a required intermediate workflow state",
                )
            if target in {"阶段二：实验与分析", "阶段三：论文写作"} and row.get(
                "门禁结果"
            ) != "已通过":
                self.add(
                    "ERROR",
                    "RESEARCH_TRANSITION_GATE_NOT_PASSED",
                    "RESEARCH.md",
                    f"{transition_id} enters a later stage without a passed gate",
                )
            for field in ("日期", "原因或授权"):
                if row.get(field, "") in PLACEHOLDER_CELLS or row.get(
                    field, ""
                ).startswith("TODO"):
                    self.add(
                        "ERROR",
                        "RESEARCH_TRANSITION_DETAIL_MISSING",
                        "RESEARCH.md",
                        f"{transition_id} is missing {field}",
                    )
            previous_target = target

        expected_target = (
            phase_one_state if phase == "阶段一：调研与设计" else phase
        )
        if previous_target != expected_target:
            self.add(
                "ERROR",
                "RESEARCH_TRANSITION_STATE_MISMATCH",
                "RESEARCH.md",
                "latest transition target conflicts with the canonical workflow state",
            )
        if status == "已完成" and phase == "阶段一：调研与设计" and previous_target != "GATE_CHECK":
            self.add(
                "ERROR",
                "RESEARCH_TRANSITION_COMPLETION_INVALID",
                "RESEARCH.md",
                "stage one cannot be complete before GATE_CHECK",
            )

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
            "当前全局阶段",
            "当前阶段一子状态",
            "当前候选方向",
            "当前唯一选定方向",
            "头脑风暴状态",
            "最新趋同判断",
            "用户是否还有更多想法",
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
        if missing:
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

        recovery_phase = self.extract_field(text, "当前全局阶段")
        recovery_state = self.extract_field(text, "当前阶段一子状态")
        if recovery_phase not in {None, "TODO", phase}:
            self.add(
                "ERROR",
                "RESEARCH_RECOVERY_PHASE_CONFLICT",
                "RESEARCH.md",
                "session recovery phase conflicts with the canonical workflow state",
            )
        canonical_state = self.extract_field(text, "阶段一子状态")
        if recovery_state not in {None, "TODO", canonical_state}:
            self.add(
                "ERROR",
                "RESEARCH_RECOVERY_SUBSTATE_CONFLICT",
                "RESEARCH.md",
                "session recovery substate conflicts with the canonical phase-one state",
            )

        direction_rows = [
            row
            for headers, rows in self.parse_markdown_tables(text)
            if "候选方向 ID" in headers and "状态" in headers
            for row in rows
            if re.fullmatch(r"DIR-\d{3}", row.get("候选方向 ID", ""))
        ]
        recovery_candidates = self.extract_field(text, "当前候选方向") or ""
        recovery_selected = self.extract_field(text, "当前唯一选定方向") or ""
        real_ids = {row.get("候选方向 ID", "") for row in direction_rows}
        selected_ids = {
            row.get("候选方向 ID", "")
            for row in direction_rows
            if row.get("状态") == "已选定"
        }
        if real_ids and recovery_candidates.startswith("无"):
            self.add(
                "ERROR",
                "RESEARCH_RECOVERY_DIRECTION_CONFLICT",
                "RESEARCH.md",
                "session recovery says there are no candidates but direction records exist",
            )
        if not real_ids and re.search(r"DIR-\d{3}", recovery_candidates):
            self.add(
                "ERROR",
                "RESEARCH_RECOVERY_DIRECTION_CONFLICT",
                "RESEARCH.md",
                "session recovery references candidate directions absent from the contract",
            )
        if selected_ids and not selected_ids.issubset(set(re.findall(r"DIR-\d{3}", recovery_selected))):
            self.add(
                "ERROR",
                "RESEARCH_RECOVERY_SELECTION_CONFLICT",
                "RESEARCH.md",
                "session recovery selected direction conflicts with the direction table",
            )
        if not selected_ids and re.search(r"DIR-\d{3}", recovery_selected):
            self.add(
                "ERROR",
                "RESEARCH_RECOVERY_SELECTION_CONFLICT",
                "RESEARCH.md",
                "session recovery claims a selected direction when none is selected",
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
            "阶段二失败停止规则",
        ):
            value = self.extract_field(text, label)
            if value is None or value in PLACEHOLDER_CELLS or value.startswith("TODO"):
                self.add(
                    "ERROR",
                    "RESEARCH_STAGE_TWO_RESOURCE_FIELD_MISSING",
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
        self,
        phase: str | None,
        status: str | None,
        phase_one_state_override: str | None = None,
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
        phase_one_state = phase_one_state_override or self.extract_field(
            research_text, "阶段一子状态"
        )
        search_required = (
            phase_one_state in VALID_PHASE_ONE_STATES
            and PHASE_ONE_STATE_ORDER.index(phase_one_state)
            >= PHASE_ONE_STATE_ORDER.index("SEARCH")
        ) or transition_ready

        sources = self.read_flat_yaml_registry(
            "research/sources.yaml", "sources", "source_id"
        )
        claims = self.read_flat_yaml_registry(
            "research/claims.yaml", "claims", "claim_id"
        )
        decisions = self.read_flat_yaml_registry(
            "research/decisions.yaml", "decisions", "decision_id"
        )
        coverage = self.read_flat_yaml_registry(
            "research/search_coverage.yaml", "direction_coverage", "direction_id"
        )
        resources = self.read_flat_yaml_registry(
            "research/resources.yaml", "snapshots", "resource_id"
        )
        if any(
            registry is None
            for registry in (sources, claims, decisions, coverage, resources)
        ):
            return

        source_ids = self.validate_source_evidence(sources)
        claim_ids, eligible_claim_ids = self.validate_claim_evidence(
            claims,
            source_ids,
            contract_ids.get("研究问题 ID", set()),
            transition_ready,
            source_entries=sources,
        )
        self.check_confirmed_data_evidence(
            research_tables, claim_ids, eligible_claim_ids
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
            contract_ids.get("候选方向 ID", set()),
        )
        query_ids = {
            str(entry.get("query_id"))
            for entry in search_entries
            if isinstance(entry.get("query_id"), str)
        }
        self.validate_search_coverage(
            coverage,
            contract_ids.get("候选方向 ID", set()),
            contract_ids.get("研究问题 ID", set()),
            query_ids,
            source_ids,
            search_required,
            transition_ready,
        )
        self.validate_phase_one_resources(
            resources,
            search_entries,
            claims,
            search_required,
        )
        self.check_phase_one_evidence_quality(
            sources,
            claims,
            search_entries,
            search_required,
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

    def check_confirmed_data_evidence(
        self,
        tables: list[tuple[list[str], list[dict[str, str]]]],
        claim_ids: set[str],
        eligible_claim_ids: set[str],
    ) -> None:
        """Prevent a data choice from outrunning fit and license evidence maturity."""

        data_rows = [
            row
            for headers, rows in tables
            if {
                "数据 ID",
                "来源、版本与许可证",
                "确认状态",
                "证据 ID",
            }.issubset(headers)
            for row in rows
            if re.fullmatch(r"DATA-\d{3}", row.get("数据 ID", ""))
        ]
        for row in data_rows:
            if row.get("确认状态") != "已确认":
                continue
            data_id = row.get("数据 ID", "data")
            evidence_ids = set(re.findall(r"CLM-\d{3}", row.get("证据 ID", "")))
            if not evidence_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_DATA_CONFIRMATION_EVIDENCE_MISSING",
                    "RESEARCH.md",
                    f"{data_id} is confirmed without claim evidence for fit and licensing",
                )
                continue
            unresolved = evidence_ids - claim_ids
            ineligible = evidence_ids - eligible_claim_ids
            if unresolved:
                self.add(
                    "ERROR",
                    "RESEARCH_DATA_CONFIRMATION_EVIDENCE_UNRESOLVED",
                    "RESEARCH.md",
                    f"{data_id} references undefined claims: {', '.join(sorted(unresolved))}",
                )
            if ineligible:
                self.add(
                    "ERROR",
                    "RESEARCH_DATA_CONFIRMATION_EVIDENCE_IMMATURE",
                    "RESEARCH.md",
                    f"{data_id} is confirmed using unverified, conflicting, or contract-ineligible claims: {', '.join(sorted(ineligible))}",
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
                (
                    "title",
                    "accessed_at",
                    "source_type",
                    "independence_group",
                    "version",
                    "license",
                ),
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
                (
                    "contains_restricted_content",
                    "external_transfer_allowed",
                    "locator_exists",
                ),
            )
            quality_level = entry.get("quality_level")
            if (
                not isinstance(quality_level, int)
                or isinstance(quality_level, bool)
                or quality_level not in range(1, 6)
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_SOURCE_QUALITY_LEVEL_INVALID",
                    relative,
                    f"{source_id} quality_level must be an integer from 1 to 5",
                )
            self.require_enum(
                relative,
                source_id,
                entry,
                "usage_role",
                VALID_SOURCE_USAGE_ROLES,
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
                "locator_verification_method",
                VALID_LOCATOR_METHODS,
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
            if entry.get("locator_exists") is True:
                if not entry.get("locator_verified_at") or entry.get(
                    "locator_verification_method"
                ) == "未核验":
                    self.add(
                        "ERROR",
                        "RESEARCH_SOURCE_LOCATOR_VERIFICATION_MISSING",
                        relative,
                        f"{source_id} locator exists without a verification date and method",
                    )
            elif entry.get("usage_role") == "关键证据":
                self.add(
                    "ERROR",
                    "RESEARCH_KEY_SOURCE_LOCATOR_UNVERIFIED",
                    relative,
                    f"{source_id} cannot be key evidence before its locator is verified",
                )
            if quality_level in {4, 5} and entry.get("usage_role") == "关键证据":
                self.add(
                    "ERROR",
                    "RESEARCH_LOW_QUALITY_SOURCE_USED_AS_KEY",
                    relative,
                    f"{source_id} quality level {quality_level} may only be a lead or supplement",
                )
        for entry in entries:
            source_id = entry.get("source_id")
            if not isinstance(source_id, str):
                continue
            primary_source_id = entry.get("primary_source_id")
            if entry.get("provenance_level") == "二手来源":
                if primary_source_id not in source_ids or primary_source_id == source_id:
                    self.add(
                        "ERROR",
                        "RESEARCH_SECONDARY_SOURCE_PRIMARY_UNRESOLVED",
                        relative,
                        f"{source_id} must trace to a different registered primary source",
                    )
            elif primary_source_id is not None:
                self.add(
                    "ERROR",
                    "RESEARCH_PRIMARY_SOURCE_LINK_INVALID",
                    relative,
                    f"{source_id} is an original source and primary_source_id must be null",
                )
        return source_ids

    def validate_claim_evidence(
        self,
        entries: list[dict[str, object]],
        source_ids: set[str],
        rq_ids: set[str],
        transition_ready: bool,
        source_entries: list[dict[str, object]] | None = None,
    ) -> tuple[set[str], set[str]]:
        """Validate claims and return all and contract-eligible claim IDs."""

        relative = "research/claims.yaml"
        claim_ids: set[str] = set()
        eligible_claim_ids: set[str] = set()
        sources_by_id = {
            str(source.get("source_id")): source
            for source in (source_entries or [])
            if isinstance(source.get("source_id"), str)
        }
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
            self.require_boolean_fields(
                relative,
                claim_id,
                entry,
                (
                    "citation_support_verified",
                    "numeric_details_verified",
                    "scope_match_verified",
                    "causality_checked",
                    "adverse_evidence_retained",
                ),
            )
            self.require_enum(
                relative,
                claim_id,
                entry,
                "model_inference_status",
                VALID_MODEL_INFERENCE_STATUSES,
            )
            self.require_enum(
                relative,
                claim_id,
                entry,
                "conflict_type",
                VALID_CLAIM_CONFLICT_TYPES,
            )
            conflict_status = entry.get("conflict_status")
            conflict_type = entry.get("conflict_type")
            if conflict_status == "存在冲突":
                if conflict_type in {"无", None} or not entry.get("conflict_reason"):
                    self.add(
                        "ERROR",
                        "RESEARCH_CLAIM_CONFLICT_DETAIL_MISSING",
                        relative,
                        f"{claim_id} must classify and explain its evidence conflict",
                    )
                if entry.get("adverse_evidence_retained") is not True:
                    self.add(
                        "ERROR",
                        "RESEARCH_CLAIM_ADVERSE_EVIDENCE_NOT_RETAINED",
                        relative,
                        f"{claim_id} conflict cannot be resolved by dropping adverse evidence",
                    )
            elif conflict_status == "无已知冲突" and conflict_type != "无":
                self.add(
                    "ERROR",
                    "RESEARCH_CLAIM_CONFLICT_TYPE_INCONSISTENT",
                    relative,
                    f"{claim_id} has a conflict type without a conflict status",
                )
            if (
                entry.get("support_level") == "间接推论"
                and entry.get("model_inference_status") != "已明确标注"
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_CLAIM_INFERENCE_UNDISCLOSED",
                    relative,
                    f"{claim_id} indirect inference must be explicitly disclosed",
                )
            if sources_by_id:
                claim_source_entries = [
                    sources_by_id[source_id]
                    for source_id in claim_sources
                    if source_id in sources_by_id
                ]
                groups = {
                    str(source.get("independence_group"))
                    for source in claim_source_entries
                    if source.get("independence_group")
                }
                if (
                    entry.get("source_independence") == "独立"
                    and len(groups) < len(claim_source_entries)
                ):
                    self.add(
                        "ERROR",
                        "RESEARCH_CLAIM_SOURCE_INDEPENDENCE_OVERSTATED",
                        relative,
                        f"{claim_id} counts reposts or same-group sources as independent evidence",
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
                incomplete_checks = [
                    field
                    for field in (
                        "citation_support_verified",
                        "numeric_details_verified",
                        "scope_match_verified",
                        "causality_checked",
                        "adverse_evidence_retained",
                    )
                    if entry.get(field) is not True
                ]
                if incomplete_checks:
                    self.add(
                        "ERROR",
                        "RESEARCH_CLAIM_CITATION_CHECK_INCOMPLETE",
                        relative,
                        f"{claim_id} is contract-eligible before checks complete: {', '.join(incomplete_checks)}",
                    )
                if entry.get("model_inference_status") == "未明确标注":
                    self.add(
                        "ERROR",
                        "RESEARCH_CLAIM_INFERENCE_UNDISCLOSED",
                        relative,
                        f"{claim_id} cannot enter the contract with undisclosed model inference",
                    )
                if sources_by_id:
                    quality_levels = [
                        source.get("quality_level")
                        for source in claim_source_entries
                        if isinstance(source.get("quality_level"), int)
                    ]
                    if quality_levels and min(quality_levels) > 2:
                        self.add(
                            "WARN",
                            "RESEARCH_KEY_CLAIM_WITHOUT_HIGH_QUALITY_SOURCE",
                            relative,
                            f"{claim_id} has no level-1 or level-2 source for a key research judgment",
                        )
                    if claim_source_entries and all(
                        source.get("quality_level") in {4, 5}
                        or source.get("usage_role") == "检索线索"
                        for source in claim_source_entries
                    ):
                        self.add(
                            "ERROR",
                            "RESEARCH_CLAIM_SUPPORTED_ONLY_BY_LEADS",
                            relative,
                            f"{claim_id} is supported only by low-quality leads",
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
            if (
                transition_ready
                and affected_fields.intersection({"研究目标", "研究问题"})
                and not alternatives
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_DIRECTION_DECISION_ALTERNATIVES_MISSING",
                    relative,
                    f"{decision_id} selects a research direction without recorded alternatives and rejection reasons",
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
        direction_ids: set[str] | None = None,
    ) -> list[dict[str, object]]:
        """Validate append-only JSONL query provenance and references."""

        active_relative = "research/search_log.jsonl"
        active_path = self.root / active_relative
        if not active_path.is_file():
            return []
        query_ids: set[str] = set()
        parsed_entries: list[dict[str, object]] = []
        archive_root = self.root / "research/archive"
        log_paths = [active_path]
        if archive_root.is_dir():
            log_paths.extend(sorted(archive_root.glob("search_log-*.jsonl")))
        records: list[tuple[str, int, str]] = []
        for log_path in log_paths:
            relative = log_path.relative_to(self.root).as_posix()
            try:
                raw_text = log_path.read_text(encoding="utf-8")
                lines = raw_text.splitlines()
            except (OSError, UnicodeError):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_LOG_INVALID",
                    relative,
                    "search log is not valid UTF-8 text",
                )
                continue
            if log_path == active_path:
                nonempty_line_count = sum(bool(line.strip()) for line in lines)
                if (
                    nonempty_line_count >= SEARCH_LOG_LINE_WARNING
                    or len(raw_text.encode("utf-8")) >= SEARCH_LOG_BYTE_WARNING
                ):
                    self.add(
                        "WARN",
                        "RESEARCH_SEARCH_LOG_ROTATION_REQUIRED",
                        relative,
                        "active search log reached its line or byte rotation threshold",
                    )
            records.extend(
                (relative, line_number, line)
                for line_number, line in enumerate(lines, start=1)
            )
        for relative, line_number, line in records:
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
                r"QRY-\d{3,}", query_id
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
            query_directions = self.require_id_list(
                relative,
                query_id,
                entry,
                "direction_ids",
                re.compile(r"DIR-\d{3}"),
                allow_empty=False,
            )
            query_rqs = self.require_id_list(
                relative,
                query_id,
                entry,
                "research_question_ids",
                re.compile(r"RQ-\d{3}"),
            )
            expected_directions = direction_ids or set()
            for direction_id in sorted(query_directions - expected_directions):
                if transition_ready or expected_directions:
                    self.add(
                        "ERROR",
                        "RESEARCH_QUERY_DIRECTION_UNRESOLVED",
                        relative,
                        f"{query_id} references undefined {direction_id}",
                    )
            search_categories = self.require_string_list(
                relative,
                query_id,
                entry,
                "search_categories",
                allow_empty=False,
            )
            invalid_categories = search_categories - REQUIRED_SEARCH_CATEGORIES
            if invalid_categories:
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_CATEGORY_INVALID",
                    relative,
                    f"{query_id} has unsupported search categories: {', '.join(sorted(invalid_categories))}",
                )
            self.require_string_list(
                relative,
                query_id,
                entry,
                "keyword_variants",
                allow_empty=False,
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
            if not isinstance(entry.get("citation_tracking"), bool):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_CITATION_TRACKING_INVALID",
                    relative,
                    f"{query_id} citation_tracking must be boolean",
                )
            returned_size = entry.get("returned_content_size")
            returned_unit = entry.get("returned_content_unit")
            if returned_unit not in VALID_RETURN_SIZE_UNITS:
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_RETURN_UNIT_INVALID",
                    relative,
                    f"{query_id} returned_content_unit is invalid",
                )
            if returned_size is not None and (
                not isinstance(returned_size, int)
                or isinstance(returned_size, bool)
                or returned_size < 0
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_RETURN_SIZE_INVALID",
                    relative,
                    f"{query_id} returned_content_size must be non-negative or null",
                )
            if (returned_size is None) != (returned_unit == "unavailable"):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_RETURN_SIZE_UNIT_MISMATCH",
                    relative,
                    f"{query_id} return size and unit must consistently represent unavailable data",
                )
            for numeric_field in ("page_count", "external_tool_calls"):
                numeric_value = entry.get(numeric_field)
                if numeric_value is not None and (
                    not isinstance(numeric_value, int)
                    or isinstance(numeric_value, bool)
                    or numeric_value < 0
                ):
                    self.add(
                        "ERROR",
                        "RESEARCH_QUERY_RESOURCE_VALUE_INVALID",
                        relative,
                        f"{query_id} {numeric_field} must be non-negative or null",
                    )
            superseded = entry.get("supersedes_query_id")
            if superseded is not None and not re.fullmatch(
                r"QRY-\d{3,}", str(superseded)
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_QUERY_SUPERSEDES_INVALID",
                    relative,
                    f"{query_id} has an invalid supersedes_query_id",
                )
        return parsed_entries

    def validate_search_coverage(
        self,
        entries: list[dict[str, object]],
        direction_ids: set[str],
        rq_ids: set[str],
        query_ids: set[str],
        source_ids: set[str],
        search_required: bool,
        transition_ready: bool,
    ) -> set[str]:
        """Validate per-direction search breadth and observable stop proxies."""

        relative = "research/search_coverage.yaml"
        covered_direction_ids: set[str] = set()
        for entry in entries:
            missing = sorted(SEARCH_COVERAGE_REQUIRED_FIELDS - entry.keys())
            if missing:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_COVERAGE_FIELDS_MISSING",
                    relative,
                    f"coverage entry is missing: {', '.join(missing)}",
                )
            self.reject_credential_fields(relative, entry)
            self.validate_evidence_minimal_disclosure(relative, entry)
            direction_id = entry.get("direction_id")
            if not isinstance(direction_id, str) or not re.fullmatch(
                r"DIR-\d{3}", direction_id
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_COVERAGE_DIRECTION_INVALID",
                    relative,
                    "direction_id must match DIR-<nnn>",
                )
                continue
            if direction_id in covered_direction_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_COVERAGE_DIRECTION_DUPLICATE",
                    relative,
                    f"{direction_id} has more than one coverage entry",
                )
            covered_direction_ids.add(direction_id)
            if direction_id not in direction_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_COVERAGE_DIRECTION_UNRESOLVED",
                    relative,
                    f"{direction_id} is not defined in RESEARCH.md",
                )
            coverage_rqs = self.require_id_list(
                relative,
                direction_id,
                entry,
                "research_question_ids",
                re.compile(r"RQ-\d{3}"),
            )
            for rq_id in sorted(coverage_rqs - rq_ids):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_COVERAGE_QUESTION_UNRESOLVED",
                    relative,
                    f"{direction_id} references undefined {rq_id}",
                )
            coverage_queries = self.require_id_list(
                relative,
                direction_id,
                entry,
                "query_ids",
                re.compile(r"QRY-\d{3,}"),
                allow_empty=not search_required,
            )
            for query_id in sorted(coverage_queries - query_ids):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_COVERAGE_QUERY_UNRESOLVED",
                    relative,
                    f"{direction_id} references undefined {query_id}",
                )
            coverage = entry.get("coverage")
            coverage_notes = entry.get("coverage_notes")
            if not isinstance(coverage, dict) or set(coverage) != REQUIRED_SEARCH_CATEGORIES:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_CATEGORIES_INCOMPLETE",
                    relative,
                    f"{direction_id} must record all required search categories",
                )
                coverage = {}
            if not isinstance(coverage_notes, dict):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_COVERAGE_NOTES_INVALID",
                    relative,
                    f"{direction_id} coverage_notes must be an object",
                )
                coverage_notes = {}
            for category, category_status in coverage.items():
                if category_status not in VALID_COVERAGE_STATUSES:
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_CATEGORY_STATUS_INVALID",
                        relative,
                        f"{direction_id} {category} has an invalid coverage status",
                    )
                if category_status in {"部分覆盖", "未覆盖", "不适用"} and not str(
                    coverage_notes.get(category, "")
                ).strip():
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_CATEGORY_REASON_MISSING",
                        relative,
                        f"{direction_id} {category} requires a coverage reason",
                    )
            for field in (
                "chinese_keywords",
                "english_keywords",
                "planned_languages",
                "covered_languages",
                "planned_platforms",
                "covered_platforms",
                "uncovered_scope",
            ):
                self.require_string_list(
                    relative,
                    direction_id,
                    entry,
                    field,
                    allow_empty=field == "uncovered_scope" or not search_required,
                )
            citation_sources = self.require_id_list(
                relative,
                direction_id,
                entry,
                "citation_tracking_source_ids",
                re.compile(r"SRC-\d{3}"),
                allow_empty=not search_required,
            )
            for source_id in sorted(citation_sources - source_ids):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_CITATION_SOURCE_UNRESOLVED",
                    relative,
                    f"{direction_id} citation tracking references undefined {source_id}",
                )
            def string_values(field: str) -> set[str]:
                value = entry.get(field)
                return (
                    set(value)
                    if isinstance(value, list)
                    and all(isinstance(item, str) for item in value)
                    else set()
                )

            planned_languages = string_values("planned_languages")
            covered_languages = string_values("covered_languages")
            planned_platforms = string_values("planned_platforms")
            covered_platforms = string_values("covered_platforms")
            if not planned_languages.issubset(covered_languages):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_LANGUAGE_SCOPE_INCOMPLETE",
                    relative,
                    f"{direction_id} has not covered every planned language",
                )
            if not planned_platforms.issubset(covered_platforms):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_PLATFORM_SCOPE_INCOMPLETE",
                    relative,
                    f"{direction_id} has not covered every planned platform",
                )
            for field in ("planned_date_range", "covered_date_range", "last_updated_at"):
                if not isinstance(entry.get(field), str) or not str(entry.get(field)).strip():
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_COVERAGE_TEXT_MISSING",
                        relative,
                        f"{direction_id} {field} must be explicit",
                    )
            yield_history = entry.get("independent_source_yield_history")
            if not isinstance(yield_history, list) or not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and 0 <= value <= 1
                for value in yield_history
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_YIELD_HISTORY_INVALID",
                    relative,
                    f"{direction_id} independent source yield history must contain rates from 0 to 1",
                )
                yield_history = []
            method_history = entry.get("new_method_categories_history")
            if not isinstance(method_history, list) or not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in method_history
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_METHOD_HISTORY_INVALID",
                    relative,
                    f"{direction_id} new method history must contain non-negative integers",
                )
                method_history = []
            for field in (
                "key_questions_covered",
                "counterevidence_completed",
                "citation_tracking_completed",
            ):
                if not isinstance(entry.get(field), bool):
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_STOP_BOOLEAN_INVALID",
                        relative,
                        f"{direction_id} {field} must be boolean",
                    )
            stop_status = entry.get("stop_status")
            if stop_status not in VALID_SEARCH_STOP_STATUSES:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_STOP_STATUS_INVALID",
                    relative,
                    f"{direction_id} has an invalid stop status",
                )
            stopped = stop_status == "已停止"
            if stopped:
                if len(yield_history) < 2 or yield_history[-1] >= yield_history[0]:
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_STOP_YIELD_UNSUPPORTED",
                        relative,
                        f"{direction_id} lacks an observed decline in independent-source yield",
                    )
                if not method_history or method_history[-1] != 0:
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_STOP_METHODS_UNSATURATED",
                        relative,
                        f"{direction_id} latest query batch still adds a method category",
                    )
                if any(value not in {"已覆盖", "不适用"} for value in coverage.values()):
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_STOP_COVERAGE_INCOMPLETE",
                        relative,
                        f"{direction_id} stopped with incomplete search categories",
                    )
                if not all(
                    entry.get(field) is True
                    for field in (
                        "key_questions_covered",
                        "counterevidence_completed",
                        "citation_tracking_completed",
                    )
                ):
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_STOP_PROXY_INCOMPLETE",
                        relative,
                        f"{direction_id} stopped before all observable proxies were met",
                    )
                stop_reason = str(entry.get("stop_reason", "")).strip()
                if not stop_reason or re.search(r"完全检索|穷尽所有|全部文献", stop_reason):
                    self.add(
                        "ERROR",
                        "RESEARCH_SEARCH_STOP_REASON_INVALID",
                        relative,
                        f"{direction_id} must use observable stop reasons rather than completeness claims",
                    )
            if transition_ready and not stopped:
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_NOT_STOPPED",
                    relative,
                    f"{direction_id} has no completed search stop record",
                )
        if search_required:
            for direction_id in sorted(direction_ids - covered_direction_ids):
                self.add(
                    "ERROR",
                    "RESEARCH_SEARCH_COVERAGE_DIRECTION_MISSING",
                    relative,
                    f"{direction_id} has no search coverage record",
                )
        return covered_direction_ids

    def validate_phase_one_resources(
        self,
        entries: list[dict[str, object]],
        search_entries: list[dict[str, object]],
        claims: list[dict[str, object]],
        search_required: bool,
    ) -> None:
        """Validate phase-one usage metrics without enforcing fixed quotas."""

        relative = "research/resources.yaml"
        current_entries: list[dict[str, object]] = []
        resource_ids: set[str] = set()
        for entry in entries:
            missing = sorted(RESOURCE_REQUIRED_FIELDS - entry.keys())
            if missing:
                self.add(
                    "ERROR",
                    "RESEARCH_RESOURCE_FIELDS_MISSING",
                    relative,
                    f"resource snapshot is missing: {', '.join(missing)}",
                )
            self.reject_credential_fields(relative, entry)
            resource_id = entry.get("resource_id")
            if not isinstance(resource_id, str) or not re.fullmatch(
                r"RES-\d{3}", resource_id
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_RESOURCE_ID_INVALID",
                    relative,
                    "resource_id must match RES-<nnn>",
                )
                continue
            if resource_id in resource_ids:
                self.add(
                    "ERROR",
                    "RESEARCH_RESOURCE_ID_DUPLICATE",
                    relative,
                    f"{resource_id} is defined more than once",
                )
            resource_ids.add(resource_id)
            if entry.get("status") not in VALID_RESOURCE_STATUSES:
                self.add(
                    "ERROR",
                    "RESEARCH_RESOURCE_STATUS_INVALID",
                    relative,
                    f"{resource_id} has an invalid status",
                )
            elif entry.get("status") == "当前":
                current_entries.append(entry)
            if not isinstance(entry.get("recorded_at"), str) or not str(
                entry.get("recorded_at")
            ).strip():
                self.add(
                    "ERROR",
                    "RESEARCH_RESOURCE_DATE_MISSING",
                    relative,
                    f"{resource_id} recorded_at must be explicit",
                )
            usage_fields = (
                "input_tokens",
                "output_tokens",
                "search_return_size",
                "search_queries",
                "search_pages",
                "external_tool_calls",
                "api_calls",
                "elapsed_seconds",
                "estimated_cost",
                "evidence_file_bytes",
                "claim_count",
                "context_compactions",
            )
            unavailable = entry.get("unavailable_metrics")
            if not isinstance(unavailable, list) or not all(
                isinstance(item, str) and ":" in item for item in unavailable
            ):
                self.add(
                    "ERROR",
                    "RESEARCH_RESOURCE_UNAVAILABLE_METRICS_INVALID",
                    relative,
                    f"{resource_id} unavailable_metrics must use field: reason strings",
                )
                unavailable_names: set[str] = set()
            else:
                unavailable_names = {item.split(":", 1)[0] for item in unavailable}
            for field in usage_fields:
                value = entry.get(field)
                if value is None:
                    if field not in unavailable_names:
                        self.add(
                            "ERROR",
                            "RESEARCH_RESOURCE_NULL_REASON_MISSING",
                            relative,
                            f"{resource_id} {field} is null without an unavailable reason",
                        )
                elif (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or value < 0
                ):
                    self.add(
                        "ERROR",
                        "RESEARCH_RESOURCE_USAGE_INVALID",
                        relative,
                        f"{resource_id} {field} must be non-negative or null",
                    )
            if entry.get("search_return_unit") not in VALID_RETURN_SIZE_UNITS:
                self.add(
                    "ERROR",
                    "RESEARCH_RESOURCE_RETURN_UNIT_INVALID",
                    relative,
                    f"{resource_id} search_return_unit is invalid",
                )
            self.require_nonempty_string_fields(
                relative, resource_id, entry, ("cost_currency",)
            )
        if search_required and len(current_entries) != 1:
            self.add(
                "ERROR",
                "RESEARCH_RESOURCE_CURRENT_SNAPSHOT_INVALID",
                relative,
                "exactly one current phase-one resource snapshot is required before SEARCH",
            )
        if not current_entries:
            return
        current = current_entries[0]

        if current.get("search_queries") != len(search_entries):
            self.add(
                "WARN",
                "RESEARCH_RESOURCE_QUERY_COUNT_MISMATCH",
                relative,
                "resource search_queries does not match parsed search-log entries",
            )
        if current.get("claim_count") != len(claims):
            self.add(
                "WARN",
                "RESEARCH_RESOURCE_CLAIM_COUNT_MISMATCH",
                relative,
                "resource claim_count does not match claims.yaml",
            )
        evidence_bytes = self.phase_one_evidence_bytes()
        recorded_bytes = current.get("evidence_file_bytes")
        if isinstance(recorded_bytes, (int, float)) and recorded_bytes != evidence_bytes:
            self.add(
                "WARN",
                "RESEARCH_RESOURCE_EVIDENCE_BYTES_MISMATCH",
                relative,
                "recorded evidence_file_bytes does not match current evidence files",
            )

    def phase_one_evidence_bytes(self) -> int:
        """Return bytes of committable phase-one evidence, excluding local-only stores."""

        research_root = self.root / "research"
        if not research_root.is_dir():
            return 0
        total = 0
        for path in research_root.rglob("*"):
            if not path.is_file() or path.name == "README.md":
                continue
            relative_parts = path.relative_to(research_root).parts
            if relative_parts and relative_parts[0] in {
                "private",
                "raw",
                "source_files",
            }:
                continue
            total += path.stat().st_size
        return total

    def check_phase_one_evidence_quality(
        self,
        sources: list[dict[str, object]],
        claims: list[dict[str, object]],
        search_entries: list[dict[str, object]],
        search_required: bool,
        transition_ready: bool,
    ) -> None:
        """Emit bounded quality warnings without pretending to judge research merit."""

        if search_required and not search_entries:
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
        for path in directory.iterdir():
            if path.name in ignored_names or path.name.startswith("."):
                continue
            if path.is_file():
                return True
            if path.is_dir() and any(
                child.name not in ignored_names and not child.name.startswith(".")
                for child in path.rglob("*")
            ):
                return True
        return False

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
            for field, pattern in (
                ("research_question_ids", r"RQ-\d{3}"),
                ("success_criterion_ids", r"SC-\d{3}"),
                ("decision_ids", r"DEC-\d{3}"),
            ):
                identifiers = metadata.get(field)
                if not isinstance(identifiers, list) or not identifiers or any(
                    not isinstance(identifier, str)
                    or not re.fullmatch(pattern, identifier)
                    for identifier in identifiers
                ):
                    self.add(
                        "ERROR",
                        "RUN_CONTRACT_REFERENCES_INVALID",
                        relative,
                        f"metadata {field} must be a non-empty valid ID array",
                    )
            self.check_run_resources(metadata, relative)
            required = (
                (
                    "command.txt",
                    "config_snapshot.json",
                    "environment.json",
                    "script_path.txt",
                    "metrics.json",
                    "run.log",
                    "status.json",
                    "events.jsonl",
                    "heartbeat.json",
                )
                if status == "success"
                else ("run.log", "status.json", "events.jsonl", "heartbeat.json")
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
            if status == "success":
                self.check_success_run_reproducibility(metadata, run_dir, relative)
            self.check_archived_run_progress(run_dir, relative, status)

    def check_archived_run_progress(
        self, run_dir: Path, relative: str, run_status: str
    ) -> None:
        """Validate the final progress snapshot archived with a run."""

        status_path = run_dir / "status.json"
        heartbeat_path = run_dir / "heartbeat.json"
        events_path = run_dir / "events.jsonl"
        if not all(path.is_file() for path in (status_path, heartbeat_path, events_path)):
            return
        task_status = self.read_json(status_path, "RUN_PROGRESS_STATUS_INVALID")
        heartbeat = self.read_json(heartbeat_path, "RUN_PROGRESS_HEARTBEAT_INVALID")
        if task_status is not None:
            expected = "success" if run_status == "success" else "failed"
            if task_status.get("status") != expected:
                self.add(
                    "ERROR",
                    "RUN_PROGRESS_STATUS_MISMATCH",
                    relative,
                    f"archived task status must be {expected}",
                )
        if task_status is not None and heartbeat is not None and heartbeat.get(
            "task_run_id"
        ) != task_status.get("task_run_id"):
            self.add(
                "ERROR",
                "RUN_PROGRESS_HEARTBEAT_MISMATCH",
                relative,
                "archived heartbeat does not match the task status",
            )
        try:
            event_lines = events_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            event_lines = []
        if not event_lines:
            self.add(
                "ERROR",
                "RUN_PROGRESS_EVENTS_MISSING",
                relative,
                "archived events.jsonl must contain progress events",
            )

    def check_success_run_reproducibility(
        self, metadata: dict[str, object], run_dir: Path, relative: str
    ) -> None:
        """Check successful runs for data, seed, environment, and usage evidence."""

        data_versions = metadata.get("data_versions")
        if not isinstance(data_versions, list) or not data_versions:
            self.add(
                "ERROR",
                "RUN_DATA_VERSION_MISSING",
                relative,
                "successful run must record at least one data version and checksum",
            )
        else:
            for index, item in enumerate(data_versions, start=1):
                if not isinstance(item, dict) or any(
                    not item.get(field)
                    for field in ("data_id", "version", "checksum", "checksum_algorithm")
                ):
                    self.add(
                        "ERROR",
                        "RUN_DATA_VERSION_INVALID",
                        relative,
                        f"data_versions item {index} lacks ID, version, checksum, or algorithm",
                    )
        if "random_seed" not in metadata:
            self.add(
                "ERROR",
                "RUN_RANDOM_SEED_MISSING",
                relative,
                "successful run must record random_seed, using null only when inapplicable",
            )
        metrics_path = run_dir / "metrics.json"
        metrics = (
            self.read_json(metrics_path, "RUN_JSON_INVALID")
            if metrics_path.is_file()
            else None
        )
        resources = metadata.get("resources")
        gpu = resources.get("gpu") if isinstance(resources, dict) else None
        api = resources.get("api") if isinstance(resources, dict) else None
        if isinstance(gpu, dict) and gpu.get("enabled") is True:
            missing_gpu_metadata = [
                field
                for field in ("cuda_version", "pytorch_version", "available_vram_bytes")
                if gpu.get(field) is None or gpu.get(field) in ("", "TODO")
            ]
            if missing_gpu_metadata:
                self.add(
                    "ERROR",
                    "RUN_GPU_ENVIRONMENT_MISSING",
                    relative,
                    f"GPU run is missing: {', '.join(missing_gpu_metadata)}",
                )
            gpu_metrics = metrics.get("gpu") if isinstance(metrics, dict) else None
            if not isinstance(gpu_metrics, dict) or any(
                field not in gpu_metrics
                for field in ("gpu_seconds", "peak_vram_bytes", "training_steps")
            ):
                self.add(
                    "ERROR",
                    "RUN_GPU_USAGE_MISSING",
                    relative,
                    "GPU metrics must record GPU seconds, peak VRAM, and training steps",
                )
        if isinstance(api, dict) and api.get("enabled") is True:
            api_metrics = metrics.get("api") if isinstance(metrics, dict) else None
            api_fields = (
                "calls",
                "successes",
                "failures",
                "retries",
                "rate_limits",
                "input_tokens",
                "output_tokens",
                "elapsed_seconds",
                "estimated_cost",
                "cost_currency",
            )
            if not isinstance(api_metrics, dict) or any(
                field not in api_metrics for field in api_fields
            ):
                self.add(
                    "ERROR",
                    "RUN_API_USAGE_MISSING",
                    relative,
                    "API metrics must record calls, outcomes, retries, tokens, time, and cost",
                )

    def check_experiment_reconciliation(self) -> None:
        """Reconcile experiment registry entries with local immutable runs."""

        relative = "experiments/registry.yaml"
        path = self.root / relative
        run_records: dict[str, dict[str, object]] = {}
        runs_root = self.root / "experiments/runs"
        if runs_root.is_dir():
            for run_dir in sorted(item for item in runs_root.iterdir() if item.is_dir()):
                metadata_path = run_dir / "metadata.json"
                if metadata_path.is_file():
                    metadata = self.read_json(
                        metadata_path, "EXPERIMENT_RECONCILIATION_RUN_INVALID"
                    )
                    if metadata is not None:
                        run_records[run_dir.name] = metadata
        if not path.is_file():
            if run_records:
                self.add(
                    "ERROR",
                    "EXPERIMENT_REGISTRY_MISSING_FOR_RUNS",
                    relative,
                    "local run records exist but experiments/registry.yaml is missing",
                )
            return
        entries = self.read_flat_yaml_registry(relative, "experiments", "experiment_id")
        if entries is None:
            return
        registry_run_ids: set[str] = set()
        registry_experiment_ids: set[str] = set()
        for entry in entries:
            experiment_id = entry.get("experiment_id")
            if not isinstance(experiment_id, str) or not re.fullmatch(
                r"exp-\d{3}", experiment_id
            ):
                self.add(
                    "ERROR",
                    "EXPERIMENT_REGISTRY_ID_INVALID",
                    relative,
                    "experiment_id must match exp-<nnn>",
                )
                continue
            registry_experiment_ids.add(experiment_id)
            status = entry.get("status")
            if status not in {
                "planned",
                "queued",
                "running",
                "blocked",
                "failed",
                "completed",
            }:
                self.add(
                    "ERROR",
                    "EXPERIMENT_REGISTRY_STATUS_INVALID",
                    relative,
                    f"{experiment_id} has an unsupported status",
                )
            runs = entry.get("runs")
            if not isinstance(runs, list):
                self.add(
                    "ERROR",
                    "EXPERIMENT_REGISTRY_RUNS_INVALID",
                    relative,
                    f"{experiment_id} runs must be a JSON array",
                )
                continue
            successful_runs = 0
            for run_id in runs:
                if not isinstance(run_id, str):
                    self.add(
                        "ERROR",
                        "EXPERIMENT_REGISTRY_RUN_ID_INVALID",
                        relative,
                        f"{experiment_id} contains a non-string run ID",
                    )
                    continue
                registry_run_ids.add(run_id)
                metadata = run_records.get(run_id)
                if metadata is None:
                    self.add(
                        "ERROR",
                        "EXPERIMENT_REGISTRY_RUN_MISSING",
                        relative,
                        f"registered run does not exist locally: {run_id}",
                    )
                    continue
                if metadata.get("experiment_id") != experiment_id:
                    self.add(
                        "ERROR",
                        "EXPERIMENT_REGISTRY_RUN_MISMATCH",
                        relative,
                        f"{run_id} belongs to a different experiment",
                    )
                if metadata.get("status") == "success":
                    successful_runs += 1
            if status == "planned" and runs:
                self.add(
                    "ERROR",
                    "EXPERIMENT_REGISTRY_PLANNED_WITH_RUNS",
                    relative,
                    f"{experiment_id} is planned but already lists local runs",
                )
            if status == "completed" and successful_runs == 0:
                self.add(
                    "ERROR",
                    "EXPERIMENT_REGISTRY_COMPLETED_WITHOUT_SUCCESS",
                    relative,
                    f"{experiment_id} is completed without a successful local run",
                )
        for run_id, metadata in run_records.items():
            experiment_id = metadata.get("experiment_id")
            if run_id not in registry_run_ids:
                self.add(
                    "ERROR",
                    "EXPERIMENT_RUN_UNREGISTERED",
                    f"experiments/runs/{run_id}",
                    "local run is not listed in experiments/registry.yaml",
                )
            if isinstance(experiment_id, str) and experiment_id not in registry_experiment_ids:
                self.add(
                    "ERROR",
                    "EXPERIMENT_RUN_EXPERIMENT_UNREGISTERED",
                    f"experiments/runs/{run_id}",
                    f"run experiment is absent from registry: {experiment_id}",
                )

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

    def check_task_progress(self) -> None:
        """Validate observable stage-two and stage-three task records."""

        roots = (
            ("workflow/tasks", "stage_two"),
            ("paper/sessions", "stage_three"),
        )
        required_status_fields = {
            "schema_version",
            "task_run_id",
            "stage",
            "task_kind",
            "label",
            "status",
            "step",
            "completed",
            "total",
            "started_at",
            "updated_at",
            "resources",
            "outputs",
        }
        for relative_root, expected_stage in roots:
            task_root = self.root / relative_root
            if not task_root.is_dir():
                continue
            for task_dir in sorted(path for path in task_root.iterdir() if path.is_dir()):
                relative = task_dir.relative_to(self.root).as_posix()
                paths = {
                    name: task_dir / name
                    for name in ("status.json", "events.jsonl", "heartbeat.json")
                }
                missing_files = [name for name, path in paths.items() if not path.is_file()]
                if missing_files:
                    self.add(
                        "ERROR",
                        "TASK_PROGRESS_FILES_MISSING",
                        relative,
                        f"task progress is missing: {', '.join(missing_files)}",
                    )
                    continue
                status = self.read_json(paths["status.json"], "TASK_STATUS_INVALID")
                heartbeat = self.read_json(
                    paths["heartbeat.json"], "TASK_HEARTBEAT_INVALID"
                )
                if status is None or heartbeat is None:
                    continue
                missing_fields = sorted(required_status_fields - status.keys())
                if missing_fields:
                    self.add(
                        "ERROR",
                        "TASK_STATUS_FIELDS_MISSING",
                        relative,
                        f"status.json is missing: {', '.join(missing_fields)}",
                    )
                if status.get("stage") != expected_stage:
                    self.add(
                        "ERROR",
                        "TASK_STAGE_INVALID",
                        relative,
                        f"task under {relative_root} must use stage {expected_stage}",
                    )
                task_status = status.get("status")
                if task_status not in {"queued", "running", "blocked", "failed", "success"}:
                    self.add(
                        "ERROR",
                        "TASK_STATUS_VALUE_INVALID",
                        relative,
                        "task status must be queued, running, blocked, failed, or success",
                    )
                if task_status == "blocked" and (
                    not status.get("blocked_reason")
                    or not status.get("resume_condition")
                ):
                    self.add(
                        "ERROR",
                        "TASK_BLOCKER_DETAILS_MISSING",
                        relative,
                        "blocked task must record a reason and resume condition",
                    )
                if task_status == "failed" and not status.get("blocked_reason"):
                    self.add(
                        "ERROR",
                        "TASK_FAILURE_REASON_MISSING",
                        relative,
                        "failed task must record its failure reason",
                    )
                completed = status.get("completed")
                total = status.get("total")
                if not isinstance(completed, int) or completed < 0:
                    self.add(
                        "ERROR",
                        "TASK_PROGRESS_VALUE_INVALID",
                        relative,
                        "completed must be a non-negative integer",
                    )
                if total is not None and (
                    not isinstance(total, int)
                    or total < 0
                    or (isinstance(completed, int) and completed > total)
                ):
                    self.add(
                        "ERROR",
                        "TASK_PROGRESS_VALUE_INVALID",
                        relative,
                        "total must be null or a non-negative integer not below completed",
                    )
                if (
                    task_status == "success"
                    and isinstance(total, int)
                    and total > 0
                    and completed != total
                ):
                    self.add(
                        "ERROR",
                        "TASK_SUCCESS_INCOMPLETE",
                        relative,
                        "successful task must complete its declared total",
                    )
                if heartbeat.get("task_run_id") != status.get("task_run_id"):
                    self.add(
                        "ERROR",
                        "TASK_HEARTBEAT_ID_MISMATCH",
                        relative,
                        "heartbeat task_run_id does not match status.json",
                    )
                heartbeat_at = self.parse_iso_datetime(heartbeat.get("heartbeat_at"))
                if heartbeat_at is None:
                    self.add(
                        "ERROR",
                        "TASK_HEARTBEAT_TIME_INVALID",
                        relative,
                        "heartbeat_at must be a timezone-aware ISO timestamp",
                    )
                elif task_status == "running" and (
                    datetime.now(timezone.utc) - heartbeat_at
                ).total_seconds() > 120:
                    self.add(
                        "WARN",
                        "TASK_HEARTBEAT_STALE",
                        relative,
                        "running task heartbeat is older than 120 seconds",
                    )
                try:
                    event_lines = paths["events.jsonl"].read_text(
                        encoding="utf-8"
                    ).splitlines()
                except (OSError, UnicodeError):
                    event_lines = []
                if not event_lines:
                    self.add(
                        "ERROR",
                        "TASK_EVENTS_MISSING",
                        relative,
                        "events.jsonl must contain at least one event",
                    )
                for line_number, line in enumerate(event_lines, start=1):
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        self.add(
                            "ERROR",
                            "TASK_EVENT_INVALID",
                            relative,
                            f"events.jsonl line {line_number} is invalid JSON",
                        )
                        continue
                    if not isinstance(event, dict) or event.get("task_run_id") != status.get(
                        "task_run_id"
                    ):
                        self.add(
                            "ERROR",
                            "TASK_EVENT_ID_MISMATCH",
                            relative,
                            f"events.jsonl line {line_number} has the wrong task_run_id",
                        )

    def check_stage_two_handoff(self, *, required: bool) -> None:
        """Require a reconciled evidence handoff before stage three."""

        relative = "experiments/evidence_handoff.yaml"
        path = self.root / relative
        if not path.is_file():
            if required:
                self.add(
                    "ERROR",
                    "STAGE_TWO_HANDOFF_MISSING",
                    relative,
                    "stage two must produce an evidence handoff before stage three",
                )
            return
        entries = self.read_flat_yaml_registry(relative, "handoffs", "handoff_id")
        if entries is None:
            return
        if required and len(entries) != 1:
            self.add(
                "ERROR",
                "STAGE_TWO_HANDOFF_COUNT_INVALID",
                relative,
                "exactly one current evidence handoff is required",
            )
        required_fields = {
            "handoff_id",
            "research_question_ids",
            "success_criterion_ids",
            "experiment_ids",
            "run_ids",
            "supported_claims",
            "unsupported_claims",
            "negative_results",
            "limitations",
            "local_evidence_verified",
            "registry_reconciled",
            "completed_at",
        }
        for entry in entries:
            missing = sorted(required_fields - entry.keys())
            if missing:
                self.add(
                    "ERROR",
                    "STAGE_TWO_HANDOFF_FIELDS_MISSING",
                    relative,
                    f"handoff is missing: {', '.join(missing)}",
                )
            handoff_id = entry.get("handoff_id")
            if not isinstance(handoff_id, str) or not re.fullmatch(
                r"HANDOFF-\d{3}", handoff_id
            ):
                self.add(
                    "ERROR",
                    "STAGE_TWO_HANDOFF_ID_INVALID",
                    relative,
                    "handoff_id must match HANDOFF-<nnn>",
                )
            for flag in ("local_evidence_verified", "registry_reconciled"):
                if entry.get(flag) is not True:
                    self.add(
                        "ERROR",
                        "STAGE_TWO_HANDOFF_UNRECONCILED",
                        relative,
                        f"{flag} must be true before stage three",
                    )
            if self.parse_iso_datetime(entry.get("completed_at")) is None:
                self.add(
                    "ERROR",
                    "STAGE_TWO_HANDOFF_TIME_INVALID",
                    relative,
                    "completed_at must be a timezone-aware ISO timestamp",
                )
            experiment_ids = entry.get("experiment_ids")
            if not isinstance(experiment_ids, list) or not experiment_ids:
                self.add(
                    "ERROR",
                    "STAGE_TWO_HANDOFF_EXPERIMENTS_MISSING",
                    relative,
                    "handoff must identify at least one experiment",
                )
            run_ids = entry.get("run_ids")
            if required and (not isinstance(run_ids, list) or not run_ids):
                self.add(
                    "ERROR",
                    "STAGE_TWO_HANDOFF_RUNS_MISSING",
                    relative,
                    "handoff must identify at least one successful local run",
                )
                continue
            if isinstance(run_ids, list):
                for run_id in run_ids:
                    run_relative = f"experiments/runs/{run_id}"
                    metadata_path = self.root / run_relative / "metadata.json"
                    metadata = (
                        self.read_json(metadata_path, "STAGE_TWO_HANDOFF_RUN_INVALID")
                        if metadata_path.is_file()
                        else None
                    )
                    if metadata is None or metadata.get("status") != "success":
                        self.add(
                            "ERROR",
                            "STAGE_TWO_HANDOFF_RUN_INVALID",
                            relative,
                            f"handoff run is missing locally or not successful: {run_id}",
                        )
                    elif isinstance(experiment_ids, list) and metadata.get(
                        "experiment_id"
                    ) not in experiment_ids:
                        self.add(
                            "ERROR",
                            "STAGE_TWO_HANDOFF_RUN_MISMATCH",
                            relative,
                            f"handoff run belongs to an unlisted experiment: {run_id}",
                        )

    def check_stage_three_session_completion(
        self, phase: str | None, status: str | None
    ) -> None:
        """Require a successful observable writing session for completion."""

        if phase != "阶段三：论文写作" or status != "已完成":
            return
        sessions_root = self.root / "paper/sessions"
        successful = False
        if sessions_root.is_dir():
            for session_dir in sessions_root.iterdir():
                if not session_dir.is_dir():
                    continue
                status_path = session_dir / "status.json"
                if not status_path.is_file():
                    continue
                session = self.read_json(status_path, "STAGE_THREE_SESSION_INVALID")
                if session is not None and session.get("status") == "success":
                    successful = True
        if not successful:
            self.add(
                "ERROR",
                "STAGE_THREE_SESSION_INCOMPLETE",
                "paper/sessions",
                "completed stage three requires at least one successful writing session",
            )

    @staticmethod
    def parse_iso_datetime(value: object) -> datetime | None:
        """Return a timezone-aware datetime for a valid ISO timestamp."""

        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)

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
