# Codex 科研工作台

这是一个面向 Codex 的可复现科研项目模板。项目将研究任务、论文源码、实验实现、实际运行证据和论文写作分离保存，使工作可在对话中断后继续，并让论文结论可追溯到具体实现与运行结果。

## 快速开始

克隆项目并在项目目录中直接启动 Codex：

```bash
git clone git@github.com:linhx1999/codex-research.git
cd codex-research
codex
```

后续研究、实验和写作均通过与 Codex 的提示词交互完成。首次进入项目时，可让 Codex 阅读 `README.md` 和 `RESEARCH.md`；进入实验或写作阶段时，再分别读取 `experiments/TODO.md` 或 `paper/TODO.md`。无需手动执行常规安装、实验或写作命令。已有克隆时，直接在其项目目录运行 `codex` 即可。

当前模板不把根目录 `main.py` 或 `research` 命令作为工作流入口，也不要求用户运行或完善它们；具体研究代码和实验入口由 Codex 在研究方案确认后按需生成。

敏感配置是例外：API key、令牌、数据库凭据和受限数据访问应由用户自行在本地完成配置，例如按需创建 `.env`。不要在对话、提示词、日志或提交中提供真实密钥；`.env` 不应被 Codex 读取、输出或提交。数据集、模型和运行产物的存放规则见对应目录的 README。

## 实验资源

本模板支持由 Codex 按具体研究任务规划并生成使用本地 GPU、外部模型 API 或二者联合的实验；外部模型 API 按 OpenAI-compatible 接口处理。Codex 会根据研究问题、数据、预算与用户确认的约束动态设计两类资源的具体分工，模板不预设固定的 API 与 GPU 组合方式。

用户负责准备本地 GPU、驱动、模型文件和真实 API 配置。API 地址、模型名称等非敏感配置可参考 `.env.example`；真实密钥继续遵循上述安全边界，不得出现在对话、代码、日志或提交中。

模板核心依赖应保持最小。具体研究需要新增或删除依赖时，Codex 会先说明用途、替代方案与环境影响，再与用户确认；GPU 框架、OCR、绘图等大型或特定硬件依赖默认按需引入。依赖变更时必须同步提交 `pyproject.toml` 与 `uv.lock`。

## 工作流程

1. 在 [RESEARCH.md](RESEARCH.md) 定义当前有效研究目标、问题、指标、预算、范围、确认状态和一致性关系；阶段一详细检索与证据进入 `research/`。
2. 在 `src/` 实现论文方法与可复用训练/评测代码。
3. 为每个实验在 `experiments/scripts/` 保存一个可直接运行的脚本。
4. 每次实际执行均在 `experiments/runs/` 创建独立目录，保存命令、配置快照、日志、元数据和指标。
5. 在 [paper/draft_zh.md](paper/draft_zh.md) 起草和修订论文；只有用户明确要求时才同步到 `paper/main.tex`。

数值、表格和实证性结论必须可追溯到相应实验 ID 与运行目录；不可核实的信息标记为 `TODO`。

若 `RESEARCH.md` 尚未提供足够完整的研究目标、约束和阶段一行动，Codex 会先与用户进行头脑风暴，确认问题、成功标准、数据、基线、预算与第一阶段产物后再开始实施。关键合同字段使用 `已确认`、`暂定`、`待确认`、`存在冲突` 或 `不适用` 标识状态，并记录信息来源、确认日期、决策 ID 与证据 ID；阶段二和阶段三的行动分别维护在 `experiments/TODO.md` 与 `paper/TODO.md`。

阶段一按 `INTAKE → DIVERGE → SEARCH → COMPARE → DRAFT → CONFIRM → GATE_CHECK` 推进，具体进入条件、交互动作、确认范围、停止和回退规则见 [阶段一交互、确认与恢复协议](docs/PHASE_ONE_PROTOCOL.md)。方向、数据、指标、预算和授权分别确认；“可以考虑”或一般性同意不构成付费、外发或高风险授权。每轮交互结束前更新 `RESEARCH.md` 的会话恢复摘要，下一会话即可从已确认事项、否决方案、暂定假设、证据、未决问题和下一任务继续。

