# tools/e2e（公网端到端执行器）

一句话：交付流水线第 8 关——用无头 Chromium 在桌面、手机、暗色三种视口，把 `旅程/*.yaml` 里每个项目的公网页面按「用户怎么用」走一遍，并检查可访问性、禁用词和数据新鲜度，给出通过或不通过的报告。规格见 [SPEC.md](./SPEC.md)。

## 线上地址与是否真在跑

- 它本身没有对外网页；它检查的是各项目的公网地址（写在 `旅程/*.yaml` 的 `base_url`，当前有 ADP、Alpha、EEI、EEI宇宙、FIFA、JobHunt、Serenity、Signal-Lattice、状态页、门户 10 份旅程）。
- 怎么判断它真在跑：VPS-3 上 `linze-e2e status`（最近一次结果 `/var/lib/linze-e2e/status.json`、状态变化记录 `state-changes.log`、下次定时）；`systemctl list-timers linze-e2e.timer`。
- 数据最迟多久该更新一次：**每天一次**，悉尼时间 07:30 加最多 20 分钟随机延迟，错过的点开机后补跑（`deploy/linze-e2e.timer`：`OnCalendar=*-*-* 07:30:00 Australia/Sydney`、`RandomizedDelaySec=20min`、`Persistent=true`）。所以 `status.json` 超过约 25 小时没变就该查。每条旅程自己还可声明页面数据的最大年龄（例如 ADP 旅程 `max_age_hours: 36`）。

## 数据放哪

服务器 `/var/lib/linze-e2e/`：`runs/<时间戳>/{report.json, 报告.md, 截图}` 保留最近 14 份，`src/` 是从公开仓 `main` 稀疏拉取的 `tools/e2e`。不含任何密钥，只有公网地址。

## 怎么部署 / 回滚

- 部署：在服务器上以 root 运行 `deploy/install.sh`（装 `linze-e2e`、service、timer 并启用定时器）；`--check` 只比对服务器与仓库是否一致。脚本不会自我更新，改了本目录后要在服务器上重跑。
- 日常更新：`linze-e2e run` 会先从 `main` 拉 `tools/e2e`，内容变了才重建镜像，拉取失败则沿用本机已有镜像。
- 回滚：`main` 上 revert，再在服务器跑 `linze-e2e sync`；镜像只保留最新一份。

## 需登录 / 需凭据而停掉的功能

无。只访问公网页面，不登录、不需要任何凭据。

## 本地测试

```bash
pip install -r tools/e2e/requirements-dev.txt && playwright install chromium
cd tools/e2e && python -m pytest -q tests     # 离线，本地夹具页；2026-09-30 实测 24 passed
```

退出码：0 全部通过；1 有项目不通过（unit 不算故障）；2 执行器自身出错。CI：`.github/workflows/e2e-runner.yml`（离线测试 + 镜像构建）。旅程文件由主线维护，格式见 Governance 仓「交付流水线/旅程格式」。
