"""Regression tests for the read-only workspace validator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.validate_workspace import REQUIRED_SEARCH_CATEGORIES, WorkspaceValidator
from src.runtime.progress import TaskProgress


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class WorkspaceValidatorTests(unittest.TestCase):
    """Cover phase-one contract, evidence, and migration safeguards."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_research(self, text: str) -> None:
        """Write a test research contract."""

        (self.root / "RESEARCH.md").write_text(text, encoding="utf-8")

    @staticmethod
    def codes(validator: WorkspaceValidator) -> set[str]:
        """Return finding codes for compact assertions."""

        return {finding.code for finding in validator.findings}

    def test_initial_stage_one_contract_is_structurally_legal(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        self.write_research(template)
        validator = WorkspaceValidator(self.root)

        phase, status = validator.check_stage_state()
        validator.check_research_contract(phase, status)

        errors = [item for item in validator.findings if item.severity == "ERROR"]
        self.assertEqual([], errors)
        self.assertNotIn("RESEARCH_SEARCH_LOG_EMPTY", self.codes(validator))

    def test_pending_field_blocks_stage_transition(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        self.write_research(template)
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract("阶段二：实验与分析", "进行中")

        self.assertIn("RESEARCH_CONFIRMATION_BLOCKING", self.codes(validator))

    def test_stage_two_requires_failure_rule(self) -> None:
        self.write_research((REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8"))
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract("阶段二：实验与分析", "进行中")

        self.assertIn("RESEARCH_STAGE_TWO_STOP_RULE_MISSING", self.codes(validator))

    def test_claim_with_missing_source_is_rejected(self) -> None:
        validator = WorkspaceValidator(self.root)
        claim = self.valid_claim(source_ids=["SRC-999"])

        validator.validate_claim_evidence([claim], set(), {"RQ-001"}, False)

        self.assertIn("RESEARCH_CLAIM_SOURCE_UNRESOLVED", self.codes(validator))

    def test_decision_with_invalid_claim_reference_is_rejected(self) -> None:
        validator = WorkspaceValidator(self.root)
        decision = self.valid_decision(supporting_claim_ids=["CLM-999"])

        validator.validate_decision_evidence([decision], set(), False)

        self.assertIn("RESEARCH_DECISION_CLAIM_UNRESOLVED", self.codes(validator))

    def test_research_reference_to_missing_decision_is_rejected(self) -> None:
        validator = WorkspaceValidator(self.root)
        tables = [
            (
                ["合同字段", "决策 ID", "证据 ID"],
                [{"合同字段": "研究目标", "决策 ID": "DEC-999", "证据 ID": "不适用"}],
            )
        ]

        validator.validate_contract_evidence_references(tables, set(), set(), set())

        self.assertIn("RESEARCH_DECISION_REFERENCE_UNRESOLVED", self.codes(validator))

    def test_large_research_contract_emits_warning(self) -> None:
        validator = WorkspaceValidator(self.root)
        oversized = "\n".join(f"line {index}" for index in range(700))

        validator.check_research_contract_quality(oversized, [], False)

        self.assertIn("RESEARCH_CONTRACT_TOO_LARGE", self.codes(validator))

    def test_credential_field_in_evidence_is_rejected(self) -> None:
        research = self.root / "research"
        research.mkdir()
        entry = self.valid_search_entry(
            research_question_ids=[],
            included_source_ids=[],
            api_key="placeholder",
        )
        (research / "search_log.jsonl").write_text(
            json.dumps(entry) + "\n", encoding="utf-8"
        )
        validator = WorkspaceValidator(self.root)

        validator.validate_search_log(set(), set(), False)

        self.assertIn(
            "RESEARCH_EVIDENCE_CREDENTIAL_FIELD_FORBIDDEN", self.codes(validator)
        )

    def test_not_applicable_field_requires_reason(self) -> None:
        text = self.contract_table("不适用", "不适用")
        self.write_research(text)
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract("阶段一：调研与设计", "未开始")

        self.assertIn("RESEARCH_NOT_APPLICABLE_REASON_MISSING", self.codes(validator))

    def test_conflict_status_blocks_stage_transition(self) -> None:
        text = self.contract_table("存在冲突", "存在两个互斥的数据许可解释")
        self.write_research(text)
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract("阶段二：实验与分析", "进行中")

        self.assertIn("RESEARCH_CONFIRMATION_BLOCKING", self.codes(validator))

    def test_legacy_contract_without_substate_has_migration_error(self) -> None:
        self.write_research(
            "\n".join(
                (
                    "- 当前阶段：阶段一：调研与设计。",
                    "- 阶段状态：未开始。",
                    "- 阶段门禁：待检查。",
                    "- 停止原因：不适用。",
                    "- 恢复条件：不适用。",
                )
            )
        )
        validator = WorkspaceValidator(self.root)

        phase, status = validator.check_stage_state()
        validator.check_research_contract(phase, status)

        codes = self.codes(validator)
        self.assertIn("INVALID_PHASE_ONE_STATE", codes)
        self.assertIn("RESEARCH_INTAKE_TABLE_MISSING", codes)
        self.assertIn("RESEARCH_DIRECTION_TABLE_MISSING", codes)

    def test_in_progress_stage_one_can_save_partial_contract(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        partial = template.replace("阶段一子状态：INTAKE", "阶段一子状态：DIVERGE")
        partial = partial.replace("阶段状态：未开始", "阶段状态：进行中")
        partial = partial.replace("阶段门禁：待检查", "阶段门禁：已通过")
        partial = partial.replace(
            "| 用户研究意图 | 待形成 | 尚无 | 待澄清 | 尚无 | 待分配 |",
            "| 用户研究意图 | 探索可复现方向 | 用户 | 暂定 | 轮次 1 | 待分配 |",
        )
        self.write_research(partial)
        self.copy_empty_research_evidence()
        validator = WorkspaceValidator(self.root)

        validator.check_requirement_intake(
            validator.parse_markdown_tables(partial), "DIVERGE", False
        )

        errors = [item for item in validator.findings if item.severity == "ERROR"]
        self.assertEqual([], errors)

    def test_broad_direction_cannot_be_promoted_directly_to_draft(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        broad_draft = template.replace("阶段一子状态：INTAKE", "阶段一子状态：DRAFT")
        self.write_research(broad_draft)
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract("阶段一：调研与设计", "进行中")

        codes = self.codes(validator)
        self.assertIn("RESEARCH_INTAKE_INCOMPLETE_FOR_SEARCH", codes)
        self.assertIn("RESEARCH_DIRECTION_CANDIDATES_INSUFFICIENT", codes)

    def test_search_allows_one_formal_direction(self) -> None:
        validator = WorkspaceValidator(self.root)
        headers = ["候选方向 ID", "核心问题", "创新性假设", "最小验证路径", "主要风险", "状态", "选择、合并或否决理由", "决策 ID"]
        rows = [{"候选方向 ID": "DIR-001", "核心问题": "问题", "创新性假设": "假设", "最小验证路径": "实验", "主要风险": "重合", "状态": "入围", "选择、合并或否决理由": "待验证", "决策 ID": "待分配"}]

        validator.check_candidate_directions(
            [(headers, rows)],
            "SEARCH",
            False,
            {},
        )

        self.assertNotIn(
            "RESEARCH_DIRECTION_CANDIDATES_INSUFFICIENT", self.codes(validator)
        )

    def test_search_requires_all_direction_fields_but_not_execution_fields(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        for field in ("用户研究意图", "研究对象", "核心问题", "创新性假设", "最小可证伪路径", "范围边界"):
            template = template.replace(
                f"| {field} | 待形成 | 尚无 | 待澄清 | 尚无 | 待分配 |",
                f"| {field} | 可工作的方向信息 | 用户 | 暂定 | 轮次 1 | 待分配 |",
            )
        validator = WorkspaceValidator(self.root)
        validator.check_requirement_intake(
            validator.parse_markdown_tables(template), "SEARCH", False
        )

        self.assertNotIn(
            "RESEARCH_INTAKE_INCOMPLETE_FOR_SEARCH", self.codes(validator)
        )

    def test_search_requires_interaction_record_and_alternative_check(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        validator = WorkspaceValidator(self.root)
        tables = validator.parse_markdown_tables(template)

        validator.check_brainstorm(tables, template, "SEARCH", False)

        codes = self.codes(validator)
        self.assertIn("RESEARCH_BRAINSTORM_RECORD_MISSING", codes)
        self.assertIn("RESEARCH_ALTERNATIVE_DIRECTION_CHECK_MISSING", codes)

    def test_transition_history_rejects_skipped_state(self) -> None:
        validator = WorkspaceValidator(self.root)
        headers = [
            "切换 ID",
            "日期",
            "原阶段",
            "新阶段",
            "门禁结果",
            "原因或授权",
            "决策 ID",
        ]
        rows = [
            {
                "切换 ID": "TRANS-001",
                "日期": "2026-07-23",
                "原阶段": "INTAKE",
                "新阶段": "SEARCH",
                "门禁结果": "已通过",
                "原因或授权": "错误地跳过头脑风暴",
                "决策 ID": "DEC-001",
            }
        ]

        validator.check_transition_history(
            [(headers, rows)], "阶段一：调研与设计", "SEARCH", "进行中", False
        )

        self.assertIn("RESEARCH_TRANSITION_STEP_SKIPPED", self.codes(validator))

    def test_confirmed_data_rejects_immature_claim_evidence(self) -> None:
        validator = WorkspaceValidator(self.root)
        headers = [
            "数据 ID",
            "当前值",
            "来源、版本与许可证",
            "信息来源",
            "确认状态",
            "最近确认日期或轮次",
            "决策 ID",
            "证据 ID",
        ]
        rows = [
            {
                "数据 ID": "DATA-001",
                "当前值": "候选数据",
                "来源、版本与许可证": "许可仍待核验",
                "信息来源": "用户偏好",
                "确认状态": "已确认",
                "最近确认日期或轮次": "2026-07-23",
                "决策 ID": "DEC-001",
                "证据 ID": "CLM-001",
            }
        ]

        validator.check_confirmed_data_evidence(
            [(headers, rows)], {"CLM-001"}, set()
        )

        self.assertIn(
            "RESEARCH_DATA_CONFIRMATION_EVIDENCE_IMMATURE",
            self.codes(validator),
        )

    def test_multiple_final_directions_are_rejected(self) -> None:
        validator = WorkspaceValidator(self.root)
        headers = ["候选方向 ID", "核心问题", "创新性假设", "最小验证路径", "主要风险", "状态", "选择、合并或否决理由", "决策 ID"]
        rows = [
            {"候选方向 ID": "DIR-001", "核心问题": "问题一", "创新性假设": "假设一", "最小验证路径": "实验一", "主要风险": "风险一", "状态": "已选定", "选择、合并或否决理由": "选择", "决策 ID": "DEC-001"},
            {"候选方向 ID": "DIR-002", "核心问题": "问题二", "创新性假设": "假设二", "最小验证路径": "实验二", "主要风险": "风险二", "状态": "已选定", "选择、合并或否决理由": "选择", "决策 ID": "DEC-001"},
        ]

        validator.check_candidate_directions(
            [(headers, rows)],
            "GATE_CHECK",
            True,
            {},
        )

        self.assertIn("RESEARCH_DIRECTION_FINAL_NOT_UNIQUE", self.codes(validator))

    def test_search_stop_requires_coverage_and_observable_proxies(self) -> None:
        validator = WorkspaceValidator(self.root)
        coverage = self.valid_search_coverage(
            coverage={
                **{category: "已覆盖" for category in REQUIRED_SEARCH_CATEGORIES},
                "失败和负面结果": "未覆盖",
            },
            coverage_notes={"失败和负面结果": "尚未执行反证检索"},
            new_method_categories_history=[1, 1],
            counterevidence_completed=False,
            stop_reason="已经完全检索全部文献",
        )

        validator.validate_search_coverage(
            [coverage],
            {"DIR-001"},
            {"RQ-001"},
            {"QRY-001"},
            {"SRC-001"},
            True,
            True,
        )

        codes = self.codes(validator)
        self.assertIn("RESEARCH_SEARCH_STOP_METHODS_UNSATURATED", codes)
        self.assertIn("RESEARCH_SEARCH_STOP_COVERAGE_INCOMPLETE", codes)
        self.assertIn("RESEARCH_SEARCH_STOP_PROXY_INCOMPLETE", codes)
        self.assertIn("RESEARCH_SEARCH_STOP_REASON_INVALID", codes)

    def test_feasibility_blocker_can_stop_without_fabricated_saturation(self) -> None:
        validator = WorkspaceValidator(self.root)
        coverage = self.valid_search_coverage(
            coverage={
                category: "部分覆盖" for category in REQUIRED_SEARCH_CATEGORIES
            },
            coverage_notes={
                category: "许可证据显示无法在计划范围内使用"
                for category in REQUIRED_SEARCH_CATEGORIES
            },
            covered_languages=["zh"],
            covered_platforms=[],
            independent_source_yield_history=[1.0],
            new_method_categories_history=[1],
            key_questions_covered=False,
            counterevidence_completed=False,
            citation_tracking_completed=False,
            uncovered_scope=["英文数据库", "后续方法搜索"],
            stop_type="可行性阻断",
            blocking_issue="数据许可证禁止计划用途",
            blocking_source_ids=["SRC-001"],
            stop_reason="已核验的许可证限制阻止该方向",
        )

        validator.validate_search_coverage(
            [coverage],
            {"DIR-001"},
            {"RQ-001"},
            {"QRY-001"},
            {"SRC-001"},
            True,
            True,
            set(),
        )

        self.assertEqual([], [item for item in validator.findings if item.severity == "ERROR"])

    def test_selected_direction_cannot_keep_feasibility_blocker(self) -> None:
        validator = WorkspaceValidator(self.root)
        coverage = self.valid_search_coverage(
            stop_type="可行性阻断",
            blocking_issue="缺少可用许可",
            blocking_source_ids=["SRC-001"],
            uncovered_scope=["因许可阻断未继续搜索"],
        )

        validator.validate_search_coverage(
            [coverage],
            {"DIR-001"},
            {"RQ-001"},
            {"QRY-001"},
            {"SRC-001"},
            True,
            True,
            {"DIR-001"},
        )

        self.assertIn("RESEARCH_SELECTED_DIRECTION_SEARCH_BLOCKED", self.codes(validator))

    def test_gate_check_activates_complete_contract_gate(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        self.write_research(template)
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract(
            "阶段一：调研与设计",
            "进行中",
            phase_one_state_override="GATE_CHECK",
            preflight_transition=True,
        )
        codes = self.codes(validator)
        self.assertIn("RESEARCH_CONFIRMATION_BLOCKING", codes)

    def test_secondary_source_must_trace_to_primary(self) -> None:
        validator = WorkspaceValidator(self.root)
        secondary = self.valid_source(
            source_id="SRC-002",
            provenance_level="二手来源",
            primary_source_id="SRC-999",
            quality_level=4,
            usage_role="检索线索",
        )

        validator.validate_source_evidence([secondary])

        self.assertIn(
            "RESEARCH_SECONDARY_SOURCE_PRIMARY_UNRESOLVED", self.codes(validator)
        )

    def test_reposts_cannot_be_counted_as_independent_evidence(self) -> None:
        validator = WorkspaceValidator(self.root)
        sources = [
            self.valid_source(source_id="SRC-001", independence_group="same-work"),
            self.valid_source(source_id="SRC-002", independence_group="same-work"),
        ]
        source_ids = validator.validate_source_evidence(sources)
        claim = self.valid_claim(source_ids=["SRC-001", "SRC-002"])

        validator.validate_claim_evidence(
            [claim], {"SRC-001", "SRC-002"}, {"RQ-001"}, True, sources
        )

        self.assertEqual({"SRC-001", "SRC-002"}, source_ids)
        self.assertIn(
            "RESEARCH_CLAIM_SOURCE_INDEPENDENCE_OVERSTATED",
            self.codes(validator),
        )

    def test_low_quality_leads_cannot_be_only_contract_support(self) -> None:
        validator = WorkspaceValidator(self.root)
        source = self.valid_source(
            quality_level=5,
            usage_role="检索线索",
        )
        validator.validate_source_evidence([source])

        validator.validate_claim_evidence(
            [self.valid_claim()], {"SRC-001"}, {"RQ-001"}, True, [source]
        )

        self.assertIn(
            "RESEARCH_CLAIM_SUPPORTED_ONLY_BY_LEADS", self.codes(validator)
        )

    def test_contract_claim_requires_citation_scope_and_causality_checks(self) -> None:
        validator = WorkspaceValidator(self.root)
        claim = self.valid_claim(
            citation_support_verified=False,
            numeric_details_verified=False,
            scope_match_verified=False,
            causality_checked=False,
        )

        validator.validate_claim_evidence(
            [claim], {"SRC-001"}, {"RQ-001"}, True
        )

        self.assertIn(
            "RESEARCH_CLAIM_CITATION_CHECK_INCOMPLETE", self.codes(validator)
        )

    def test_conflicting_claim_retains_reason_and_adverse_evidence(self) -> None:
        validator = WorkspaceValidator(self.root)
        claim = self.valid_claim(
            conflict_status="存在冲突",
            conflict_type="无",
            conflict_reason=None,
            adverse_evidence_retained=False,
            eligible_for_research_contract=False,
        )

        validator.validate_claim_evidence(
            [claim], {"SRC-001"}, {"RQ-001"}, False
        )

        codes = self.codes(validator)
        self.assertIn("RESEARCH_CLAIM_CONFLICT_DETAIL_MISSING", codes)
        self.assertIn("RESEARCH_CLAIM_ADVERSE_EVIDENCE_NOT_RETAINED", codes)

    def test_search_log_emits_rotation_warning_at_threshold(self) -> None:
        research = self.root / "research"
        research.mkdir()
        entries = [
            self.valid_search_entry(query_id="QRY-001"),
            self.valid_search_entry(query_id="QRY-002"),
        ]
        (research / "search_log.jsonl").write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
            encoding="utf-8",
        )
        validator = WorkspaceValidator(self.root)

        with mock.patch(
            "scripts.validate_workspace.SEARCH_LOG_LINE_WARNING", 2
        ):
            validator.validate_search_log(
                {"SRC-001"}, {"RQ-001"}, False, {"DIR-001"}
            )

        self.assertIn("RESEARCH_SEARCH_LOG_ROTATION_REQUIRED", self.codes(validator))

    def test_archived_and_active_search_ids_must_be_globally_unique(self) -> None:
        research = self.root / "research"
        archive = research / "archive"
        archive.mkdir(parents=True)
        entry = self.valid_search_entry(query_id="QRY-001")
        serialized = json.dumps(entry, ensure_ascii=False) + "\n"
        (research / "search_log.jsonl").write_text(serialized, encoding="utf-8")
        (archive / "search_log-QRY-001-QRY-001.jsonl").write_text(
            serialized, encoding="utf-8"
        )
        validator = WorkspaceValidator(self.root)

        validator.validate_search_log(
            {"SRC-001"}, {"RQ-001"}, False, {"DIR-001"}
        )

        self.assertIn("RESEARCH_QUERY_ID_DUPLICATE", self.codes(validator))

    def test_empty_evidence_and_absent_registries_are_valid_before_research(self) -> None:
        self.copy_empty_research_evidence()
        for directory in ("datasets", "models", "baselines", "experiments/scripts", "experiments/runs"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        validator = WorkspaceValidator(self.root)

        validator.check_phase_one_evidence("阶段一：调研与设计", "未开始")
        validator.check_registries()

        errors = [item for item in validator.findings if item.severity == "ERROR"]
        self.assertEqual([], errors)
        self.assertFalse(any(self.root.glob("*/registry.yaml")))

    def test_fulltext_and_sensitive_sample_fields_are_rejected(self) -> None:
        validator = WorkspaceValidator(self.root)

        validator.validate_evidence_minimal_disclosure(
            "research/sources.yaml",
            {"source_id": "SRC-001", "full_text": "synthetic restricted text"},
        )

        self.assertIn(
            "RESEARCH_EVIDENCE_FULLTEXT_FIELD_FORBIDDEN", self.codes(validator)
        )

    def test_oversized_source_summary_is_rejected(self) -> None:
        validator = WorkspaceValidator(self.root)

        validator.validate_evidence_minimal_disclosure(
            "research/sources.yaml",
            {"source_id": "SRC-001", "notes": "x" * 2_001},
        )

        self.assertIn(
            "RESEARCH_EVIDENCE_MINIMAL_DISCLOSURE_EXCEEDED",
            self.codes(validator),
        )

    def test_personal_data_in_search_log_is_rejected(self) -> None:
        validator = WorkspaceValidator(self.root)

        validator.validate_evidence_minimal_disclosure(
            "research/search_log.jsonl",
            {"query_id": "QRY-001", "query": "contact test-person@example.org"},
        )

        self.assertIn(
            "RESEARCH_EVIDENCE_PERSONAL_DATA_FORBIDDEN", self.codes(validator)
        )

    def test_external_transfer_requires_scoped_authorization(self) -> None:
        text = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8").replace(
            "- 外部传输：待设计；计划外发时创建限定范围的 `AUTH-<nnn>`。",
            "- 外部传输：允许发送公开合成摘要。",
        ).replace(
            "- 计算与外部服务：待设计；只登记实际使用的 GPU、API、模型和数据流。",
            "- 计算与外部服务：使用外部 API 分析公开合成摘要。",
        )
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract_quality(
            text, validator.parse_markdown_tables(text), False
        )

        self.assertIn(
            "RESEARCH_API_TRANSFER_AUTHORIZATION_MISSING", self.codes(validator)
        )

        authorized_text = text + """

## 补充授权记录

| 授权 ID | 授权事项 | 范围 | 用户确认日期或轮次 | 状态 | 关联决策 ID |
| --- | --- | --- | --- | --- | --- |
| AUTH-001 | 允许外部 API 传输 | 仅限公开合成摘要 | 2026-07-21 | 已确认 | DEC-001 |
"""
        authorized_validator = WorkspaceValidator(self.root)
        authorized_validator.check_research_contract_quality(
            authorized_text,
            authorized_validator.parse_markdown_tables(authorized_text),
            False,
        )
        self.assertNotIn(
            "RESEARCH_API_TRANSFER_AUTHORIZATION_MISSING",
            self.codes(authorized_validator),
        )

    def test_secret_scan_excludes_env_without_reading_it(self) -> None:
        env_path = self.root / ".env"
        safe_path = self.root / "safe.txt"
        env_path.write_text("SYNTHETIC_SECRET=do-not-read\n", encoding="utf-8")
        safe_path.write_text("safe content\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        validator = WorkspaceValidator(self.root)
        original_read_text = Path.read_text
        read_paths: list[Path] = []

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            read_paths.append(path)
            if path.name == ".env":
                raise AssertionError("validator attempted to read .env")
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", guarded_read_text):
            validator.check_suspected_secrets()

        self.assertNotIn(env_path, read_paths)
        self.assertIn("SECRET_FILE_VISIBLE", self.codes(validator))

    def test_repository_template_end_to_end_passes_without_registries(self) -> None:
        project_root = self.root / "synthetic-project"
        shutil.copytree(
            REPOSITORY_ROOT,
            project_root,
            ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"),
        )
        self.initialize_git_repository(project_root)

        validator = WorkspaceValidator(project_root)
        findings = validator.validate()

        blocking = [item for item in findings if item.severity in {"ERROR", "WARN"}]
        self.assertEqual([], blocking)
        self.assertFalse(any(project_root.glob("*/registry.yaml")))
        self.assertFalse(
            any(path.is_dir() for path in (project_root / "experiments/runs").iterdir())
        )

    def test_task_progress_lifecycle_is_observable_and_valid(self) -> None:
        (self.root / "experiments").mkdir()
        (self.root / "paper").mkdir()
        experiment_todo = self.root / "experiments/TODO.md"
        paper_todo = self.root / "paper/TODO.md"
        experiment_todo.write_text("experiment sentinel\n", encoding="utf-8")
        paper_todo.write_text("paper sentinel\n", encoding="utf-8")
        task_dir = self.root / "workflow/tasks/task-run-001"
        progress = TaskProgress(task_dir)

        progress.start(
            task_run_id="task-run-001",
            stage="stage_two",
            task_kind="training",
            label="synthetic seed 1337",
            step="queued",
            total=2,
            unit="epoch",
        )
        progress.update(
            status_name="running",
            step="epoch 1",
            completed=1,
            message="first epoch complete",
            resource_updates={"gpu_seconds": 10.0},
        )
        progress.update(
            status_name="success",
            step="evaluation complete",
            completed=2,
            message="task complete",
            outputs=["experiments/runs/run-synthetic"],
        )
        validator = WorkspaceValidator(self.root)

        validator.check_task_progress()

        self.assertEqual([], validator.findings)
        self.assertEqual(3, len((task_dir / "events.jsonl").read_text().splitlines()))
        self.assertEqual("experiment sentinel\n", experiment_todo.read_text(encoding="utf-8"))
        self.assertEqual("paper sentinel\n", paper_todo.read_text(encoding="utf-8"))

    def test_stale_running_task_heartbeat_is_reported(self) -> None:
        task_dir = self.root / "paper/sessions/write-001"
        progress = TaskProgress(task_dir)
        progress.start(
            task_run_id="write-001",
            stage="stage_three",
            task_kind="drafting",
            label="methods section",
            step="outline",
        )
        progress.update(status_name="running", step="drafting")
        heartbeat = json.loads((task_dir / "heartbeat.json").read_text())
        heartbeat["heartbeat_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=3)
        ).isoformat()
        (task_dir / "heartbeat.json").write_text(json.dumps(heartbeat), encoding="utf-8")
        validator = WorkspaceValidator(self.root)

        validator.check_task_progress()

        self.assertIn("TASK_HEARTBEAT_STALE", self.codes(validator))

    def test_stage_three_requires_stage_two_evidence_handoff(self) -> None:
        validator = WorkspaceValidator(self.root)

        validator.check_stage_two_handoff(required=True)

        self.assertIn("STAGE_TWO_HANDOFF_MISSING", self.codes(validator))

    def test_machine_state_rejects_manual_markdown_advance(self) -> None:
        shutil.copytree(REPOSITORY_ROOT / "workflow", self.root / "workflow")
        research = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        self.write_research(
            research.replace("阶段一子状态：INTAKE", "阶段一子状态：DIVERGE")
        )
        validator = WorkspaceValidator(self.root)

        validator.check_machine_workflow_state()

        self.assertIn("WORKFLOW_STATE_PROJECTION_MISMATCH", self.codes(validator))

    def test_valid_stage_two_handoff_resolves_local_success_run(self) -> None:
        run_dir = self.root / "experiments/runs/run-001"
        run_dir.mkdir(parents=True)
        (run_dir / "metadata.json").write_text(
            json.dumps({"experiment_id": "exp-001", "status": "success"}),
            encoding="utf-8",
        )
        (self.root / "experiments/evidence_handoff.yaml").write_text(
            """schema_version: 1
handoffs:
  - handoff_id: "HANDOFF-001"
    research_question_ids: ["RQ-001"]
    success_criterion_ids: ["SC-001"]
    experiment_ids: ["exp-001"]
    run_ids: ["run-001"]
    supported_claims: ["The synthetic run completed."]
    unsupported_claims: []
    negative_results: []
    limitations: ["Synthetic fixture only."]
    local_evidence_verified: true
    registry_reconciled: true
    completed_at: "2026-07-23T00:00:00+00:00"
""",
            encoding="utf-8",
        )
        validator = WorkspaceValidator(self.root)

        validator.check_stage_two_handoff(required=True)

        self.assertEqual([], validator.findings)

    def test_success_run_requires_reproducibility_metadata(self) -> None:
        run_dir = self.root / "experiments/runs/run-001"
        run_dir.mkdir(parents=True)
        for filename in (
            "command.txt",
            "environment.json",
            "script_path.txt",
            "run.log",
            "events.jsonl",
        ):
            (run_dir / filename).write_text("synthetic\n", encoding="utf-8")
        for filename in ("config_snapshot.json", "metrics.json", "status.json", "heartbeat.json"):
            (run_dir / filename).write_text("{}\n", encoding="utf-8")
        (run_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "experiment_id": "exp-001",
                    "status": "success",
                    "resources": {
                        "gpu": {"enabled": False},
                        "api": {"enabled": False},
                    },
                }
            ),
            encoding="utf-8",
        )
        validator = WorkspaceValidator(self.root)

        validator.check_run_records()

        codes = self.codes(validator)
        self.assertIn("RUN_DATA_VERSION_MISSING", codes)
        self.assertIn("RUN_RANDOM_SEED_MISSING", codes)

    def test_experiment_registry_and_local_runs_are_reconciled(self) -> None:
        run_dir = self.root / "experiments/runs/run-001"
        run_dir.mkdir(parents=True)
        (run_dir / "metadata.json").write_text(
            json.dumps({"experiment_id": "exp-001", "status": "success"}),
            encoding="utf-8",
        )
        (self.root / "experiments/registry.yaml").write_text(
            """schema_version: 1
experiments:
  - experiment_id: "exp-001"
    status: "completed"
    script: "experiments/scripts/exp-001-synthetic.py"
    runs: ["run-001"]
    research_question_ids: ["RQ-001"]
    success_criterion_ids: ["SC-001"]
    decision_ids: ["DEC-001"]
""",
            encoding="utf-8",
        )
        validator = WorkspaceValidator(self.root)

        validator.check_experiment_reconciliation()

        self.assertEqual([], validator.findings)

    def test_unregistered_local_run_is_rejected(self) -> None:
        run_dir = self.root / "experiments/runs/run-001"
        run_dir.mkdir(parents=True)
        (run_dir / "metadata.json").write_text(
            json.dumps({"experiment_id": "exp-001", "status": "failed"}),
            encoding="utf-8",
        )
        (self.root / "experiments/registry.yaml").write_text(
            """schema_version: 1
experiments:
  - experiment_id: "exp-001"
    status: "planned"
    script: "experiments/scripts/exp-001-synthetic.py"
    runs: []
    research_question_ids: ["RQ-001"]
    success_criterion_ids: ["SC-001"]
    decision_ids: ["DEC-001"]
""",
            encoding="utf-8",
        )
        validator = WorkspaceValidator(self.root)

        validator.check_experiment_reconciliation()

        self.assertIn("EXPERIMENT_RUN_UNREGISTERED", self.codes(validator))

    def copy_empty_research_evidence(self) -> None:
        """Copy only the committed empty evidence schema into the test workspace."""

        target = self.root / "research"
        target.mkdir(parents=True, exist_ok=True)
        for name in (
            "search_log.jsonl",
            "search_coverage.yaml",
            "sources.yaml",
            "claims.yaml",
            "decisions.yaml",
        ):
            shutil.copyfile(REPOSITORY_ROOT / "research" / name, target / name)

    @staticmethod
    def initialize_git_repository(project_root: Path) -> None:
        """Create a local Git baseline so immutability checks are meaningful."""

        environment = os.environ.copy()
        environment.update(
            {
                "GIT_AUTHOR_NAME": "Codex Test",
                "GIT_AUTHOR_EMAIL": "codex-test@example.invalid",
                "GIT_COMMITTER_NAME": "Codex Test",
                "GIT_COMMITTER_EMAIL": "codex-test@example.invalid",
            }
        )
        subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
        subprocess.run(["git", "add", "."], cwd=project_root, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "test: synthetic baseline"],
            cwd=project_root,
            check=True,
            env=environment,
        )

    @staticmethod
    def valid_search_entry(**overrides: object) -> dict[str, object]:
        """Create one schema-valid search-log entry."""

        entry: dict[str, object] = {
            "query_id": "QRY-001",
            "direction_ids": ["DIR-001"],
            "research_question_ids": ["RQ-001"],
            "search_categories": ["背景"],
            "query": "synthetic background query",
            "language": "en",
            "keyword_variants": ["background"],
            "platform": "local fixture",
            "searched_at": "2026-07-22T10:00:00+08:00",
            "filters": {},
            "result_count": 1,
            "included_source_ids": ["SRC-001"],
            "exclusions": [],
            "counterevidence_search": False,
            "citation_tracking": False,
        }
        entry.update(overrides)
        return entry

    @staticmethod
    def valid_search_coverage(**overrides: object) -> dict[str, object]:
        """Create one schema-valid stopped direction-coverage entry."""

        entry: dict[str, object] = {
            "direction_id": "DIR-001",
            "research_question_ids": ["RQ-001"],
            "query_ids": ["QRY-001"],
            "coverage": {
                category: "已覆盖" for category in REQUIRED_SEARCH_CATEGORIES
            },
            "coverage_notes": {},
            "chinese_keywords": ["背景", "失败"],
            "english_keywords": ["background", "failure"],
            "citation_tracking_source_ids": ["SRC-001"],
            "planned_languages": ["zh", "en"],
            "covered_languages": ["zh", "en"],
            "planned_platforms": ["local fixture"],
            "covered_platforms": ["local fixture"],
            "planned_date_range": "2020-2026",
            "covered_date_range": "2020-2026",
            "independent_source_yield_history": [1.0, 0.0],
            "new_method_categories_history": [1, 0],
            "key_questions_covered": True,
            "counterevidence_completed": True,
            "citation_tracking_completed": True,
            "uncovered_scope": [],
            "stop_type": "证据饱和",
            "blocking_issue": None,
            "blocking_source_ids": [],
            "stop_reason": "independent-source yield declined and no new method category appeared",
            "stop_status": "已停止",
            "last_updated_at": "2026-07-22T10:10:00+08:00",
        }
        entry.update(overrides)
        return entry

    @staticmethod
    def valid_source(**overrides: object) -> dict[str, object]:
        """Create one schema-valid high-quality source entry."""

        source: dict[str, object] = {
            "source_id": "SRC-001",
            "title": "Synthetic primary source",
            "creators": ["Test institution"],
            "url": None,
            "doi_or_identifier": "urn:test:source-001",
            "published_at": "2026-07-22",
            "accessed_at": "2026-07-22",
            "source_type": "测试规范",
            "quality_level": 1,
            "provenance_level": "原始来源",
            "primary_source_id": None,
            "independence_group": "source-001",
            "usage_role": "关键证据",
            "version": "1",
            "license": "CC0-1.0",
            "data_classification": "公开",
            "contains_restricted_content": False,
            "external_transfer_allowed": False,
            "accessibility_status": "可访问",
            "locator_exists": True,
            "locator_verified_at": "2026-07-22",
            "locator_verification_method": "官方登记",
            "update_retraction_conflict_status": "无已知问题",
            "notes": None,
        }
        source.update(overrides)
        if "source_id" in overrides and "doi_or_identifier" not in overrides:
            source["doi_or_identifier"] = f"urn:test:{source['source_id']}"
        return source

    @staticmethod
    def valid_claim(**overrides: object) -> dict[str, object]:
        """Create one schema-valid claim entry."""

        claim: dict[str, object] = {
            "claim_id": "CLM-001",
            "claim": "A minimal verifiable claim.",
            "research_question_ids": ["RQ-001"],
            "source_ids": ["SRC-001"],
            "evidence_locations": ["section 1"],
            "support_level": "直接支持",
            "source_independence": "独立",
            "temporal_status": "当前有效",
            "conflict_status": "无已知冲突",
            "verification_status": "已核验",
            "citation_support_verified": True,
            "numeric_details_verified": True,
            "scope_match_verified": True,
            "causality_checked": True,
            "model_inference_status": "非模型推论",
            "conflict_type": "无",
            "conflict_reason": None,
            "uncertainty_notes": None,
            "adverse_evidence_retained": True,
            "verification_notes": "Checked against the synthetic fixture.",
            "eligible_for_research_contract": True,
        }
        claim.update(overrides)
        return claim

    @staticmethod
    def valid_decision(**overrides: object) -> dict[str, object]:
        """Create one schema-valid decision entry."""

        decision: dict[str, object] = {
            "decision_id": "DEC-001",
            "decision": "Adopt the current research direction.",
            "user_input_source": "turn 2",
            "supporting_claim_ids": ["CLM-001"],
            "alternatives": [],
            "rejection_reasons": [],
            "user_confirmation_status": "已确认",
            "affected_contract_fields": ["研究目标"],
            "triggers_phase_rollback": False,
            "decided_at": "2026-07-21",
        }
        decision.update(overrides)
        return decision

    @staticmethod
    def contract_table(status: str, value: str) -> str:
        """Create a compact field-status table for a targeted test."""

        fields = (
            "最终研究方向",
            "数据、baseline、指标与成功标准",
            "阶段二实验与执行方案",
            "数据、许可与隐私边界",
            "范围边界",
        )
        rows = [
            "| 合同字段 | 当前值或引用 | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        rows.extend(
            f"| {field} | {value} | 用户 | {status} | 2026-07-21 | DEC-001 | 不适用 |"
            for field in fields
        )
        return "\n".join(rows)


if __name__ == "__main__":
    unittest.main()
