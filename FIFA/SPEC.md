# FIFA 日报规格（一页）

## 要解决什么问题

Owner 想每天看一份可信的足球研究：每场比赛的概率和不确定区间、模型到底准不准。必须让人一眼知道数据是不是新的、旧了要明说。

## 给谁用

Owner 一人，手机或电脑打开网页读。

## 明确不做

- 不下注、不点赔率、不改投注单、不绕过任何访问控制（`AGENTS.md`）。
- 不用禁止自动访问或要注册的来源（football-data.co.uk、The Odds API、TAB 官网、FixtureDownload 等，依据见 `daily-research/README.md`「数据源与合规」）。
- 没有合法盘口源时不算期望值、凯利比例和投注金额。
- 不用付费服务、不注册账号；运行时不调用任何 AI。
- 旧的 TAB 研究流水线不参与日报。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 离线单元与端到端 | `cd FIFA/daily-research && python -m unittest discover -s tests -t .`（2026-09-30 实测 25 tests OK） |
| 部署件语法正确 | `.github/workflows/fifa-daily-report.yml` 的三步：`bash -n FIFA/deploy/vps/*.sh`、`docker compose -f FIFA/deploy/vps/docker-compose.yml config -q`、`nginx -t` |
| 网站可达 | `curl -sI https://fifa.linzezhang.com/` 返回 200（2026-09-30 实测 200） |
| 数据新鲜（≤30 小时） | 页面第一屏「今天有没有新报告」；Gatus 端点 `fifa_fifa-daily-freshness`；服务器 `systemctl list-timers 'fifa-daily*'` |
| 双平面文档未漂移 | `python3 FIFA/machine/tools/check_dual_plane_ci.py --root . --projects FIFA --require-projects` |

## 已知坑

- 失败时页面照样发布并在第一屏写明原因，旧报告标「旧的」；unit 记为失败。看 `journalctl -u fifa-daily -n 80`。
- 欧冠淘汰赛（2027 年 2 月起）页面尚未接入，需补 `WIKI_CL_KO_PAGE` 解析。
- 澳超 2026-27 赛季暂无合规完整数据源。
- 旧地址 `home.linzezhang.com/fifa` 由 nginx 301 到新域名（`deploy/vps/nginx.conf`）。
- 治理类 YAML 仍引用 `FIFA/README.md` 作证据路径，文件在原位，内容已换成新版。
