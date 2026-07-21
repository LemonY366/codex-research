"""Regression tests for the read-only workspace validator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        research = self.root / "research"
        research.mkdir()
        entry = {
            "query_id": "QRY-001",
            "research_question_ids": [],
            "query": "synthetic public query",
            "language": "en",
            "platform": "local fixture",
            "searched_at": "2026-07-21T10:00:00+08:00",
            "filters": {},
            "result_count": 0,
            "included_source_ids": [],
            "exclusions": [],
            "counterevidence_search": False,
            "api_key": "placeholder",
        }
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

        validator.check_stage_state()

        self.assertIn("INVALID_PHASE_ONE_STATE", self.codes(validator))

    def test_in_progress_stage_one_can_save_partial_contract(self) -> None:
        template = (REPOSITORY_ROOT / "RESEARCH.md").read_text(encoding="utf-8")
        partial = template.replace("阶段一子状态：INTAKE", "阶段一子状态：SEARCH")
        partial = partial.replace("阶段状态：未开始", "阶段状态：进行中")
        partial = partial.replace("阶段门禁：待检查", "阶段门禁：已通过")
        self.write_research(partial)
        self.copy_empty_research_evidence()
        validator = WorkspaceValidator(self.root)

        phase, status = validator.check_stage_state()
        validator.check_research_contract(phase, status)
        validator.check_phase_one_evidence(phase, status)

        errors = [item for item in validator.findings if item.severity == "ERROR"]
        self.assertEqual([], errors)

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

    def copy_empty_research_evidence(self) -> None:
        """Copy only the committed empty evidence schema into the test workspace."""

        target = self.root / "research"
        target.mkdir(parents=True, exist_ok=True)
        for name in ("search_log.jsonl", "sources.yaml", "claims.yaml", "decisions.yaml"):
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
            ("约束与预算", "零 API 调用、零 GPU 时间、2026-07-31 前完成"),
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
- 本轮已确认事项：DEC-001，确认 RQ-001、DATA-001、BASE-001、METRIC-001 与 SC-001。
- 本轮否决方案：拒绝使用真实个人数据和外部模型 API。
- 当前暂定假设：无；合同字段均已明确确认。
- 新增证据：SRC-001、CLM-001、DEC-001。
- 未解决问题：无；本轮未保留开放问题。
- 下一轮首要任务：执行 experiments/TODO.md 中的 exp-001，但本演练不实际运行实验。
- 不应重新采用的旧方案：真实用户数据、外部 API 和模型训练。

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

## 约束与预算

- 最大 GPU 时间：不适用：不使用 GPU。
- 最大 API 调用次数：0 次。
- 最大外部 API 预算：0 元。
- 截止日期：2026-07-31。

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

        search_entry = {
            "query_id": "QRY-001",
            "research_question_ids": ["RQ-001"],
            "query": "synthetic keyword classifier robustness fixture specification",
            "language": "en",
            "platform": "local synthetic fixture catalog",
            "searched_at": "2026-07-21T10:00:00+08:00",
            "filters": {"domain": "example.invalid", "date": "2026-07-21"},
            "result_count": 1,
            "included_source_ids": ["SRC-001"],
            "exclusions": [],
            "counterevidence_search": True,
        }
        (project_root / "research/search_log.jsonl").write_text(
            json.dumps(search_entry, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (project_root / "research/sources.yaml").write_text(
            """schema_version: 1
sources:
  - source_id: "SRC-001"
    title: "Synthetic fixture specification"
    creators: ["Local test suite"]
    url: "https://example.invalid/synthetic-fixture-v1"
    doi_or_identifier: null
    published_at: "2026-07-21"
    accessed_at: "2026-07-21"
    source_type: "测试规范"
    provenance_level: "原始来源"
    data_classification: "公开"
    version: "1"
    license: "CC0-1.0"
    contains_restricted_content: false
    external_transfer_allowed: false
    accessibility_status: "可访问"
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
    eligible_for_research_contract: true
""",
            encoding="utf-8",
        )
        affected_fields = [
            "研究目标",
            "研究问题",
            "成功标准",
            "数据、baseline 与评测",
            "数据与隐私边界",
            "计算与外部服务",
            "约束与预算",
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
