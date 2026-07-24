# 公开证据契约

当前 Stage 0 证据使用 `schemas/stage0-evidence-v1.0.1.schema.json`，位于
`evidence/tasks/T0001.json` 至 `T0007.json` 和 `evidence/stage0/latest.json`。它们必须可机读、脱敏，且通过只读
`machine/tools/validate_evidence.py`。

`evidence/stage0/v1.0.0-blocked/` 是不可改写的历史判定，不代表当前交付状态。公开证据可以包含代码、结构、解析器版本、桶化状态、验收结果和不透明证据根；不得包含真实邮件、金融内容、私有仓定位、密钥或本机绝对路径。
