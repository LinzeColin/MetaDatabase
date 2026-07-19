# stock-commercial-opportunities-skill Agent Contract

## 永久边界

- 中文优先；代码、ticker、filing form、API 与错误保留英文。
- 本项目是专有源码备份，不是本地安装目录。禁止写入 `~/.agents/skills` 或 `~/.codex/skills`。
- MetaDatabase 当前公开可见：仅提交公开安全内容。禁止会话、客户/组合/交易、账户、邮件、凭据、内部路径、MNPI 或未授权第三方材料。
- 研究候选不等于投资建议。禁止个性化 buy/sell/hold、仓位、收益保证、无风险表达、拉群荐股、自动下单或推广链接。
- 当前价格、估值、预期、财报、公告、法规和事件日期必须同次核验；缺失即降级。
- 只读优先；外部发布、交易、外联和连接账户均需单独授权。

## 修改纪律

1. 先读根 `AGENTS.md`、本文件、`task-pack/CODEX_MASTER_TASK.md`。
2. 只在隔离 worktree 修改；MetaDatabase 主树保持 `main` 且干净。
3. 历史 ZIP 为版本谱系，禁止静默重写；新增版本必须更新 SHA、SOURCE_INVENTORY、CHANGELOG 与 manifest。
4. 确定性脚本仅 Python 标准库；不得把付费/专有数据固化进 fixture。
5. 任何评分都必须分离商业机会、发行人敞口、股票设置、证据置信度与证据成熟度。
6. `ADVANCE_RESEARCH` 只表示进入更深研究，不表示适合买入或通过投资委员会。

## 完成门禁

- 任务包测试、strict validators、JSON/JSONL/YAML/links、secret/local-path scan 全部通过。
- v3 ZIP 与 `BACKUP_MANIFEST.sha256` 可重算。
- PR 合并后从 GitHub main 独立下载并复核 ZIP SHA。
- 未跑的新鲜模型触发/A-B、未安装和未做真实投资决策必须保持 `NOT_RUN`。