`RESEARCH.md` 只保存当前研究合同、全局状态、阶段一当前行动、关键未决问题、授权、决策、阶段切换和调研证据摘要。搜索流水账、网页或论文全文、命令输出、实验日志与指标明细不得堆积在其中。研究问题、决策、未决问题、来源、调研主张、授权和阶段切换使用稳定 ID；研究问题还应通过一致性表关联数据、baseline、指标、成功标准与 `experiments/TODO.md` 中的计划实验。

阶段一的可复现证据保存在 [`research/`](research/)：`search_log.jsonl` 记录脱敏后的实际查询，`sources.yaml` 登记正式来源，`claims.yaml` 维护最小事实主张与证据关系，`decisions.yaml` 解释持久研究决策，`summaries/` 保存按研究问题压缩的摘要。结构化元数据可以提交不代表来源全文可以提交；受限资料、版权全文、完整聊天和工具原始输出不得写入该目录。

## 阶段门禁

三个阶段均有明确的进入、完成、停止、恢复与回退条件，详见 [三阶段工作流门禁](docs/WORKFLOW_GATES.md)。条件不满足时，Codex 应暂停相关工作、记录原因和恢复条件，并仅在需要新决策、授权或访问权限时请用户处理。不得为了自动推进而绕过预算、数据许可证、隐私、外部传输或证据完整性要求；未确认数据可外发时，默认不将其发送给外部 API。

仓库级 Skills 位于 `.agents/skills/`，其三阶段适用范围见 [三阶段 Skill 使用规则](docs/SKILL_USAGE.md)。Skill 由用户显式指定或 Codex 根据实际任务匹配，不会因为进入某个阶段而全部运行；涉及外部 OCR、依赖安装、创建新的 paper Skill 或生成 DOCX/PPTX 等可选交付物时，仍需满足对应授权、预算、隐私和阶段门禁。

## 三阶段推荐模型与命令

模型选择应服从任务难度与成本预算；以下是本项目的默认建议。可用模型和推理等级取决于账号与所用 Codex 客户端。

### 阶段一：调研与设计

初始的 1–3 轮头脑风暴使用 **GPT-5.6 Sol / Ultra**，处理开放式问题定义、研究空白与方案取舍；在方向明确后切换到 **GPT-5.6 Sol / Medium**，以较低成本完善包含阶段一任务的 `RESEARCH.md`。

可先使用普通对话或 `/plan`，例如：

```text
/plan 阅读 RESEARCH.md；与我头脑风暴研究xx问题、成功标准、数据集、基线、预算和阶段一交付物。确认后更新该文件，并生成 experiments/TODO.md 中可执行的阶段二任务。
```

### 阶段二：实验与分析

选择 **GPT-5.6 Terra / Low**，然后使用 `/goal` 执行已定义、可验证的实验任务：

```text
/goal 执行 experiments/TODO.md 中的实验与分析任务。详细命令、指标和失败原因保存到新的 experiments/runs/ 运行记录。
```

### 阶段三：论文写作（可选专利）

继续使用 **GPT-5.6 Terra / Low**，以 `/goal` 将已验证实验结果写入唯一工作草稿 `paper/draft_zh.md`：

```text
/goal 根据已验证的 experiments/runs/ 结果完成 paper/TODO.md 中的论文写作事项。所有数值和实验结论必须标注实验 ID；默认只修改 paper/draft_zh.md，无法核实的信息标记 TODO。
```

