# Equity Foresight Signal Agent Contract

- Stable ID：`equity-foresight-signal`；Version：`0.0.0.1`；version scheme：`numeric-quad`。
- Canonical project：`Signal-Lattice/Stock_Skill/equity-foresight-signal-skill/`；canonical Skill：`task-pack/skill_draft/equity-foresight-signal/`。
- 分发：`SOURCE_ONLY`；禁止本机 Skill 安装、自动交易、独立服务/数据库或 Agent/LLM Runtime。
- v0.0.0.1 能力上限是 `SHADOW_ONLY`；Outcome 为 `NOT_PROVEN`，不得转换为 Alpha、荐股或 Decision Support 声明。
- Codex 仅原样落库、运行验证、commit/push/PR/merge/备份；任何代码或阈值差异都使既有验收失效并交回 ChatGPT。
- 冲突顺序：当前线程最新明确要求 → 用户基础设施事实 → 目标仓规则 → 本包 Canonical Facts/Acceptance → 官方文档 → 锁定第三方 → 历史材料 → 推断。

## 本机零足迹硬约束

- 只允许远程宿主嵌入；不得在 macOS 安装、启动、注册或调度 Runtime。
- 全生命周期禁止 `launchd`、LaunchAgent、LaunchDaemon、登录项、后台 helper 和本机常驻进程。
- 不得写入 `$HOME`、`~/Library`、XDG cache/config/state/data、系统临时持久目录、SQLite、日志或模型缓存。
- 显式调用完成后，本机持久文件数、持久字节数、常驻后台进程数必须全部为 0；调用期间临时 CPU/RAM 不属于“持久占用”。
- Codex 落库后，Owner 可删除下载 ZIP；生产运行仅发生在既有远程宿主，不依赖 Owner 的 Mac 在线。
