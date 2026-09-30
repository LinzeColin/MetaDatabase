# FIFA 足球研究日报（当前运行中的部分）

**只研究，不下注。** 每天自动生成一份中文研究日报并发布为网页：
`https://fifa.linzezhang.com/`

## 它做什么
- 覆盖英超、西甲、德甲、意甲、法甲和欧冠；未来 14 天每场比赛给出：胜/平/负概率及 10%–90% 不确定区间、预期进球、大于 2.5 球与双方进球概率、最可能比分、风险提示。
- 第一屏写明：数据截至何时、今天有没有新报告、没有的话为什么。失败时显示旧报告并标明「旧的」，不会冒充新的。
- 「模型成绩单」：滚动回测（只用截止日之前的数据预测之后的比赛）+ 每日发出的赛前预测被冻结、赛后自动打分。
- 「盘口对比」：目前如实显示「暂无合法盘口源」，不算期望值、凯利比例和投注金额（原因见页面的数据源审查表）。

## 调度与发布（云服务器 VPS-3，零 Mac、零 agent；GitHub 只放代码）
- **定时**：服务器上的 systemd timer `fifa-daily.timer` 每天两次（UTC 20:37 与 08:47，加几分钟随机抖动；第二次是兜底，错过的点开机后补跑），跑 `fifa-daily.service`：复制线上站点目录 -> 用服务器的 Python 生成 -> 校验 -> 原子切换发布。同一天重复运行是幂等的。
- **代码更新**：`fifa-daily-pull.timer` 每 10 分钟看一眼公开仓 main，只有本目录 `FIFA/daily-research` 的内容变了才取新代码、跑离线测试，通过才切换并立刻重出一份报告；不通过则保留旧代码（无令牌，匿名只读拉取）。
- **对外**：一个极小的 nginx 容器 `fifa-daily-web` 只读挂载发布目录，经 Traefik 路由 `fifa.linzezhang.com`（自己的域名，站点在根路径 `/`；证书与门户同为 letsencrypt）。页面全部用相对链接；`/data/`（账本、缓存）不对外。旧地址 `home.linzezhang.com/fifa[/…]` 由 nginx 301 到新域名。
- **状态与产物**：都在服务器 `/var/lib/fifa-daily/`（`releases/<时间戳>/` 是完整站点，`current` 指向线上这份，留最近 4 份；预测账本、运行记录、回测与比赛缓存在站点的 `data/` 里，随站点一起版本化，所以每次都从上次状态继续；缺的天数由下一次运行自动覆盖，不补发当天的赛前预测，那是事后诸葛）。代码在 `/opt/fifa-daily/`。
- **失败时**：生成器判定「今天没出新报告」时，页面照样发布并在第一屏如实写明原因、旧报告标明「旧的」，unit 记为失败；生成器崩溃或校验不过则丢弃新目录、线上保持旧页面，unit 记为失败。失败会写 journal（`journalctl -t fifa-daily -p err`），并向 Gatus 推失败心跳。资源限额：`MemoryMax=768M`、`CPUQuota=200%`、超时 20 分钟，以无特权用户 `fifa-daily` 在沙箱里运行。
- 页面内置过期提醒：生成超过 30 小时没更新，浏览器端会自己亮红条；Gatus 面板另有「fifa-daily-freshness」心跳端点，30 小时没有心跳也会判红。
- 部署件（脚本、unit、nginx、compose、安装脚本）在 `../deploy/vps/`，服务器上 `sudo bash install.sh` 安装（`--check` 比对是否与仓库一致；不自我更新）。

## 怎么看它活着
- 对外地址：`https://fifa.linzezhang.com/`（第一屏写着报告日期和「今天有没有新报告」）。
- 服务器上：`systemctl status fifa-daily.timer fifa-daily.service`（每日生成）、`systemctl status fifa-daily-pull.timer`（代码更新）；下一次什么时候跑：`systemctl list-timers 'fifa-daily*'`；一眼看全：`sudo fifa-daily-run.sh status`。

## 本地运行
```bash
cd FIFA/daily-research
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -t .      # 离线测试，合成数据
.venv/bin/python -m fifa_daily run --site /tmp/site/fifa  # 联网，约 1 分钟
```

## 代码地图
| 文件 | 作用 |
|---|---|
| `fifa_daily/sources.py` | 抓取与解析（openfootball、Wikipedia） |
| `fifa_daily/teams.py` | 球队名归一与中文名 |
| `fifa_daily/model.py` | 泊松进球模型（时间衰减 + 岭惩罚 + 低比分修正 + 不确定区间） |
| `fifa_daily/backtest.py` / `ledger.py` | 回测 / 预测账本 |
| `fifa_daily/build.py` | 组装日报、风险提示、数据源审查表 |
| `fifa_daily/render.py` | 单文件网页 |
| `fifa_daily/run.py` | 一次运行：抓取→出报告→写站点→失败时如实记录 |

## 数据源与合规（2026-09-30 实测，详见页面）
采用：openfootball（CC0）、Wikipedia 官方 API（CC BY-SA 4.0，页面署名）。
不用：football-data.co.uk（禁止自动化访问，这是唯一的免费赔率源）、The Odds API（要注册）、TAB 官网（被判拒绝 AI 受控访问，失败关闭）、FixtureDownload（禁止转存）、TheSportsDB 免费档（数据不全）、ClubElo（接口停用）。

## 已知缺口（下一步）
- 澳超：2026-27 赛季 10-16 开赛，暂无合规且完整的当季数据源，开季后再评估。
- 欧冠淘汰赛（2027 年 2 月起）：Wikipedia 另有淘汰赛页面，尚未接入；联赛阶段结束后需补 `WIKI_CL_KO_PAGE` 的解析。
- 盘口对比：出现合法免费且条款允许自动访问的盘口源后，在 `build.py` 的 `market` 字段接入。

## 硬边界
不下注、不点赔率、不改投注单、不绕过任何访问控制；零付费；不注册账号。旧的 TAB 研究流水线（`../tab-research-pipeline/`）保持原样，不参与日报。
