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
        intake_values = {
            "用户研究意图": "探索一个可复现的合成研究方向",
        }
        for index, (field, value) in enumerate(intake_values.items(), start=1):
            old = f"| {index} | {field} | TODO | TODO | 待澄清 | TODO | 待分配 |"
            new = f"| {index} | {field} | {value} | 用户 | 暂定 | 轮次 1 | 待分配 |"
            partial = partial.replace(old, new)
        partial = partial.replace(
            "| 待分配 | TODO | TODO | TODO | TODO | TODO | 待分配 |",
            "| TRANS-001 | 2026-07-22 | INTAKE | DIVERGE | 已通过 | 用户提供研究种子 | DEC-001 |",
        )
        self.write_research(partial)
        self.copy_empty_research_evidence()
        validator = WorkspaceValidator(self.root)

        phase, status = validator.check_stage_state()
        validator.check_research_contract(phase, status)
        validator.check_phase_one_evidence(phase, status)

        errors = [item for item in validator.findings if item.severity == "ERROR"]
        self.assertEqual([], errors)

    def test_broad_direction_cannot_be_promoted_directly_to_draft(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        broad_draft = template.replace("阶段一子状态：INTAKE", "阶段一子状态：DRAFT")
        self.write_research(broad_draft)
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract("阶段一：调研与设计", "进行中")

        codes = self.codes(validator)
        self.assertIn("RESEARCH_INTAKE_INCOMPLETE_FOR_DRAFT", codes)
        self.assertIn("RESEARCH_DIRECTION_CANDIDATES_INSUFFICIENT", codes)

    def test_search_requires_two_compared_candidate_directions(self) -> None:
        text = self.synthetic_completed_research()
        validator = WorkspaceValidator(self.root)
        candidate_tables = [
            (headers, rows[:1])
            for headers, rows in validator.parse_markdown_tables(text)
            if "候选方向 ID" in headers
        ]

        validator.check_candidate_directions(
            candidate_tables,
            "SEARCH",
            False,
            {"研究问题 ID": {"RQ-001"}},
        )

        self.assertIn(
            "RESEARCH_DIRECTION_CANDIDATES_INSUFFICIENT", self.codes(validator)
        )

    def test_search_allows_data_and_resource_intake_to_remain_pending(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        for index, field in enumerate(
            ("用户研究意图", "研究对象", "核心问题", "预期贡献"), start=1
        ):
            template = template.replace(
                f"| {index} | {field} | TODO | TODO | 待澄清 | TODO | 待分配 |",
                f"| {index} | {field} | 可工作的方向信息 | 用户 | 暂定 | 轮次 1 | 待分配 |",
            )
        validator = WorkspaceValidator(self.root)
        validator.check_requirement_intake(
            validator.parse_markdown_tables(template), "SEARCH", False
        )

        self.assertNotIn(
            "RESEARCH_INTAKE_INCOMPLETE_FOR_SEARCH", self.codes(validator)
        )

    def test_search_requires_brainstorm_record_and_user_exit(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        validator = WorkspaceValidator(self.root)
        tables = validator.parse_markdown_tables(template)

        validator.check_brainstorm(tables, template, "SEARCH", False)

        codes = self.codes(validator)
        self.assertIn("RESEARCH_BRAINSTORM_RECORD_MISSING", codes)
        self.assertIn("RESEARCH_BRAINSTORM_USER_EXIT_MISSING", codes)

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
        text = self.synthetic_completed_research().replace(
            "| 不适用 | 已否决 | 引入不必要的外发、费用和不可控版本风险 |",
            "| RQ-001 | 已选定 | 引入不必要的外发、费用和不可控版本风险 |",
        )
        validator = WorkspaceValidator(self.root)

        validator.check_candidate_directions(
            validator.parse_markdown_tables(text),
            "GATE_CHECK",
            True,
            {"研究问题 ID": {"RQ-001"}},
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

    def test_resource_quota_is_ignored_but_unexplained_null_is_rejected(self) -> None:
        validator = WorkspaceValidator(self.root)
        resource = self.valid_resource(
            max_search_queries=2,
            search_queries=3,
            input_tokens=None,
            unavailable_metrics=[],
        )

        validator.validate_phase_one_resources([resource], [], [], True)

        codes = self.codes(validator)
        self.assertNotIn("RESEARCH_RESOURCE_BUDGET_EXCEEDED", codes)
        self.assertIn("RESEARCH_RESOURCE_NULL_REASON_MISSING", codes)

    def test_summary_size_is_not_a_phase_one_quota(self) -> None:
        summaries = self.root / "research/summaries"
        summaries.mkdir(parents=True)
        (summaries / "RQ-001.md").write_text("123456", encoding="utf-8")
        validator = WorkspaceValidator(self.root)

        validator.validate_phase_one_resources(
            [self.valid_resource(max_summary_chars=5)], [], [], True
        )

        self.assertNotIn("RESEARCH_SUMMARY_SIZE_EXCEEDED", self.codes(validator))

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
        text = self.synthetic_completed_research().replace(
            "- 外部模型 API：不适用：合成演练只使用本地 CPU。",
            "- 外部模型 API：OpenAI-compatible 测试接口。",
        ).replace(
            "- API 用途：不适用：不调用外部服务。",
            "- API 用途：分析公开合成摘要。",
        ).replace(
            "- API 模型：不适用：不调用外部服务。",
            "- API 模型：synthetic-model。",
        ).replace(
            "- API 与 GPU 分工及数据流：不适用：数据保持本地。",
            "- API 与 GPU 分工及数据流：将公开合成摘要发送到外部 API 并接收分类结果。",
        ).replace(
            "- 外部 API 传输：不允许：合成演练保持本地。",
            "- 外部 API 传输：允许发送公开合成摘要。",
        )
        validator = WorkspaceValidator(self.root)

        validator.check_research_contract_quality(
            text, validator.parse_markdown_tables(text), False
        )

        self.assertIn(
            "RESEARCH_API_TRANSFER_AUTHORIZATION_MISSING", self.codes(validator)
        )

        authorized_text = text + """

## 授权记录

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

    def test_synthetic_phase_one_end_to_end_passes_without_registries(self) -> None:
        project_root = self.root / "synthetic-project"
        shutil.copytree(
            REPOSITORY_ROOT,
            project_root,
            ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"),
        )
        (project_root / "RESEARCH.md").write_text(
            self.synthetic_completed_research(), encoding="utf-8"
        )
        (project_root / "experiments/TODO.md").write_text(
            self.synthetic_experiment_todo(), encoding="utf-8"
        )
        self.write_synthetic_workflow_state(project_root)
        self.write_synthetic_evidence(project_root)
        self.initialize_git_repository(project_root)

        validator = WorkspaceValidator(project_root)
        findings = validator.validate()

        blocking = [
            item for item in findings if item.severity in {"ERROR", "WARN"}
        ]
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

    @staticmethod
    def write_synthetic_workflow_state(project_root: Path) -> None:
        """Synchronize machine state with the completed synthetic contract."""

        nodes = ("INTAKE", "DIVERGE", "SEARCH", "COMPARE", "DRAFT", "CONFIRM", "GATE_CHECK")
        events = []
        for revision, (source, target) in enumerate(zip(nodes, nodes[1:]), start=1):
            events.append(
                {
                    "schema_version": 1,
                    "transition_id": f"TRANS-{revision:03d}",
                    "revision": revision,
                    "from_node": source,
                    "to_node": target,
                }
            )
        workflow = project_root / "workflow"
        (workflow / "state.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "revision": 6,
                    "current_phase": "阶段一：调研与设计",
                    "phase_one_substate": "GATE_CHECK",
                    "phase_status": "已完成",
                    "gate_result": "已通过",
                    "last_transition_id": "TRANS-006",
                    "updated_at": "2026-07-21T00:00:00+00:00",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (workflow / "transitions.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )

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
            "resources.yaml",
        ):
            shutil.copyfile(REPOSITORY_ROOT / "research" / name, target / name)

    @staticmethod
    def synthetic_completed_research() -> str:
        """Return a compact, fictional, non-sensitive completed phase-one contract."""

        contract_fields = (
            ("研究目标", "研究公开合成短文本的规则分类稳定性"),
            ("研究问题", "RQ-001"),
            ("成功标准", "SC-001"),
            ("数据、baseline 与评测", "DATA-001 / BASE-001 / METRIC-001"),
            ("数据与隐私边界", "仅使用公开合成文本，不含个人信息且禁止外发"),
            ("计算与外部服务", "仅使用本地 CPU"),
            ("阶段二执行约束与资源方案", "零 API 调用、零 GPU 时间"),
            ("Skills、依赖与授权", "不适用：使用 Python 标准库且无外部服务"),
            ("范围外事项", "不训练模型、不处理真实用户数据、不撰写论文"),
        )
        contract_rows = "\n".join(
            f"| {field} | {value} | 用户确认与 CLM-001 | 已确认 | 2026-07-21 / 演练轮次 6 | DEC-001 | CLM-001 |"
            for field, value in contract_fields
        )
        return f"""# 合成阶段一研究合同

本文件仅用于运行时端到端测试，内容均为虚构、公开且非敏感的合成研究方向。

## 当前工作流状态

- 当前阶段：阶段一：调研与设计。
- 阶段一子状态：GATE_CHECK。
- 阶段状态：已完成。
- 阶段门禁：已通过。
- 停止原因：不适用。
- 恢复条件：不适用。
- 最近确认日期：2026-07-21。

## 会话恢复摘要

- 最近交接日期或轮次：2026-07-21 / 演练轮次 7。
- 当前全局阶段：阶段一：调研与设计。
- 当前阶段一子状态：GATE_CHECK。
- 当前候选方向：DIR-001、DIR-002。
- 当前唯一选定方向：DIR-001。
- 头脑风暴状态：已结束。
- 最新趋同判断：趋同；新回答未形成新的实质方向。
- 用户是否还有更多想法：暂无；进入搜索。
- 本轮已确认事项：DEC-001，确认 RQ-001、DATA-001、BASE-001、METRIC-001 与 SC-001。
- 本轮否决方案：拒绝使用真实个人数据和外部模型 API。
- 当前暂定假设：无；合同字段均已明确确认。
- 新增证据：SRC-001、CLM-001、DEC-001。
- 未解决问题：无；本轮未保留开放问题。
- 下一轮首要任务：执行 experiments/TODO.md 中的 exp-001，但本演练不实际运行实验。
- 不应重新采用的旧方案：真实用户数据、外部 API 和模型训练。

## 阶段一：调研与设计进度

### 需求获取清单

| 顺序 | 需求字段 | 当前摘要或引用 | 信息来源 | 获取状态 | 最近澄清日期或轮次 | 未决问题 ID |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 用户研究意图 | 演练自动化分阶段科研工作流 | 用户 | 已澄清 | 2026-07-21 / 轮次 1 | 不适用 |
| 2 | 研究对象 | 公开合成短文本规则分类器 | 用户 | 已澄清 | 2026-07-21 / 轮次 1 | 不适用 |
| 3 | 核心问题 | 规则对文本扰动的分类稳定性 | 用户与 Codex | 已澄清 | 2026-07-21 / 轮次 2 | 不适用 |
| 4 | 预期贡献 | 可复现的稳定性测量流程 | 用户 | 已澄清 | 2026-07-21 / 轮次 2 | 不适用 |
| 5 | 成功标准 | SC-001 | 用户 | 已澄清 | 2026-07-21 / 轮次 3 | 不适用 |
| 6 | 数据条件 | DATA-001，仅使用运行时合成文本 | 用户 | 已澄清 | 2026-07-21 / 轮次 3 | 不适用 |
| 7 | baseline | BASE-001，固定关键词精确匹配 | 用户与 Codex | 已澄清 | 2026-07-21 / 轮次 4 | 不适用 |
| 8 | 指标 | METRIC-001，一致率及 bootstrap 区间 | 用户 | 已澄清 | 2026-07-21 / 轮次 4 | 不适用 |
| 9 | API/GPU | 不使用 API 或 GPU | 用户 | 已澄清 | 2026-07-21 / 轮次 5 | 不适用 |
| 10 | 数据许可和隐私 | CC0 合成夹具，不含个人信息且不外发 | 用户 | 已澄清 | 2026-07-21 / 轮次 5 | 不适用 |
| 11 | 范围外事项 | 真实数据、训练、论文与专利 | 用户 | 已澄清 | 2026-07-21 / 轮次 5 | 不适用 |

### 头脑风暴记录

| 轮次 | Codex 主动问题焦点 | 用户回答摘要 | 新增差异维度 | 关联候选方向 | 趋同判断 |
| --- | --- | --- | --- | --- | --- |
| 1 | 更重视透明规则还是外部模型能力 | 用户优先透明且本地的规则评测 | 方法机制、验证方式 | DIR-001、DIR-002 | 有新差异 |
| 2 | 是否还有不同的研究对象或贡献形式 | 暂时没有，已有方向足够比较 | 无 | DIR-001、DIR-002 | 趋同 |

- 发散结论：用户表示暂时没有更多想法，进入 SEARCH。

### 候选方向比较

| 候选方向 ID | 核心问题 | 研究价值 | 创新性风险 | 数据需求 | 计算成本 | 验证难度 | 预计交付物 | 关联研究问题 ID | 状态 | 选择或否决理由 | 决策 ID |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DIR-001 | 固定规则对合成文本扰动是否稳定 | 提供透明且可复现的工作流演练 | 创新性有限但适合验证模板 | 100 条运行时合成文本 | 本地 CPU，成本低 | 可用确定性脚本直接验证 | 脚本计划、指标和运行记录 | RQ-001 | 已选定 | 无外发和隐私风险，能够完整验证证据链 | DEC-001 |
| DIR-002 | 外部模型对合成文本扰动是否稳定 | 可比较模型语义鲁棒性 | 容易与既有模型评测重复 | 合成文本及外部模型响应 | 产生 API 调用费用 | 受模型版本和服务波动影响 | API 评测报告 | 不适用 | 已否决 | 引入不必要的外发、费用和不可控版本风险 | DEC-001 |

## 研究合同字段状态

| 合同字段 | 当前值或引用 | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |
| --- | --- | --- | --- | --- | --- | --- |
{contract_rows}

## 研究目标

| 当前值 | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |
| --- | --- | --- | --- | --- | --- |
| 研究公开合成短文本的规则分类稳定性 | 用户确认与 CLM-001 | 已确认 | 2026-07-21 | DEC-001 | CLM-001 |

## 研究问题

| 研究问题 ID | 当前值 | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |
| --- | --- | --- | --- | --- | --- | --- |
| RQ-001 | 固定关键词规则在公开合成扰动文本上的分类一致率是多少 | 用户确认 | 已确认 | 2026-07-21 | DEC-001 | CLM-001 |

## 预期贡献

| 贡献 ID | 当前值 | 比较 baseline ID | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CONTRIB-001 | 提供可复现的合成文本稳定性测量 | BASE-001 | 用户确认 | 已确认 | 2026-07-21 | DEC-001 | CLM-001 |

## 成功标准

| 成功标准 ID | 当前值 | 关联研究问题 ID | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SC-001 | 在固定的 100 条合成样本上报告一致率、95% bootstrap 区间及全部失败样本数量 | RQ-001 | 用户确认 | 已确认 | 2026-07-21 | DEC-001 | CLM-001 |

- 必须完成的消融：比较区分大小写与不区分大小写两种规则。
- 必须完成的稳健性验证：对空格和标点扰动分别报告一致率。
- 负面结果的有效完成条件：按预定口径完成评测并保留失败样本的脱敏编号。

## 数据集、baseline 与评测

### 数据集

| 数据 ID | 当前值 | 来源、版本与许可证 | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DATA-001 | 运行时生成的 100 条虚构短文本 | SRC-001；版本 1；CC0 合成夹具 | 用户确认 | 已确认 | 2026-07-21 | DEC-001 | CLM-001 |

### Baseline

| baseline ID | 当前值 | 上游版本或 revision | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BASE-001 | 固定关键词精确匹配规则 | 本地规范版本 1 | 用户确认 | 已确认 | 2026-07-21 | DEC-001 | CLM-001 |

### 评测指标

| 指标 ID | 当前值与统计口径 | 所需数据 ID | 信息来源 | 确认状态 | 最近确认日期或轮次 | 决策 ID | 证据 ID |
| --- | --- | --- | --- | --- | --- | --- | --- |
| METRIC-001 | 分类一致率和 95% bootstrap 区间，固定种子 1337 | DATA-001 | 用户确认 | 已确认 | 2026-07-21 | DEC-001 | CLM-001 |

## 研究合同一致性关系

| 研究问题 ID | 数据 ID | baseline ID | 指标 ID | 成功标准 ID | 阶段二实验 ID | 关系状态 |
| --- | --- | --- | --- | --- | --- | --- |
| RQ-001 | DATA-001 | BASE-001 | METRIC-001 | SC-001 | exp-001 | 已确认 |

## 数据与隐私边界

- 数据分类：公开合成数据。
- 个人信息：不包含；生成规则禁止姓名、联系方式和真实标识。
- 内部或受限数据：不使用。
- 外部 API 传输：不允许：合成演练保持本地。
- 允许外发范围：不适用：没有外部服务调用。
- 日志与产物脱敏：只记录合成样本编号，不记录完整失败文本。
- 数据保留与删除：测试临时目录在测试结束后删除。
- 论文、图表与公开限制：不适用：本演练不生成论文或对外产物。

## 计算与外部服务

- 本地计算资源：普通 CPU 与 Python 标准库。
- GPU 用途：不适用：规则分类不需要 GPU。
- 外部模型 API：不适用：合成演练只使用本地 CPU。
- API 用途：不适用：不调用外部服务。
- API 模型：不适用：不调用外部服务。
- API 与 GPU 分工及数据流：不适用：数据保持本地。

## 阶段二执行约束与资源方案

- 最大 GPU 时间：不适用：不使用 GPU。
- 最大 API 调用次数：0 次。
- 最大外部 API 预算：0 元。
- 阶段二失败停止规则：任何预检失败均停止，不生成运行证据。

### 阶段一资源记录说明

阶段一只记录实际用量，不设置查询、页面、调用、费用、时间或存储上限。

## Skills 与辅助工具

- 计划使用的 Skills：不适用：合成演练使用标准库。
- Skill 用途与阶段：不适用：不调用 Skill。
- 外部传输、依赖、费用与内容保存授权：不适用：无外发、依赖或费用。
- Skill 产生内容的核验与归档位置：不适用：无 Skill 产物。

## 范围外事项

- 模型训练、真实个人数据、外部服务调用、论文与专利均不在范围内。

## 调研证据摘要

| 主张 ID | 摘要 | 来源 ID | 支持的合同字段或研究问题 ID | 核验状态 |
| --- | --- | --- | --- | --- |
| CLM-001 | 合成夹具规范定义了固定数据生成和评测边界 | SRC-001 | RQ-001、DATA-001、SC-001 | 已核验 |

| 来源 ID | 最小引用信息或 URL | 核验日期 | 状态 |
| --- | --- | --- | --- |
| SRC-001 | 合成测试夹具规范，https://example.invalid/synthetic-fixture-v1 | 2026-07-21 | 已核验 |

## 当前决策

| 决策 ID | 日期 | 决策 | 理由摘要 | 影响字段 | 用户确认状态 | 证据 ID |
| --- | --- | --- | --- | --- | --- | --- |
| DEC-001 | 2026-07-21 | 采用本地、公开、合成的规则分类稳定性方向 | 可完整演练证据链且无隐私、费用和外发风险 | 研究合同全部字段 | 已确认 | CLM-001 |

## 阶段切换记录

| 切换 ID | 日期 | 原阶段 | 新阶段 | 门禁结果 | 原因或授权 | 决策 ID |
| --- | --- | --- | --- | --- | --- | --- |
| TRANS-001 | 2026-07-21 | INTAKE | DIVERGE | 已通过 | 用户提供研究种子 | DEC-001 |
| TRANS-002 | 2026-07-21 | DIVERGE | SEARCH | 已通过 | 用户结束发散并保留两个候选 | DEC-001 |
| TRANS-003 | 2026-07-21 | SEARCH | COMPARE | 已通过 | 八类覆盖与停止代理满足 | DEC-001 |
| TRANS-004 | 2026-07-21 | COMPARE | DRAFT | 已通过 | 用户选择唯一方向 | DEC-001 |
| TRANS-005 | 2026-07-21 | DRAFT | CONFIRM | 已通过 | 合同草案完整 | DEC-001 |
| TRANS-006 | 2026-07-21 | CONFIRM | GATE_CHECK | 已通过 | 字段逐项确认完成 | DEC-001 |
"""

    @staticmethod
    def synthetic_experiment_todo() -> str:
        """Return an executable-looking plan without creating or running an experiment."""

        return """# 合成实验任务

本文件仅用于端到端门禁测试，不表示已经执行实验。

## 当前目标

- 目标：实现并运行固定关键词分类稳定性评测。
- 验证标准：满足 SC-001 的预定报告口径。
- 资源上限：零 API 调用和零 GPU 时间。

## 进行中

| 任务 ID | 实验 ID | 研究问题 ID | 成功标准 ID | 任务 | 状态 | 完成条件 | 证据位置 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXP-TASK-001 | exp-001 | RQ-001 | SC-001 | 编写独立脚本并运行合成稳定性评测 | 未开始 | 输出一致率、区间、消融和稳健性结果 | 尚未产生运行证据 |

## 下一步

| 优先级 | 实验 ID | 研究问题 ID | 成功标准 ID | 任务 | 前置条件 | 完成条件 |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | exp-001 | RQ-001 | SC-001 | 创建脚本和新的运行目录 | 阶段二进入门禁通过 | 生成不可变运行记录 |

## 阻塞项

| 实验 ID | 原因 | 所需处理 | 恢复条件 |
| --- | --- | --- | --- |
| 不适用 | 无 | 无 | 无 |

## 已完成摘要

尚无已执行实验或结果。
"""

    @staticmethod
    def write_synthetic_evidence(project_root: Path) -> None:
        """Write runtime-only fictional query, source, claim, and decision evidence."""

        search_entries = [
            {
                "query_id": "QRY-001",
                "direction_ids": ["DIR-001"],
                "research_question_ids": ["RQ-001"],
                "search_categories": sorted(REQUIRED_SEARCH_CATEGORIES),
                "query": "合成关键词分类器 稳定性 baseline 失败 数据 指标 许可 相似工作",
                "language": "zh",
                "keyword_variants": ["规则分类", "扰动稳定性", "负面结果"],
                "platform": "local synthetic fixture catalog",
                "searched_at": "2026-07-22T10:00:00+08:00",
                "filters": {"date": "2026-07-22"},
                "result_count": 1,
                "included_source_ids": ["SRC-001"],
                "exclusions": [],
                "counterevidence_search": True,
                "citation_tracking": True,
                "returned_content_size": 180,
                "returned_content_unit": "characters",
                "page_count": 1,
                "external_tool_calls": 0,
            },
            {
                "query_id": "QRY-002",
                "direction_ids": ["DIR-002"],
                "research_question_ids": [],
                "search_categories": sorted(REQUIRED_SEARCH_CATEGORIES),
                "query": "synthetic external model robustness baseline failures datasets metrics licensing related work",
                "language": "en",
                "keyword_variants": ["model robustness", "negative results", "related work"],
                "platform": "local synthetic fixture catalog",
                "searched_at": "2026-07-22T10:05:00+08:00",
                "filters": {"date": "2026-07-22"},
                "result_count": 1,
                "included_source_ids": ["SRC-001"],
                "exclusions": [],
                "counterevidence_search": True,
                "citation_tracking": True,
                "returned_content_size": 220,
                "returned_content_unit": "characters",
                "page_count": 1,
                "external_tool_calls": 0,
            },
        ]
        (project_root / "research/search_log.jsonl").write_text(
            "".join(
                json.dumps(entry, ensure_ascii=False) + "\n"
                for entry in search_entries
            ),
            encoding="utf-8",
        )
        coverage = {
            category: "已覆盖" for category in REQUIRED_SEARCH_CATEGORIES
        }
        coverage_entries = [
            {
                "direction_id": "DIR-001",
                "research_question_ids": ["RQ-001"],
                "query_ids": ["QRY-001"],
            },
            {
                "direction_id": "DIR-002",
                "research_question_ids": [],
                "query_ids": ["QRY-002"],
            },
        ]
        coverage_lines = ["schema_version: 1", "direction_coverage:"]
        for entry in coverage_entries:
            coverage_lines.extend(
                [
                    f'  - direction_id: "{entry["direction_id"]}"',
                    "    research_question_ids: "
                    + json.dumps(entry["research_question_ids"], ensure_ascii=False),
                    "    query_ids: "
                    + json.dumps(entry["query_ids"], ensure_ascii=False),
                    "    coverage: " + json.dumps(coverage, ensure_ascii=False),
                    "    coverage_notes: {}",
                    '    chinese_keywords: ["规则分类", "稳定性", "失败结果"]',
                    '    english_keywords: ["rule classification", "robustness", "negative results"]',
                    '    citation_tracking_source_ids: ["SRC-001"]',
                    '    planned_languages: ["zh", "en"]',
                    '    covered_languages: ["zh", "en"]',
                    '    planned_platforms: ["local synthetic fixture catalog"]',
                    '    covered_platforms: ["local synthetic fixture catalog"]',
                    '    planned_date_range: "2026-07-22 synthetic range"',
                    '    covered_date_range: "2026-07-22 synthetic range"',
                    "    independent_source_yield_history: [1.0, 0.0]",
                    "    new_method_categories_history: [1, 0]",
                    "    key_questions_covered: true",
                    "    counterevidence_completed: true",
                    "    citation_tracking_completed: true",
                    "    uncovered_scope: []",
                    '    stop_reason: "observable yield declined and the latest batch added no method category"',
                    '    stop_status: "已停止"',
                    '    last_updated_at: "2026-07-22T10:10:00+08:00"',
                ]
            )
        (project_root / "research/search_coverage.yaml").write_text(
            "\n".join(coverage_lines) + "\n", encoding="utf-8"
        )
        (project_root / "research/sources.yaml").write_text(
            """schema_version: 1
sources:
  - source_id: "SRC-001"
    title: "Synthetic fixture specification"
    creators: ["Local test suite"]
    url: null
    doi_or_identifier: "urn:codex-test:synthetic-fixture-v1"
    published_at: "2026-07-22"
    accessed_at: "2026-07-22"
    source_type: "测试规范"
    quality_level: 1
    provenance_level: "原始来源"
    primary_source_id: null
    independence_group: "synthetic-fixture-v1"
    usage_role: "关键证据"
    data_classification: "公开"
    version: "1"
    license: "CC0-1.0"
    contains_restricted_content: false
    external_transfer_allowed: false
    accessibility_status: "可访问"
    locator_exists: true
    locator_verified_at: "2026-07-22"
    locator_verification_method: "官方登记"
    update_retraction_conflict_status: "无已知问题"
    notes: "Runtime-only fictional fixture metadata."
""",
            encoding="utf-8",
        )
        (project_root / "research/claims.yaml").write_text(
            """schema_version: 1
claims:
  - claim_id: "CLM-001"
    claim: "The synthetic fixture specification defines fixed generation and evaluation boundaries."
    research_question_ids: ["RQ-001"]
    source_ids: ["SRC-001"]
    evidence_locations: ["fixture specification section 1"]
    support_level: "直接支持"
    source_independence: "独立"
    temporal_status: "当前有效"
    conflict_status: "无已知冲突"
    verification_status: "已核验"
    citation_support_verified: true
    numeric_details_verified: true
    scope_match_verified: true
    causality_checked: true
    model_inference_status: "非模型推论"
    conflict_type: "无"
    conflict_reason: null
    uncertainty_notes: null
    adverse_evidence_retained: true
    verification_notes: "Checked the synthetic locator, scope, version, and evidence location."
    eligible_for_research_contract: true
""",
            encoding="utf-8",
        )
        resources_path = project_root / "research/resources.yaml"
        resources_template = """schema_version: 1
snapshots:
  - resource_id: "RES-001"
    recorded_at: "2026-07-22T10:15:00+08:00"
    status: "当前"
    input_tokens: null
    output_tokens: null
    search_return_size: 400
    search_return_unit: "characters"
    search_queries: 2
    search_pages: 2
    external_tool_calls: 0
    api_calls: 0
    elapsed_seconds: 900
    estimated_cost: 0
    cost_currency: "CNY"
    evidence_file_bytes: {evidence_bytes}
    claim_count: 1
    context_compactions: 0
    unavailable_metrics: ["input_tokens: local fixture does not report tokens", "output_tokens: local fixture does not report tokens"]
"""
        evidence_bytes = 0
        for _ in range(4):
            resources_path.write_text(
                resources_template.format(evidence_bytes=evidence_bytes),
                encoding="utf-8",
            )
            measured = WorkspaceValidator(project_root).phase_one_evidence_bytes()
            if measured == evidence_bytes:
                break
            evidence_bytes = measured
        affected_fields = [
            "研究目标",
            "研究问题",
            "成功标准",
            "数据、baseline 与评测",
            "数据与隐私边界",
            "计算与外部服务",
            "阶段二执行约束与资源方案",
            "Skills、依赖与授权",
            "范围外事项",
        ]
        (project_root / "research/decisions.yaml").write_text(
            """schema_version: 1
decisions:
  - decision_id: "DEC-001"
    decision: "Use the local public synthetic rule-classification direction."
    user_input_source: "2026-07-21 synthetic exercise turn 6"
    supporting_claim_ids: ["CLM-001"]
    alternatives: ["Use real user text", "Call an external model API"]
    rejection_reasons: ["Unnecessary privacy risk", "Unnecessary transfer and cost"]
    user_confirmation_status: "已确认"
    affected_contract_fields: """
            + json.dumps(affected_fields, ensure_ascii=False)
            + """
    triggers_phase_rollback: false
    decided_at: "2026-07-21"
""",
            encoding="utf-8",
        )
        for _ in range(4):
            resources_path.write_text(
                resources_template.format(evidence_bytes=evidence_bytes),
                encoding="utf-8",
            )
            measured = WorkspaceValidator(project_root).phase_one_evidence_bytes()
            if measured == evidence_bytes:
                break
            evidence_bytes = measured

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
            "returned_content_size": 10,
            "returned_content_unit": "characters",
            "page_count": 1,
            "external_tool_calls": 0,
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
    def valid_resource(**overrides: object) -> dict[str, object]:
        """Create one schema-valid phase-one resource snapshot."""

        resource: dict[str, object] = {
            "resource_id": "RES-001",
            "recorded_at": "2026-07-22T10:15:00+08:00",
            "status": "当前",
            "input_tokens": None,
            "output_tokens": None,
            "search_return_size": 0,
            "search_return_unit": "characters",
            "search_queries": 0,
            "search_pages": 0,
            "external_tool_calls": 0,
            "api_calls": 0,
            "elapsed_seconds": 0,
            "estimated_cost": 0,
            "cost_currency": "CNY",
            "evidence_file_bytes": 0,
            "claim_count": 0,
            "context_compactions": 0,
            "unavailable_metrics": [
                "input_tokens: unavailable in local fixture",
                "output_tokens: unavailable in local fixture",
            ],
        }
        resource.update(overrides)
        return resource

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
            "研究目标",
            "研究问题",
            "成功标准",
            "数据、baseline 与评测",
            "数据与隐私边界",
            "计算与外部服务",
            "阶段二执行约束与资源方案",
            "Skills、依赖与授权",
            "范围外事项",
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
