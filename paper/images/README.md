# 论文图像

`paper/images/` 存放论文正文直接引用的最终图像、图示及其可编辑源文件。所有图像必须具备清晰来源和可复现路径；不要将临时截图、未经核实的网络图片、原始数据、密钥或敏感内容放入此目录。

## 数据图

实验结果图、统计图和消融图必须满足以下要求：

- 使用 Python 的 **Seaborn** 库生成；必要时可配合 Matplotlib 完成版式微调。
- 每张图都必须有对应的、可直接运行的 Python 生成脚本，并与图像一起持久化保存。
- 生成脚本应放在明确位置，例如 `paper/images/scripts/fig-001-main-results.py`；不要只保留 Notebook 单元格或终端历史。
- 脚本应读取已记录的实验结果或分析数据，不能手动填写图中的数值。
- 脚本应在文件开头说明输入数据、输出文件、实验 ID 和运行命令，并固定随机种子（如适用）。
- 图像文件和脚本使用相同的稳定编号，例如 `fig-001-main-results.pdf` 与 `scripts/fig-001-main-results.py`。

示例：

```bash
uv run python paper/images/scripts/fig-001-main-results.py \
  --input experiments/runs/run-20260718-001-baseline/artifacts/summary.csv \
  --output paper/images/fig-001-main-results.pdf
```

## 架构图与概念图

模型架构、系统流程和方法概念图按以下流程制作：

1. 先使用 **GPT-image2** 生成美观、严谨的参考图，用于确定信息层级、布局、配色和视觉语言。
2. 根据经确认的参考图，制作可编辑的 **SVG** 正式版本。
3. 同时存档参考图、正式 SVG 和必要的导出版本（例如 PDF 或 PNG）。SVG 是后续论文修改的事实来源。

建议命名：

```text
fig-002-method-reference.png    # GPT-image2 参考图
fig-002-method.svg              # 可编辑正式源文件
fig-002-method.pdf              # 论文排版使用的导出文件（如需要）
```

参考图只能辅助设计，不能替代对方法细节的核实。SVG 中的模块名称、箭头、公式和数据流必须与 `draft_zh.md`、实验脚本及实际实现一致。

## 来源与交付规范

- 每个实证图必须能追溯到 `experiments/runs/` 中的运行目录、实验 ID 与指标文件。
- 不得手动修改数据值、坐标标签、误差线或统计结果；需要修改时应修正输入数据或生成脚本后重新导出。
- 图注中应说明数据范围、聚合方式、误差线定义和相关实验 ID。
- 外部素材必须具有兼容许可证并在论文中注明来源；未经许可的素材不得提交。
- 若图像来自 GPT-image2，应在对应草稿或图像元数据中记录提示词、生成日期及其仅作为设计参考的用途。
