# ADP 规格（一页）

## 要解决什么问题

论文和公开来源太多，owner 没时间逐篇筛。ADP 每天自动抓取、排序，挑出值得学的内容，产出中文讲解、复习卡片与收益判断，放在一个网页里看。证据优先：每条结论要能指到来源，拿不到来源就不写。

## 给谁用

项目 owner 一人，每天读一次（owner 阅读面见 `用户中心/`）。没有多用户设计。

## 明确不做

- 不自动发真实邮件（需 SMTP 凭据，已停）；`ADP_ALLOW_SMTP_SEND` 只接受 `UNSET` 或 false-like。
- 不进入 S3/DAILY_OPERATION 持久日常运行（缺持久授权文件）。
- 语音、分镜、视频命令与手工 Release 媒体交付只作历史保留，不作验收目标。
- 自托管运行时不需要任何凭据或账号（`deploy/selfhost/adp.env` 头部说明）。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 自托管运行时与部署件正确 | `PYTHONPATH=arxiv-daily-push/src python3 -m pytest -q -p no:cacheprovider arxiv-daily-push/tests/test_selfhost_migration.py arxiv-daily-push/tests/test_selfhost_deploy_files.py arxiv-daily-push/tests/test_selfhost_node.py arxiv-daily-push/tests/test_arxiv_fetch_retry.py`（2026-09-30 实测 38 passed） |
| 镜像能以生产同款限制起来 | `.github/workflows/adp-selfhost.yml` 的 docker 步骤（非 root、只读根、256m） |
| 进程活着 | `curl -fsS https://adp.linzezhang.com/healthz`，响应体含 `"service":"adp"`（域名切换后才成立） |
| 数据新鲜（≤30 小时且入库 arXiv 论文数 >0） | `curl -fsS 'https://adp.linzezhang.com/healthz?strict=1'` 返回 200；503 即过期 |
| 双平面文档未漂移 | `python3 arxiv-daily-push/machine/tools/check_dual_plane_ci.py --root . --projects arxiv-daily-push --require-projects` |
| 历史合同不被误启用 | 仓根运行 `tools/verify_daily_operation_readiness.py --root .` 与 `tools/verify_daily_operation_enablement_preflight.py --root .`，退出码必须为 2 |

## 已知坑

- 域名 `adp.linzezhang.com` 截至 2026-09-30 仍指向旧 Cloudflare（`/healthz` 返回 404）；上面两条线上判据在切换前会失败，这不是代码问题。
- 全量 `unittest` 要求 Python 3.12；在 Python 3.11 沙箱实测有 5 个 failure、15 个 error（2026-09-30，与本次文档整理无关，未在 3.12 复核）。
- `README.md` 里的一批措辞被 `tests/test_user_center_candidate_pool.py` 钉住，改 README 前先跑该测试。
- 自托管 Node 运行时要求 Node >= 22.13（`node:sqlite`）。
- 用户中心页面由双平面/用户中心同步门管：增删改板块或数据源必须同步 `用户中心/` 与对应两个测试，见仓根 `AGENTS.md`。
