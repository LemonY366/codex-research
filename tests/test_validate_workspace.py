"""Regression tests for the read-only workspace validator."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validate_workspace import WorkspaceValidator


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
        validator = WorkspaceValidator(self.root)

        validator.reject_credential_fields(
            "research/search_log.jsonl", {"query_id": "QRY-001", "api_key": "placeholder"}
        )

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

        validator.check_stage_state()

        self.assertIn("INVALID_PHASE_ONE_STATE", self.codes(validator))

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
            "约束与预算",
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
