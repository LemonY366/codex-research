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

敏感配置是例外：API key、令牌、数据库凭据和受限数据访问应由用户自行在本地完成配置，例如按需创建 `.env`。不要在对话、提示词、日志或提交中提供真实密钥；`.env` 不应被 Codex 读取、输出或提交。数据集、模型和运行产物的存放规则见对应目录的 README。

## 实验资源

本模板支持由 Codex 按具体研究任务规划并生成使用本地 GPU、外部模型 API 或二者联合的实验；外部模型 API 按 OpenAI-compatible 接口处理。Codex 会根据研究问题、数据、资源条件与用户确认的授权设计资源分工，并记录实际 GPU 时间、API 调用和费用，用于进度展示、复现与审计。付费使用和数据外发须事先明确授权；GPU 不可用/OOM、API 连续失败、授权失效或用户暂停会触发安全停止。

用户负责准备本地 GPU、驱动、模型文件和真实 API 配置。API 地址、模型名称等非敏感配置可参考 `.env.example`；真实密钥继续遵循上述安全边界，不得出现在对话、代码、日志或提交中。

模板核心依赖应保持最小。具体研究需要新增或删除依赖时，Codex 会先说明用途、替代方案与环境影响，再与用户确认；GPU 框架、OCR、绘图等大型或特定硬件依赖默认按需引入。依赖变更时必须同步提交 `pyproject.toml` 与 `uv.lock`。

## 工作流程

1. 全局机器状态由 [`workflow/state.json`](workflow/state.json) 与追加式转换账本保存；[RESEARCH.md](RESEARCH.md) 展示其可读投影，并先通过 Codex 主导的头脑风暴形成研究方向，再定义研究合同；阶段一详细检索与证据进入 `research/`。
2. 在 `src/` 实现论文方法与可复用训练/评测代码。
3. 为每个实验在 `experiments/scripts/` 保存一个可直接运行的脚本。
4. 每次实际执行均在 `experiments/runs/` 创建独立目录，保存命令、配置快照、日志、元数据、指标及归档进度；阶段二结束前将 registry 与本地运行对账并生成证据交接。
5. 在 [paper/draft_zh.md](paper/draft_zh.md) 起草和修订论文，写作会话进度进入 `paper/sessions/`；只有用户明确要求时才同步到 `paper/main.tex`。

数值、表格和实证性结论必须可追溯到相应实验 ID 与运行目录；不可核实的信息标记为 `TODO`。

若研究方向尚不明确，Codex 会通过高信息量问题完善用户的工作方向，检查实质替代视角，并在必要时使用标题、摘要和元数据做轻量创新性或可行性侦察。非正式想法不分配正式方向 ID，也不要求完整搜索；只有值得深入验证的方向才进入正式搜索。不存在真实分叉时允许一个方向完成压力测试，不会为了数量制造候选。

阶段一仍按 `INTAKE → DIVERGE → SEARCH → COMPARE → DRAFT → CONFIRM → GATE_CHECK` 推进。最初 1–3 轮 Ultra 只进行“理解—完善—替代检查—必要侦察—修订”的方向推理，不修改项目文件、不分配 ID、不正式搜索、不设计实验，也不运行验证。方向明确后输出一次紧凑交接并切换 Medium；由 Medium 一次性更新 `RESEARCH.md`，随后完成正式搜索、比较、设计和门禁。

`RESEARCH.md` 只保存当前研究合同、机器状态的可读投影、阶段一当前行动、关键未决问题、授权、决策、阶段切换投影和调研证据摘要。尚未出现的方向、问题、证据、决策、授权和切换保持空表，不创建虚假占位记录；方向确认后才生成详细研究对象，并把确认依据集中在设计确认表。搜索流水账、网页或论文全文、命令输出、实验日志与指标明细不得堆积在其中。研究问题、决策、未决问题、来源、调研主张、授权和阶段切换使用稳定 ID；研究问题还应通过一致性表关联数据、baseline、指标、成功标准与 `experiments/TODO.md` 中的计划实验。

阶段一的正式证据保存在 [`research/`](research/)：`search_log.jsonl` 记录脱敏查询，`search_coverage.yaml` 记录正式方向的覆盖与停止依据，`sources.yaml` 登记来源，`claims.yaml` 维护最小主张，`decisions.yaml` 解释持久决策，`summaries/` 保存按研究问题压缩的摘要。结构化元数据可以提交不代表来源全文可以提交。