专利工作仅在用户明确要求时加入阶段三。`/goal` 的目标应包含成果、约束与可验证的完成条件；可使用 `/goal edit`、`/goal pause`、`/goal resume` 和 `/goal clear` 管理运行中的目标。更多说明见 [Codex 模型选择](https://developers.openai.com/codex/codex-manual.md#model-selection) 与 [Goal 模式](https://developers.openai.com/codex/codex-manual.md#set-or-view-a-task-goal-with-goal)。

## 目录说明

```text
README.md            # 项目入口与使用说明
AGENTS.md            # Codex 的长期工作规则
RESEARCH.md          # 当前有效研究合同与全局工作流状态
research/            # 阶段一查询、来源、主张、决策与精简摘要
datasets/            # 数据集与来源说明
models/              # 模型检查点与版本说明
baselines/           # 外部对比方法源码与版本登记
src/                 # 论文方法、训练和评测源码
scripts/             # 数据预处理等跨实验通用脚本
tests/               # 工作区验证器的标准库回归测试
experiments/         # 实验脚本、运行记录与索引
  TODO.md            # 阶段二实验与分析任务
paper/               # 草稿、正式论文、引用与图像
  TODO.md            # 阶段三论文写作任务
patents/             # 专利技术交底、权利要求草案与附图
docs/                # 稳定、跨阶段的项目规范
.agents/skills/      # Codex 可按任务发现和调用的仓库级 Skills
```

进入某个目录前，优先阅读该目录的 `README.md`。在仓库根目录启动 Codex 时，它应遵循 [AGENTS.md](AGENTS.md)。

仓库中哪些内容由模板预置、哪些由 Codex 根据研究任务动态生成、哪些必须由用户在本地管理，以及哪些运行证据生成后不得改写，统一遵循 [模板与动态内容边界](docs/TEMPLATE_BOUNDARIES.md)。具体研究文件和代码由 Codex 在已确认范围内生成；真实凭据、受限访问和必要授权仍由用户负责。

数据、模型、baseline 和实验的 `registry.yaml` 只在首次确认真实对象时由 Codex 创建，不预置空表或虚假条目。实验 registry 还需关联研究问题、成功标准和决策 ID。`research/` 的四个阶段一证据文件属于预置结构化集合，可以在尚无真实证据时保留空集合，但不得填入虚构示例。模板提供只读的 `scripts/validate_workspace.py`，用于检查必需文档、阶段状态与恢复摘要、阶段一证据和质量预警、动态登记、运行证据、疑似凭据和论文实验 ID 追溯；它不会启动 Codex、读取 `.env`、创建登记表或修改研究内容。验证器回归测试可运行 `python3 -m unittest discover -s tests -v`，不引入第三方测试依赖。

### 分阶段任务文件的程序行为

Codex 和工作区校验器以 `RESEARCH.md` 中的“当前工作流状态”为全局状态来源。程序进入不同阶段时按以下规则选择任务文件：

| 当前阶段 | 全局状态与门禁 | 可执行任务 | 详细产物 |
| --- | --- | --- | --- |
| 阶段一：调研与设计 | `RESEARCH.md` | `RESEARCH.md` 的阶段一进度 | 当前合同写入 `RESEARCH.md`；详细查询、来源、主张与决策证据进入 `research/` |
| 阶段二：实验与分析 | `RESEARCH.md` | `experiments/TODO.md` | 脚本进入 `experiments/scripts/`，每次运行证据进入新的 `experiments/runs/<run-id>/` |
| 阶段三：论文写作 | `RESEARCH.md` | `paper/TODO.md` | 正文进入 `paper/draft_zh.md`，图表和来源进入 `paper/images/` |

`scripts/validate_workspace.py` 会强制执行这套结构：根目录重新出现旧 `TODO.md` 时报告错误；全局阶段、阶段一子状态、门禁、停止原因、恢复条件和会话恢复摘要均从 `RESEARCH.md` 检查；研究合同字段确认依据、稳定 ID、研究问题一致性关系、阶段二任务回指，以及阶段一查询、来源、主张、决策的结构、交叉引用、时效、冲突、来源类型和敏感字段也会被检查。模板尚处于未开始阶段时，空的阶段一证据集合和未填写占位符只作为初始状态，不阻止校验通过。

## 观察进展

用户可查看 [RESEARCH.md](RESEARCH.md) 了解全局阶段状态和阶段一进展，查看 [experiments/TODO.md](experiments/TODO.md) 了解实验与分析任务，查看 [paper/TODO.md](paper/TODO.md) 了解论文写作任务。阶段 TODO 只保存当前行动、下一步、阻塞项和精简的完成摘要；实验细节进入运行记录，论文正文进入工作草稿。默认阶段三只进行论文写作；只有用户明确要求时才新增专利工作。

## 文档维护

每次变更仓库内容时，都应同步检查根目录 `README.md` 和 `AGENTS.md` 是否仍准确反映项目结构、使用方式、边界与维护约定。仅影响某个子目录的变更，应先更新该目录的说明文档；如果同时影响根目录使用方式或 Codex 工作流，再更新根目录文档。详细的 agent 侧约束以 `AGENTS.md` 的 `Documentation Update Policy` 为准。
