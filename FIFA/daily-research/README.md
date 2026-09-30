# FIFA 足球研究日报（当前运行中的部分）

**只研究，不下注。** 每天自动生成一份中文研究日报并发布为网页：
`https://linzecolin.github.io/MetaDatabase/fifa/`

## 它做什么
- 覆盖英超、西甲、德甲、意甲、法甲和欧冠；未来 14 天每场比赛给出：胜/平/负概率及 10%–90% 不确定区间、预期进球、大于 2.5 球与双方进球概率、最可能比分、风险提示。
- 第一屏写明：数据截至何时、今天有没有新报告、没有的话为什么。失败时显示旧报告并标明「旧的」，不会冒充新的。
- 「模型成绩单」：滚动回测（只用截止日之前的数据预测之后的比赛）+ 每日发出的赛前预测被冻结、赛后自动打分。
- 「盘口对比」：目前如实显示「暂无合法盘口源」，不算期望值、凯利比例和投注金额（原因见页面的数据源审查表）。

## 调度与发布（零 Mac、零 agent）
- 工作流 `.github/workflows/fifa-daily-report.yml`：每天两次（UTC 20:37 与 08:47，非整点；第二次是兜底），幂等。
- 产物发布到 `gh-pages` 分支的 `fifa/` 目录（GitHub Pages 从该分支提供网页）。状态、预测账本、运行记录都存在该目录的 `data/` 里，所以每次运行都从上次状态继续；缺的天数由下一次运行自动覆盖（不补发当天的赛前预测，那是事后诸葛）。
- 页面内置过期提醒：生成超过 30 小时没更新，浏览器端会自己亮红条——定时任务整个没跑时也看得见。

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
