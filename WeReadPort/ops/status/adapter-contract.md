# LinzeStatus 状态适配契约

`weread-port-ops reconcile` 每次即时检查生产站点四个独立机器 Oracle：

- `/healthz`：请求入口存活；
- `/readyz`：静态资源真实可读，业务线 ID 唯一、依赖存在且依赖图无环；
- `/api/status`：脱敏运行合同、零用户持久化边界和七条业务基线纵向切片；
- `/api/version`：应用版本、腾讯官方 WeRead Skill 版本和业务治理 schema。

## 七条业务线

适配器要求精确存在：`public-trust`、`weread-direct-export`、`local-import`、`normalize-export`、`chatgpt-handoff`、`release-supply-chain`、`operations-recovery`。缺行、重复、未知行、无效依赖图、schema 漂移或任一 `BLOCKED` 均 fail-closed 为 `degraded`；`NOT_VERIFIED` 与 `EXTERNAL` 保持原义，不转写为已通过。

只有四个机器 Oracle 全部通过，且业务合同有效、无阻塞线时，公开项目状态才是 `operational`。存活但未就绪、版本漂移、治理合同异常或业务线阻塞均为 `degraded`。检查不携带微信读书密钥，不调用用户上游数据，也不读取用户上传文件。

## 最小公开数据

状态文件只包含项目名、公开 URL、版本、HTTP 状态、延迟、错误代码、脱敏运维摘要，以及每条业务线的 `id/state/reasonCode/evidenceLevel`。不得包含密钥、书名、文件名、笔记、用户 ID、内部项目 ID、环境变量、私有路径或原始错误正文。

对象中的 `project` 字段沿用 LinzeStatus 收集器已消费的字段：`name`、`url`、`parts`、`host`、`db`、`store`、`deploy`、`backup`、`agent`、`notify`。安装器只增加一个有界文件加载器并扩展既有 `PROJECTS` 循环，不执行外部代码，不让本项目成为状态收集器关键依赖。适配文件缺失、过期或无效时只忽略本项目，其他状态采集继续运行。