正式搜索围绕最接近工作、实质差异、反证、数据/指标和可行性展开，最终方向以证据饱和停止；有可回查硬阻断的方向可以提前停止但不得入选。付费、数据外发、受限访问和依赖变更只在实际动作发生前按范围授权。

## 阶段门禁

三个阶段均有明确的进入、完成、停止、恢复与回退条件，详见 [三阶段工作流门禁](docs/WORKFLOW_GATES.md)。条件不满足时，Codex 应暂停相关工作、记录原因和恢复条件，并仅在需要新决策、授权或访问权限时请用户处理。不得为了自动推进而绕过阶段二资源方案、付费授权、数据许可证、隐私、外部传输或证据完整性要求；未确认数据可外发时，默认不将其发送给外部 API。

阶段转换不得靠手工编辑状态字段完成。`scripts/transition_workflow.py` 会先执行严格门禁，再以事务方式同步 `workflow/state.json`、`workflow/transitions.jsonl` 和 `RESEARCH.md` 投影；任一检查失败都不会留下“名义进入后一阶段”的半状态。进入阶段三还必须存在已与本地运行及 registry 对账的 `experiments/evidence_handoff.yaml`。

仓库级 Skills 位于 `.agents/skills/`，其三阶段适用范围见 [三阶段 Skill 使用规则](docs/SKILL_USAGE.md)。Skill 由用户显式指定或 Codex 根据实际任务匹配，不会因为进入某个阶段而全部运行；涉及外部 OCR、依赖安装、创建新的 paper Skill 或生成 DOCX/PPTX 等可选交付物时，仍需满足对应授权、付费使用、隐私和阶段门禁。

## 三阶段推荐模型与命令

模型选择应服从任务难度、资源条件与付费授权；以下是本项目的默认建议。可用模型和推理等级取决于账号与所用 Codex 客户端。

### 阶段一：调研与设计

初始的 1–3 轮头脑风暴使用 **GPT-5.6 Sol / Ultra**，只处理开放式问题定义、研究空白、替代方向与方案取舍。Ultra 期间不修改仓库、不创建稳定 ID 或 TODO、不进行正式检索与证据登记、不补数据/评测/实验方案，也不运行验证器或测试。方向明确后先输出紧凑交接摘要，再切换到 **GPT-5.6 Sol / Medium**，由 Medium 持久化结果并以较低成本完成阶段一其余工作。

可先使用普通对话或 `/plan`，例如：

```text
/plan 只读取 RESEARCH.md 中理解当前起点所需的状态；在 Ultra 的 1–3 轮内只通过高信息量问题完善工作方向、检查实质替代方向，并仅在可能改变方向去留时进行轻量侦察。期间不要修改文件、创建 ID 或 TODO、正式搜索、登记证据、设计数据/评测/实验、运行验证器或处理其他任务。方向明确后输出研究对象、核心问题、创新性假设、最小可证伪路径、替代方向结论、范围、主要风险和剩余未知的紧凑交接摘要，然后停止并提示我切换 Sol / Medium。切换后再写入 RESEARCH.md、正式搜索、总结推荐；我确认唯一方向后补齐数据、评测和阶段二执行方案。
```

模型切换规则本身不能保证客户端自动更换模型。如果当前界面不支持自动切换，Ultra 应在交接摘要后停止，由用户切换模型或新开 Medium 会话后继续。

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
RESEARCH.md          # 当前有效研究合同与机器工作流状态投影
workflow/            # 机器工作流状态、追加式转换记录和活动实验任务进度
research/            # 阶段一正式查询、覆盖、来源/主张/决策与精简摘要
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
  sessions/          # 阶段三写作会话进度、事件与心跳
