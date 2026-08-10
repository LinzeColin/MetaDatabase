# JobHuntBot Online Delivery Rules

本文件适用于整个任务包。目标仓存在更严格安全或部署规则时同时遵守；冲突按 `taskpack/CANONICAL_CONTRACT.md` 裁决。

## 事实与责任

- 本包是完整 v0.3.0 Candidate，不是生产 PASS 声明。
- Delivery Agent 对真实环境观察、适配、迁移、部署、修复、回滚和重测端到端负责。
- HTTP 200、容器存活、截图、测试绿灯或 Agent 自述不能代替真实用户事务。
- 保护仓库中更新且更好的实现；先分类 `satisfied / apply / adapt / equivalent / conflict / blocked / obsolete`。

## Secret 与隐私

- 不把 `.env`、Owner 密码、SMTP 密码、DeepSeek Key、Cookie、验证码、恢复口令或私人简历提交到 Git。
- 平台 DeepSeek Key只存在于服务器 Secret 管理或部署环境；普通用户页面、导出、日志和业务快照中不得出现。
- 生产测试只使用专用验收账户和合成简历。

## 数据与租户

- 生产数据库使用 PostgreSQL 和 Alembic。
- 所有候选人私有表按 `user_id` 查询；跨租户读取返回不泄露资源存在性的 404/拒绝。
- v0.2 数据迁移必须先备份、后迁移、再读回；失败保持旧服务和恢复点。
- 删除账户只删除该用户数据，不影响其他用户或公共岗位。

## 自动岗位发现

- 刷新周期固定为 6 小时；不得改成人工保活或其他周期。
- Scheduler 只排队到期用户；Worker 处理队列。运行不依赖活动 Agent 或聊天。
- 单一来源失败不得拖垮其他来源；页面区分“没有岗位”和“来源失败”。
- 未经授权不得增加 SEEK、LinkedIn、Indeed 抓取或绕过限制。

## 验收

- 本地：`python -m pytest -q`、`python tools/ui_contract.py`、`python tools/restart_readback.py`、`python tools/e2e_local.py`。
- 生产：`deploy/acceptance.sh`，覆盖 HTTPS、真实 SMTP、平台 DeepSeek、两账户隔离、上传简历、自动推荐、关键筛选、持久化、重启读回和备份验证。
- `NOT_RUN / BLOCKED / UNKNOWN` 永远不能折算为 PASS。
- 同一修复两次仍失败，回滚并定位根因，不降低 Acceptance。
