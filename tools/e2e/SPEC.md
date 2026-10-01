# tools/e2e 规格（一页）

## 要解决什么问题

单元测试绿、容器活着，不等于用户打开网页真能用。需要一个每天自动、从公网视角、像用户一样把每个项目走一遍的检查，并且在数据过期或页面出现 `undefined`、`Traceback` 之类问题时明确报不通过。

## 给谁用

主线和项目 owner：看每日报告知道哪个项目的公网页面坏了；项目开发者用它当「完成」的外部证据。

## 明确不做

- 不登录、不用任何凭据，只检查公开页面。
- 不改旅程文件格式（格式由 Governance 仓定义，本执行器只实现）。
- 不碰别的项目的代码，不写入被检查的站点。
- 不依赖 AI 或 agent 运行；不用付费服务；不在本机常驻（跑在 VPS-3 的 systemd 定时器 + Docker 里）。
- 「有项目不通过」不算执行器故障（退出码 1 与 2 区分）。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 执行器逻辑 | `cd tools/e2e && python -m pytest -q tests`（离线夹具页，2026-09-30 实测 24 passed） |
| 镜像能构建且依赖齐 | `docker build -t linze-e2e:ci tools/e2e && docker run --rm --entrypoint python linze-e2e:ci -c "import run, yaml, playwright; print('ok', run.VERSION)"`（即 `.github/workflows/e2e-runner.yml` 的 `image-build`） |
| 部署件一致 | 服务器上 `bash tools/e2e/deploy/install.sh --check` 退出码 0 |
| 每天在跑 | 服务器上 `linze-e2e status` 的最近一次结果不早于约 25 小时；`systemctl list-timers linze-e2e.timer` 有下次触发 |
| 退出码约定 | 0 全过、1 有不通过、2 执行器自身出错（`run.py` 文件头） |

## 已知坑

- 新增一个项目的公网旅程由主线写 `旅程/*.yaml`，开发任务不要改这些文件。
- 容器一核一 GB 限制、总时限 20 分钟（`TimeoutStartSec=20min`）；旅程太多会超时，超时算退出码 2。
- axe-core 版本和 sha256 固定在 `run.py` 与 `Dockerfile` 两处，必须同步改。
- Playwright 基础镜像版本必须与 `requirements.txt` 里的 playwright 版本一致。
- 被检查的站点本身没上线（例如 ADP 域名还指向旧 Cloudflare）时，对应旅程会不通过，这是真实结果，不是执行器问题。