patents/             # 专利技术交底、权利要求草案与附图
docs/                # 稳定、跨阶段的项目规范
.agents/skills/      # Codex 可按任务发现和调用的仓库级 Skills
```

进入某个目录前，优先阅读该目录的 `README.md`。在仓库根目录启动 Codex 时，它应遵循 [AGENTS.md](AGENTS.md)。

仓库中哪些内容由模板预置、哪些由 Codex 根据研究任务动态生成、哪些必须由用户在本地管理，以及哪些运行证据生成后不得改写，统一遵循 [模板与动态内容边界](docs/TEMPLATE_BOUNDARIES.md)。具体研究文件和代码由 Codex 在已确认范围内生成；真实凭据、受限访问和必要授权仍由用户负责。

数据、模型、baseline 和实验的 `registry.yaml` 只在首次确认真实对象时由 Codex 创建，不预置空表或虚假条目。实验 registry 还需关联研究问题、成功标准和决策 ID。`research/` 的阶段一证据 schema 属于预置结构化集合，可以在尚无真实证据时保留空集合，但不得填入虚构示例。模板提供只读的 `scripts/validate_workspace.py`，用于检查必需文档、阶段状态与恢复摘要、阶段一证据和质量预警、动态登记、运行证据、疑似凭据和论文实验 ID 追溯；它不会启动 Codex、读取 `.env`、创建登记表或修改研究内容。验证器回归测试可运行 `python3 -m unittest discover -s tests -v`，不引入第三方测试依赖；端到端演练只在临时目录生成合成证据，结束后自动删除，不污染正式研究状态。

### 分阶段任务文件的程序行为

Codex 和工作区校验器以 `workflow/state.json` 为机器全局状态来源，并要求它与 `RESEARCH.md` 顶部投影及 `workflow/transitions.jsonl` 连续账本完全一致。程序进入不同阶段时按以下规则选择任务文件：

| 当前阶段 | 全局状态与门禁 | 可执行任务 | 详细产物 |
| --- | --- | --- | --- |
| 阶段一：调研与设计 | `workflow/state.json` + `RESEARCH.md` 投影 | `RESEARCH.md` 的精简活动区与研究设计 | 正式搜索覆盖、来源、主张和决策证据进入 `research/` |
| 阶段二：实验与分析 | `workflow/state.json` + `RESEARCH.md` 投影 | `experiments/TODO.md` | 活动进度进入 `workflow/tasks/`；脚本进入 `experiments/scripts/`，证据进入新的 `experiments/runs/<run-id>/` |
| 阶段三：论文写作 | `workflow/state.json` + `RESEARCH.md` 投影 | `paper/TODO.md` | 写作进度进入 `paper/sessions/`；正文进入 `paper/draft_zh.md`，图表和来源进入 `paper/images/` |

`scripts/validate_workspace.py` 会强制执行这套结构：根目录重新出现旧 `TODO.md` 时报告错误；机器状态、连续转换账本和 `RESEARCH.md` 投影必须一致；Codex 主导头脑风暴、趋同退出、门禁、会话恢复、研究合同、阶段一证据、registry/run 对账、运行可复现字段、任务心跳、阶段二交接和论文追溯也会被检查。模板尚处于未开始阶段时，空的阶段一证据集合和未填写占位符只作为初始状态，不阻止校验通过；进入 `GATE_CHECK` 时则启用完整合同、证据和 TODO 门禁。`RESEARCH.md` 中的阶段一复选框只是人工阅读摘要，手工勾选不会推进工作流。结构检查不能自动判断科研设计合理性或来源内容真实，仍需回查原始来源。

## 观察进展

用户可查看 [RESEARCH.md](RESEARCH.md) 了解研究合同与阶段投影，查看 [experiments/TODO.md](experiments/TODO.md) 和 [paper/TODO.md](paper/TODO.md) 了解任务。两个 TODO 文件保持原有的任务规划、下一步、阻塞项和精简完成摘要记录方式，不承担实时刷新，也不会被进度工具自动改写。阶段二与阶段三的实时状态分别进入 `workflow/tasks/` 与 `paper/sessions/`，记录当前步骤、完成数、资源消耗、检查点、阻塞原因和心跳；运行中至少每 30 秒刷新，Codex 每 30–60 秒轮询并向用户发送简短进度。超过 120 秒未刷新即报告异常，不能把沉默当作正常运行。

## 文档维护

每次变更仓库内容时，都应同步检查根目录 `README.md` 和 `AGENTS.md` 是否仍准确反映项目结构、使用方式、边界与维护约定。仅影响某个子目录的变更，应先更新该目录的说明文档；如果同时影响根目录使用方式或 Codex 工作流，再更新根目录文档。详细的 agent 侧约束以 `AGENTS.md` 的 `Documentation Update Policy` 为准。
