# FIFA 足球研究日报

一句话：每天自动生成中文足球研究日报（英超、西甲、德甲、意甲、法甲、欧冠未来 14 天的胜平负概率、预期进球、模型成绩单），**只研究，不下注**。规格见 [SPEC.md](./SPEC.md)；代码与细节见 [daily-research/README.md](./daily-research/README.md)。

## 线上地址与是否真在跑

- 地址：`https://fifa.linzezhang.com/`（VPS-3 上 nginx 容器只读挂载发布目录，Traefik 按域名路由）。2026-09-30 实测 `curl -sI` 返回 200。
- 怎么判断真在跑：页面第一屏写着报告日期和「今天有没有新报告」；服务器上 `systemctl list-timers 'fifa-daily*'`。
- 数据最迟多久该更新一次：**30 小时**。`fifa-daily.timer` 每天两次，UTC 20:37 与 08:47；超过 30 小时没更新，页面浏览器端自己亮红条，Gatus 的 `fifa-daily-freshness` 心跳也判红（`deploy/vps/fifa-daily.env`、`daily-research/README.md`）。
- 代码更新：`fifa-daily-pull.timer` 每 10 分钟看一眼 `main`，只有 `FIFA/daily-research` 变了才取新代码、先跑离线测试，通过才切换。

## 数据放哪

服务器 `/var/lib/fifa-daily/`（`releases/<时间戳>/` 是完整站点，`current` 指向线上，留最近 4 份；预测账本、运行记录随站点版本化）；代码发布在 `/opt/fifa-daily/`（留最近 2 份）。本仓只放代码，备份类数据见仓根 `WHERE_IS_PROJECT_DATA.md`。

## 怎么部署 / 回滚

- 部署：合入 `main` 后服务器自动拉取（见上）。首次安装 / 比对：在服务器上 `sudo bash FIFA/deploy/vps/install.sh [--check]`（安装件在 `FIFA/deploy/vps/`）。
- 回滚：在 `main` 上 revert 提交，10 分钟内自动拉取新的旧版代码；生成失败或校验不过会丢弃新目录，线上留在上一份好版本（`fifa-daily-run.sh`，`daily-research/README.md`「失败时」）。

## 需登录 / 需凭据而停掉的功能

- 盘口对比与期望值：需合规盘口源，目前没有，页面如实显示「暂无合法盘口源」，已停。
- TAB 官网相关的旧流水线（`tab-research-pipeline/`）：TAB 官网拒绝受控访问（`AGENTS.md`「Current Access Policy」），已停，保持失败关闭，不参与日报。
- 澳超：暂无合规当季数据源，未接入。

## 本地测试

```bash
cd FIFA/daily-research
python3 -m venv /tmp/venv-fifa && /tmp/venv-fifa/bin/pip install -r requirements.txt
/tmp/venv-fifa/bin/python -m unittest discover -s tests -t .   # 离线，合成数据，2026-09-30 实测 25 tests OK
```

CI：`.github/workflows/fifa-daily-report.yml`（PR 上跑离线测试与部署件语法检查）。历史长版说明、变更记录在 [文档/归档/](./文档/归档/)。
