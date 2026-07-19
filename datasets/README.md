# 数据集

将本地数据集放在这里。默认不要提交数据；仅在用户明确指定、许可证允许且 `.gitignore` 已为目标数据集配置白名单时提交。

开始实验前，还应在 `RESEARCH.md` 记录数据分类、个人信息、内部或受限属性、脱敏要求、保留/删除要求和公开限制。数据未明确获得外部传输授权时，默认不得将原文、样本、标注或可识别摘要发送给外部 API。只传输已授权且完成实验所必需的最少数据。

## 动态登记

首次确认具体数据集时，由 Codex 创建 `datasets/registry.yaml`；没有实际数据集时不创建空登记表或虚假示例。每个条目至少记录 `id`、`name`、`source`、`version`、`license`、`checksum`、`path`、`classification` 和 `external_api_allowed`。受限 URL、凭据、个人信息或原始样本不得写入登记表。
