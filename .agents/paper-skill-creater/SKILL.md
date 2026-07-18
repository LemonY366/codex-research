---
name: paper-skill-creater
description: "将论文全文转化为可复用的 paper skill。当用户提供论文 PDF、OCR Markdown、论文全文 Markdown 或 LaTeX 项目，并需要通过 PaddleOCR 进行 PDF 转 Markdown、表格/公式/版面解析，或创建用于了解、引用、撰写相关工作、方法对比和实验复现的结构化论文 skill 时，使用此 skill。"
---

# Paper Skill 创建指南

从论文全文生成结构化的 Agent skill。生成的 paper skill 应服务于两个核心场景：快速了解论文，以及在写论文时准确引用该论文。

## 输入

用户会提供以下之一：
- **PDF 文件**: 优先转换为带版面结构的 Markdown，再提取结构化信息
- **Markdown 文件**: 论文全文的 `.md` 文件（通过 OCR 提取或手动整理）
- **LaTeX 项目**: 论文的源文件（如 arXiv 下载的 `.tex` 文件）

## 输出

生成 `paper-{论文缩写}/` 目录，包含：

```
paper-{论文缩写}/
├── SKILL.md              # 论文核心信息（摘要、创新点、实验结果）
├── fulltext.md            # 统一后的论文全文（PDF 时由解析生成）
└── source/                # 原始文件、PaddleOCR JSON 与提取资源（如有）
```

**全文文件保留规则：**
- 用户提供的 `.md` 文件 → 原样保存在 `source/`，并作为 `fulltext.md`
- 用户提供的 LaTeX 项目 → 保留整个项目目录在 `source/`
- PDF → 保留原 PDF 路径或副本、PaddleOCR JSON/资源与生成的 `fulltext.md`

## 工作流程

### 1. 准备论文全文

按输入类型选择低损失路径：

- **LaTeX 项目**：优先解析源文件；保留 `.tex`、`.bib` 与图表目录。
- **已有 Markdown**：保留原文件，检查章节、公式、表格和页码来源是否完整。
- **PDF**：优先使用本仓库的 `paddleocr-doc-parsing` Skill 进行结构化解析；学术论文通常包含双栏、表格、公式、图和复杂阅读顺序，默认使用 `doc_parsing`，而非纯文本 OCR。

对本地 PDF 的标准命令为：

```bash
paddleocr api \
  --model_type doc_parsing \
  --model PP-StructureV3 \
  --file_path "<paper.pdf>" \
  --prettify_markdown True \
  --output "<output>/paddleocr.json" \
  --save_resources "<output>/resources"
```

将各页 `markdownText` 按页序合并为 `fulltext.md`，保留页码分隔标记；同时归档 API 返回的 JSON 与资源目录，便于回查图、表、公式和阅读顺序。

仅当 PDF 内容是简单、单栏的纯文字，或任务只需要逐行文字与坐标时，才使用 `paddleocr-text-recognition` Skill 的 `ocr` 模型。扫描件、旋转页、复杂布局或公式/表格识别异常时，保留预处理选项并记录失败页；不要静默用猜测补全内容。

### 2. 读取并理解论文全文

分析论文结构，提取关键信息：
- **完整标题、作者、机构、发表信息**
- **摘要**（原文引用）
- **核心问题**（论文解决什么）
- **主要贡献**（技术创新点）
- **实验结果**（关键数据和结论）
- **BibTeX 引用**
- **局限性和适合引用的观点**

### 3. 生成 SKILL.md

参考 [references/skill_template.md](references/skill_template.md)，生成结构化的 SKILL.md：

- **Frontmatter**:
  - `name`: 使用 `paper-{slug}` 短名称，不超过 64 个字符，优先与目录名一致；不要放完整论文标题
  - `description`: 必须包含完整论文标题，并明确写出“当需要了解、引用或围绕该论文撰写相关工作/方法对比/实验复现时，使用此 skill”
- **BibTeX**: 完整引用格式
- **摘要**: 原文摘要
- **使用指南**: 说明该论文在了解、引用、相关工作、方法对比和实验复现中的使用方式
- **核心痛点与背景**: 论文解决的问题
- **核心创新**: 主要贡献和技术方法
- **实验结果**: 关键实验数据和表格
- **与相关工作的对比**: 优缺点分析
- **如何使用这篇论文**: 适用场景和实现建议
- **局限性**: 论文自身指出的不足

### 4. 写作导向整理

为每个 paper skill 补充可直接服务论文写作的内容：

- **可引用观点**: 该论文可以支持哪些论断，避免夸大原文结论
- **相关工作定位**: 该论文属于数据集、数据合成、模型、评测、系统框架或应用场景中的哪一类
- **对比维度**: 可与哪些方法比较，比较时应关注数据规模、schema 难度、查询复杂度、模型成本、执行准确率等哪些维度
- **引用注意事项**: 标明结果对应的数据集、split、metric、模型设置和是否来自论文原文

### 5. 保留全文与解析证据

保留可追溯的全文来源：
- PDF：保存 `fulltext.md`、原 PDF 路径或副本、PaddleOCR JSON、资源目录，以及页码映射。
- `.md`：保留原文件并将其作为 `fulltext.md`。
- LaTeX：保留整个项目目录结构；若生成 Markdown，记录生成命令与源 `.tex` 文件。

对于表格、公式、图注、作者信息和实验数字，应在笔记或 SKILL.md 中标明页码或章节。PaddleOCR 结果与原 PDF 不一致时，以原 PDF 人工核对后的内容为准，并记录修正原因。

### 6. 校验

创建或更新后执行以下检查：

- `SKILL.md` frontmatter 只有 `name` 和 `description`
- `name` 长度不超过 64 个字符
- `description` 包含完整论文标题
- `description` 明确包含“当需要了解、引用”
- 正文 H1 使用完整论文标题
- BibTeX、摘要、实验数据和结论与原文一致
- `fulltext.md` 的章节顺序与原文一致，并保留 PDF 页码映射（若输入为 PDF）
- 关键表格、公式、图注和实验数字已对照原 PDF 或 LaTeX 源文件核验

## 注意事项

- **准确提取**: 确保 SKILL.md 中的信息与原文一致
- **简洁聚焦**: SKILL.md 突出核心信息，详细内容参考用户提供的全文文件
- **命名规范**: 目录和 `name` 使用 `paper-{论文缩写}` 格式，完整标题只放在 `description` 和正文标题中
- **引用完整**: BibTeX 包含所有必要字段
- **写作可用**: 明确该论文适合放入相关工作、方法背景、实验设置或局限性讨论的哪些位置
- **保留原文件**: 用户提供的全文文件原样保留，不做修改
- **PaddleOCR 优先**: 复杂 PDF 使用 `paddleocr-doc-parsing`；纯文字逐行提取才使用 `paddleocr-text-recognition`
- **解析可追溯**: 保存 Markdown、原始 JSON、资源和页码映射，不把 OCR 输出视为无需核验的事实
