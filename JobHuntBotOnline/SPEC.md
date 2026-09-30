# JobHuntBot Online 规格（一页）

## 要解决什么问题

求职者（首要是金融与法律方向）要在大量公开岗位里找到自己真正够格的，并为每个岗位准备贴合的材料。系统自动聚合、先判硬资格再排序，并生成只含本人事实的定制 DOCX。

## 给谁用

多个候选人，各自注册（或由 Owner 入口进入）；数据按 `user_id` 严格隔离，跨租户返回 404。

## 明确不做

- 不自动提交申请；不保存第三方招聘平台账号。
- 不抓取 SEEK、LinkedIn、Indeed，不绕过任何限制（`AGENTS.md`）。
- 不编造简历里没有的事实。
- 邮件：不调低生产频率限制（同一收件人至少间隔 30 分钟、24 小时最多 3 封），不自动重试真实邮件验收。
- 核心流程不依赖任何 AI 调用；DeepSeek 仅可选复核。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 业务主链路（注册、多份简历、岗位聚合、硬资格过滤、按岗位选简历、导出 DOCX） | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests/test_business_e2e.py` |
| 全部测试 | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q`（CI：`jobhunt-ci.yml`） |
| 发布清单与密钥边界 | `python tools/verify_taskpack.py` |
| 网站活着 | `curl -fsS https://jobhunt.linzezhang.com/healthz`（`status=ok`）与 `.../readyz`（`status=ready`） |
| 6 小时聚合在跑 | 服务器上 `docker compose logs --since 13h worker | grep 'completed discovery run'` 有输出；`discovery_runs` 见 README 所引清单第 8 步 |
| 刷新周期固定 | `DISCOVERY_REFRESH_HOURS=6`，由配置层强制（`app/config.py`） |

## 已知坑

- 真实邮件注册从未在生产走通；注册依赖 SMTP 凭据，缺凭据时保持 `ALLOW_REGISTRATION=false`。
- 冷路由首个请求偶发 502/503（2026-08-11 实测）；`docker-compose.yml` 有 `web-canary` 热备，线上是否启用未核实。
- 本地全量 pytest 在缺 `_cffi_backend` 的环境里 `test_acceptance_tools.py::test_mail_transport_probe_ignores_generated_evidence` 会失败（2026-09-30 沙箱实测，环境问题）；CI 用 Python 3.13 + Postgres 服务。
- VPS-3 上有已退出的旧 v0.2 容器，不属于当前运行时，清理待 Owner 决定。
- 增删项目文件要重写 `deploy/MANIFEST.json`（`tools/verify_taskpack.py --write-manifest`）。
