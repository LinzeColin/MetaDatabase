# JobHuntBot Online Agent Rules

先读 `README.md`（做什么、怎么跑、数据在哪、上线核验清单）。以下是违反有代价的规则。

## 完成的判据

线上一个真实候选人账号每 6 小时收到新的合格岗位，并能导出岗位定制 DOCX。
测试绿、`/readyz` 200、容器存活只是前提。本地判据是 `tests/test_business_e2e.py`。

## 邮件安全（Owner 硬边界）

- 邮件只走任意标准 SMTP；NitroSend 已删除，不得重新引入。缺 SMTP 时保持 `ALLOW_REGISTRATION=false`。
- 生产按收件人至少间隔 30 分钟、24 小时最多 3 封，删除重注册不重置；禁止调低、禁止自动重试真实邮件验收。
- `deploy/acceptance.sh` 会发真实邮件，只在 Owner 明确同意、`RUN_REAL_EMAIL_ACCEPTANCE=true` 且使用全新 run ID 时运行。

## Secret 与隐私

- `.env`、`secrets/*.txt`、`OWNER_LOGIN.txt`、DeepSeek/SMTP 凭据、私人简历不进 Git。
- 平台 DeepSeek Key 只在服务器 `.env`；页面、导出、日志中不得出现。生产测试只用专用测试账户和合成简历。

## 数据与租户

- 生产数据库是 PostgreSQL + Alembic；候选人私有表一律按 `user_id` 查询，跨租户返回 404。
- 删除账户只删该用户数据。

## 岗位发现

- 刷新周期固定 6 小时（`DISCOVERY_REFRESH_HOURS=6`，配置层强制）。成功或失败都把下一轮排在 6 小时后。
- `scheduler` 容器每分钟只排队到期用户，`worker` 容器处理队列；不依赖任何 Agent 或聊天在线。
- 单一来源失败不拖垮其他来源。未经授权不得抓取 SEEK、LinkedIn、Indeed 或绕过限制。

## 改动后

- `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q`（虚拟环境放项目目录外）。
- 增删文件后运行 `python tools/verify_taskpack.py --write-manifest`，否则发布前检查报 manifest drift。
