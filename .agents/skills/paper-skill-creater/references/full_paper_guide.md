# 论文全文内容准备指南

`full_paper.md` 是 paper skill 的可选补充文件，用于存储论文完整文本，便于 Agent 深入理解细节。

## 内容获取方式

### PDF 结构化解析（推荐）

```bash
# 学术论文通常有双栏、表格、公式与图注；使用 PaddleOCR 文档解析
paddleocr api \
  --model_type doc_parsing \
  --model PP-StructureV3 \
  --file_path /path/to/paper.pdf \
  --prettify_markdown True \
  --output /path/to/output/paddleocr.json \
  --save_resources /path/to/output/resources
```

将 JSON 中每页的 `markdownText` 依页序合并为 `fulltext.md`，并保留原始 JSON、资源目录和页码分隔标记。仅当任务需要简单逐行文本/坐标、且 PDF 没有复杂表格或公式时，才使用 `paddleocr api --model_type ocr`。

### arXiv源文件

```bash
# 下载源文件
wget https://arxiv.org/e-print/论文ID

# 解压后找到.tex文件，转换为markdown
pandoc main.tex -o paper.md
```

## 注意事项

1. **版权问题**: 仅存储自己拥有权限的论文内容
2. **结构化优先**: 保持论文原有的章节结构
3. **公式处理**: OCR 可能无法准确识别复杂公式，必须对照原 PDF 或 LaTeX 源文件手动校对
4. **图表说明**: 保留图表的 caption 文本、页码和对应资源
5. **表格与阅读顺序**: 核对双栏顺序、表格单元格、脚注和跨页内容；发现异常时记录页码与修正原因
