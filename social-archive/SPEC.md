# Social Archive 规格（一页）

## 要解决什么问题

收藏分散在 B站、抖音、小红书、Reddit、Instagram、Chrome 书签里，平台一删就没了，换个工具又要重来。要一个自己的、私有的、免费的资料库：一键保存、可搜索，并在多处留下密文备份，让「存下来的东西不会丢」可被验证。

## 给谁用

Owner 本人，通过 Chrome 插件和资料库网页使用；国内平台的登录态只留在 Owner 的浏览器里。

## 明确不做

- 不用付费 API（`/health` 的 `paid_api_allowed` 为 false）；云端账单必须恒为 0：不用 R2 的 `InfrequentAccess` 存储类，不用整包下载判断对象是否存在（改用 `HeadObject`）。
- 国内平台 Cookie 不出 Owner 的浏览器；服务器上一个都不许有。
- 默认只归档 L0/L1/L3 三层，L2 关闭。
- 配置存在不等于已连接；没验证过的目的地不显示为已连接。
- 不把 OCI 当副本（2026-09-30 退役）；副本集合由 `SOCIAL_ARCHIVE_REPLICA_STORES` 配置决定。
- 不承诺文档里不存在的保存入口（没有安装插件时没有别的保存路径）。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 版本声明与真源一致 | `python scripts/check_the_stated_version_is_the_real_one.py`（README 第一行、AGENTS、CHANGELOG 最新一节都要等于 `VERSION`） |
| 仓库门面不引用不存在的界面词 | `python -m pytest -q tests/focused/test_the_front_door_does_not_promise_what_is_not_there.py` |
| 全量测试 | `cd social-archive && python -m pytest -q tests`（Python 3.12；2026-09-30 沙箱实测 2151 passed、18 failed） |
| 服务活着、后台在跑 | `curl -s https://social-archive-api.linzezhang.com/health`：`status` 为 `ok`，`worker.alive` 为 true |
| 备份与复制没停 | 同一个 `/health`：`backup.stale` 与 `replication.stale` 均为 `false`（备份阈值 30 小时、复制阈值 2 小时） |
| 部署后版本一致 | 同一个 `/health` 的 `worker.version_matches` 为 true |

## 已知坑

- 沙箱里有 18 项测试在未改动时就失败（2026-09-30 实测）：缺 `.venv/bin/python`、`node` 退出码 1、发布门 `final_verify` 当前为 FAIL、交接日期不得早于最后一次升版等，与本次文档整理无关，未逐项修复。
- 要求 Python 3.12；跑完测试会在 `social-archive/` 下生成 `bilibili/`、`douyin/` 目录并改写 `evidence/G5/ONE_VERSION_ONE_PACKAGE.json`，提交前要清掉。
- `README.md` 第一行 `# Social Archive v<版本>` 由 `scripts/bump_version.py` 改写并被版本检查读取，不能改格式；`CHANGELOG.md`、`HANDOFF.md` 被检查脚本和测试引用，所以留在根目录。
- 三个国内平台账号目前断开，只有 Owner 能重新授权（`HANDOFF.md` 第四节）。
- 数字（条数、磁盘占用）手抄必漂，一律从 `/health` 现读。
