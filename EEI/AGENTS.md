# AGENTS.md（EEI）

只写「违反有代价」的规则。现状看 `HANDOFF.md`，怎么跑看 `README.md`，旧规则全文在 `文档/归档/AGENTS_旧版.md`。仓根 `AGENTS.md` 的数据落地铁律同样适用。

## 数据与事实

- 证据、时间、金额、unknown、reported/derived/disputed/revoked 状态不得丢；金额只在同语义、同币种、同期间下聚合。
- 评分只用于研究排序，不是收益概率，不输出买卖结论；模型版本不可变、可回滚，双周校准不自动激活。
- fixture、合成、dry-run 数据不得当作真实事实展示。
- 不加登录，不买商业数据（Owner 决定，`.ramify/KERNEL.md`）。
- 公开仓：不提交 `.env`、密钥、`SEC_USER_AGENT`（含联系邮箱，只放 secret/环境变量）、原始数据。长期事实写私有仓 `Private-Database`（`scripts/sync_facts_to_private_db.py`）。

## 线上与服务器

- `EEI/apps/universe/` 合入 `main` 后约 10 分钟内自动上线（服务器拉取式部署），没有人工闸门：只走 PR，改完先本地验证。
- 改 `apps/universe/deploy/` 后，服务器要重跑 `install.sh` 并 `eei-pull-deploy.sh run eei-universe --force`，否则线上与仓库不一致。
- 不要从 `apps/cloudflare-public/` 运行 `wrangler deploy` 或 `scripts/deploy_cloud.sh`：其 `wrangler.jsonc` 仍声明 `eei.linzezhang.com` 自定义域名，可能把主站抢回 Cloudflare（推断，见 `HANDOFF.md` 问题 3）。
- Cloudflare D1 免费额度每天 500 万行读取且全账户共用，2026-09-30 已被读光并拖垮 EEI 与 ADP。禁止新增读 D1 的路径；nginx 对 `/v1/*` 的缓存（`apps/universe/deploy/site.conf.template`）不要去掉。
- 服务器采集容器（`docker-compose.ovh.yml`）与 Alpha 交易系统同机：保留 `mem_limit == memswap_limit` 与 `oom_score_adj: 500`，不碰 Alpha 的 unit、系统 postgresql、cloudflared；部署避开美股交易时段（周一至周五 UTC 13:30-20:00）。出处 `.ramify/KERNEL.md`。
- SEC 访问必须带联系邮箱的 `SEC_USER_AGENT`，`eei-watch` 保持约每分钟一次请求；不要放大频率（见 `docker-compose.ovh.yml` 注释）。

## 改仓库时

- 提交前跑 `make verify`。`EEI/` 下被跟踪文件（`apps/universe/` 除外）变了，`EEI validation` 会校验清洁室 ZIP、`manifest.txt`、`DIRECTORY_TREE.txt`、`CHECKSUMS.sha256`，按顺序重新生成，不要手改哈希：
  1. `git add` 显式路径（不要 `-A`）
  2. `make generate-clean-room-release`
  3. `make generate-release-artifacts`
- 改功能、模型/参数、关系/行业/公司范围、任务或风险验收时，要同步 `data/` 下对应 CSV 和 `文档/归档/` 里对应的目录文档；
  `make verify`（`validate_task_pack`、`validate_governance`）会校验它们。同步清单见 `文档/归档/CONTRIBUTING.md`。
- 改布局后，视觉基线以 CI（ubuntu 字体栈）为准：在分支上手动触发 `eei-visual-baseline.yml`，下载 artifact 覆盖 snapshots 再提交。出处 `文档/归档/HANDOFF_EEI.md`。
- `文档/00`–`06` 由 `machine/tools/render_human.py` 从 `machine/facts/` 渲染，手改会被 `dual-plane.yml` 判红；改事实源后重新渲染。
- `docs/governance/development_events.jsonl` 只追加，不重写历史。
- 根目录只留 `README.md`、`HANDOFF.md`、`AGENTS.md` 与构建必需文件；其它说明放 `文档/` 或 `docs/`，旧文档进 `文档/归档/` 并登记到那里的 README 表。
