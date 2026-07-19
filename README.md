# Codex 科研工作台

这是一个面向 Codex 的可复现科研项目模板。项目将研究任务、论文源码、实验实现、实际运行证据和论文写作分离保存，使工作可在对话中断后继续，并让论文结论可追溯到具体实现与运行结果。

## 快速开始

克隆项目并在项目目录中直接启动 Codex：

```bash
git clone git@github.com:linhx1999/codex-research.git
cd codex-research
codex
```

后续研究、实验和写作均通过与 Codex 的提示词交互完成。首次进入项目时，可让 Codex 阅读 `README.md`、`RESEARCH.md` 和 `TODO.md`，并根据当前状态与用户头脑风暴或继续已有工作；无需手动执行常规安装、实验或写作命令。已有克隆时，直接在其项目目录运行 `codex` 即可。

当前模板不把根目录 `main.py` 或 `research` 命令作为工作流入口，也不要求用户运行或完善它们；具体研究代码和实验入口由 Codex 在研究方案确认后按需生成。

敏感配置是例外：API key、令牌、数据库凭据和受限数据访问应由用户自行在本地完成配置，例如按需创建 `.env`。不要在对话、提示词、日志或提交中提供真实密钥；`.env` 不应被 Codex 读取、输出或提交。数据集、模型和运行产物的存放规则见对应目录的 README。

## 实验资源

本模板支持由 Codex 按具体研究任务规划并生成使用本地 GPU、外部模型 API 或二者联合的实验；外部模型 API 按 OpenAI-compatible 接口处理。Codex 会根据研究问题、数据、预算与用户确认的约束动态设计两类资源的具体分工，模板不预设固定的 API 与 GPU 组合方式。

用户负责准备本地 GPU、驱动、模型文件和真实 API 配置。API 地址、模型名称等非敏感配置可参考 `.env.example`；真实密钥继续遵循上述安全边界，不得出现在对话、代码、日志或提交中。

模板核心依赖应保持最小。具体研究需要新增或删除依赖时，Codex 会先说明用途、替代方案与环境影响，再与用户确认；GPU 框架、OCR、绘图等大型或特定硬件依赖默认按需引入。依赖变更时必须同步提交 `pyproject.toml` 与 `uv.lock`。

## 工作流程

1. 在 [RESEARCH.md](RESEARCH.md) 定义研究目标、问题、指标、预算和范围。
2. 在 `src/` 实现论文方法与可复用训练/评测代码。
3. 为每个实验在 `experiments/scripts/` 保存一个可直接运行的脚本。
4. 每次实际执行均在 `experiments/runs/` 创建独立目录，保存命令、配置快照、日志、元数据和指标。
5. 在 [paper/draft_zh.md](paper/draft_zh.md) 起草和修订论文；只有用户明确要求时才同步到 `paper/main.tex`。

数值、表格和实证性结论必须可追溯到相应实验 ID 与运行目录；不可核实的信息标记为 `TODO`。

若 `RESEARCH.md` 与 `TODO.md` 尚未提供足够完整的研究目标、约束和下一步行动，Codex 会先与用户进行头脑风暴，确认问题、成功标准、数据、基线、预算与第一阶段产物后再开始实施。

## 阶段门禁

三个阶段均有明确的进入、完成、停止、恢复与回退条件，详见 [三阶段工作流门禁](docs/WORKFLOW_GATES.md)。条件不满足时，Codex 应暂停相关工作、记录原因和恢复条件，并仅在需要新决策、授权或访问权限时请用户处理。不得为了自动推进而绕过预算、数据许可证、隐私、外部传输或证据完整性要求；未确认数据可外发时，默认不将其发送给外部 API。

## 三阶段推荐模型与命令

模型选择应服从任务难度与成本预算；以下是本项目的默认建议。可用模型和推理等级取决于账号与所用 Codex 客户端。

### 阶段一：调研与设计

初始的 1–3 轮头脑风暴使用 **GPT-5.6 Sol / Ultra**，处理开放式问题定义、研究空白与方案取舍；在方向明确后切换到 **GPT-5.6 Sol / Medium**，以较低成本完善 `RESEARCH.md` 和 `TODO.md`。

