# 手把手操作指南

Owner 批准最终交付后：下载唯一 ZIP；不改名、不重压缩；一次性给 Codex；粘贴 `PURSUING_GOAL.txt`；要求只执行 `CODEX_LANDING_INSTRUCTIONS.md`。Codex 报错时把完整日志交回 ChatGPT，不允许其自行修复。只以 MetaDatabase registry validator、项目 Oracle、commit/merge/backup receipts 为落库完成证据。该版本只进入 `SOURCE_ONLY / SHADOW_ONLY`，不安装本机、不接券商、不产生交易指令。

## 上线后本机零占用

1. 不在 Mac 上解压后安装、运行或注册 Skill；只把唯一 ZIP 一次性提供给 Codex。
2. Codex 必须在目标仓/远程开发环境落库并运行冻结 Oracle，不得创建 `launchd`、LaunchAgent、LaunchDaemon 或登录项。
3. 收到真实 merge、Registry validator、Oracle 和备份回执后，删除 Mac `Downloads` 中的 ZIP 和任何手动解压副本。
4. 上线运行仅由既有远程宿主按需调用；Owner 的 Mac 可关机，不保留缓存、日志、数据库、后台进程或调度项。
5. 在 Mac 的“系统设置 → 通用 → 登录项”以及 `~/Library/LaunchAgents`、`/Library/LaunchAgents`、`/Library/LaunchDaemons` 不应出现本 Skill 条目；发现任何条目即视为 FAIL 并删除/回滚。

## Status 业务矩阵

1. Codex 在独立的 `LinzeHomeHub` 工作树运行 `status_integration/apply_status_integration.py preflight/apply/verify`，再运行该仓现有 `npm run validate`；不得手改。
2. 远程宿主调用 `build_host_status_payload()` 后，以一次性 `write_status_fact.py` 原子写入 `/srv/linze/apps/status/data/efs_business_baseline.json`。
3. 既有 LinzeStatus cron 将其合并进 `status/data/snapshot.json`；保留现有“总览 / 运行 / 成本 / GitHub”四个一级入口，在“运行”页内嵌“业务基线治理”区块，并把无效、缺失或阻塞状态接入既有健康行动清单。最低展示：业务线、阶段、阶段环节、状态、上下游、耦合控制、阻塞原因、下一动作和依赖拓扑。
4. 缺少状态文件时显示“尚未接入”，哈希或结构错误时显示“状态事实无效”并拒绝展示；不得影响其他状态采集。
5. 复用既有 OVH cron、静态页面和 host-direct rsync；不新增 daemon、数据库、域名、Agent、LLM 或 macOS 运行项。
