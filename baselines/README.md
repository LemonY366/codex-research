# 对比方法源码

`baselines/` 存放为对比实验克隆或引入的外部方法源码。每个子目录对应一个上游项目；不要将这些代码与本项目在 `src/` 中实现的论文方法混合。

## 使用规则

- 每个方法使用清晰的目录名，例如 `baselines/text2sql-baseline/`。
- 克隆后固定到明确的 tag 或 commit；不要在未记录来源的情况下跟随上游分支更新。
- 在方法目录或本文件中记录方法名称、论文引用、上游 URL、commit/tag、许可证和引入日期。
- 优先在 `experiments/scripts/` 中创建包装脚本运行基线，不直接改写上游源码。
- 必须修改时，保留可审阅的 patch 或在方法目录中记录改动原因、文件和对应实验 ID。
- 运行产物仍保存至 `experiments/runs/<run-id>/`，并记录所用基线版本。

## 动态登记

首次确认具体 baseline 时，由 Codex 创建 `baselines/registry.yaml`；没有实际 baseline 时不创建空登记表或虚假示例。每个条目至少记录 `id`、`name`、`upstream`、`revision`、`license` 和 `path`，并在有运行后关联实验 ID。需要鉴权的上游地址只记录非敏感公开部分，不得嵌入凭据。

不要在此目录提交数据集、模型检查点、密钥或未授权再分发的内容。