可先使用普通对话或 `/plan`，例如：

```text
/plan 阅读 RESEARCH.md 和 TODO.md；与我头脑风暴研究xx问题、成功标准、数据集、基线、预算和阶段一交付物。确认后更新这两个文件。
```

### 阶段二：实验与分析

选择 **GPT-5.6 Terra / Low**，然后使用 `/goal` 执行已定义、可验证的实验任务：

```text
/goal 执行 TODO.md 中的第二阶段“实验与分析”。记录期间的命令、文档、指标和失败原因等信息。
```

### 阶段三：论文写作（可选专利）

继续使用 **GPT-5.6 Terra / Low**，以 `/goal` 将已验证实验结果写入唯一工作草稿 `paper/draft_zh.md`：

```text
/goal 根据已验证的 experiments/runs/ 结果完成 TODO.md 中“阶段三：论文写作”的事项。所有数值和实验结论必须标注实验 ID；默认只修改 paper/draft_zh.md，无法核实的信息标记 TODO。
```

专利工作仅在用户明确要求时加入阶段三。`/goal` 的目标应包含成果、约束与可验证的完成条件；可使用 `/goal edit`、`/goal pause`、`/goal resume` 和 `/goal clear` 管理运行中的目标。更多说明见 [Codex 模型选择](https://developers.openai.com/codex/codex-manual.md#model-selection) 与 [Goal 模式](https://developers.openai.com/codex/codex-manual.md#set-or-view-a-task-goal-with-goal)。

## 目录说明

```text
README.md            # 项目入口与使用说明
AGENTS.md            # Codex 的长期工作规则
RESEARCH.md          # 全局唯一的研究任务合同
TODO.md              # 当前待办事项
datasets/            # 数据集与来源说明
models/              # 模型检查点与版本说明
baselines/           # 外部对比方法源码与版本登记
src/                 # 论文方法、训练和评测源码
scripts/             # 数据预处理等跨实验通用脚本
experiments/         # 实验脚本、运行记录与索引
paper/               # 草稿、正式论文、引用与图像
patents/             # 专利技术交底、权利要求草案与附图
docs/                # 稳定、跨阶段的项目规范
```

进入某个目录前，优先阅读该目录的 `README.md`。在仓库根目录启动 Codex 时，它应遵循 [AGENTS.md](AGENTS.md)。

仓库中哪些内容由模板预置、哪些由 Codex 根据研究任务动态生成、哪些必须由用户在本地管理，以及哪些运行证据生成后不得改写，统一遵循 [模板与动态内容边界](docs/TEMPLATE_BOUNDARIES.md)。具体研究文件和代码由 Codex 在已确认范围内生成；真实凭据、受限访问和必要授权仍由用户负责。

数据、模型、baseline 和实验的 `registry.yaml` 只在首次确认真实对象时由 Codex 创建，不预置空表或虚假条目。模板提供只读的 `scripts/validate_workspace.py`，用于检查必需文档、阶段状态、动态登记、运行证据、疑似凭据和论文实验 ID 追溯；它不会启动 Codex、读取 `.env`、创建登记表或修改研究内容。

## 观察进展

用户可随时查看 [TODO.md](TODO.md) 了解三个阶段的当前进展：调研与设计、实验与分析、论文写作（可选专利成果整理）。默认阶段三只进行论文写作；只有用户明确要求时才新增专利工作。执行任务时应及时更新各阶段的进行中、下一步和已完成事项；研究目标、约束和长期决策仍维护在 `RESEARCH.md`。

## 文档维护

每次变更仓库内容时，都应同步检查根目录 `README.md` 和 `AGENTS.md` 是否仍准确反映项目结构、使用方式、边界与维护约定。仅影响某个子目录的变更，应先更新该目录的说明文档；如果同时影响根目录使用方式或 Codex 工作流，再更新根目录文档。详细的 agent 侧约束以 `AGENTS.md` 的 `Documentation Update Policy` 为准。
