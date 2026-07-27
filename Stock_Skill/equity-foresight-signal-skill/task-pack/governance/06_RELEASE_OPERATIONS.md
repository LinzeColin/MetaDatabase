# 发布与运维

Codex 只按 `CODEX_LANDING_INSTRUCTIONS.md` 原样落库。任务包绑定目标基线 `522b8bee22b572a0bbe15c9cf0b4aea513594805` 的 claim 文件和 Registry 哈希；目标已变化时只回报冲突，不做猜测合并。

Skill 不单独部署。宿主直接调用 API/CLI，负责数据、状态、Private-Database/R2/D1/OCI 和展示。失败时恢复预修改文件并删除新项目目录。生产只允许既有远程宿主嵌入；禁止在 macOS 安装/运行，禁止 `launchd`、本机常驻进程和本机持久缓存/日志/数据库/状态。

落库后从 MetaDatabase 仓根运行真实 `Stock_Skill/scripts/validate_registry.py`，再运行项目 Oracle。无真实时间 soak；持续验证不阻塞 source-only 发布。

合并与远程备份回执确认后，Owner 删除本机下载 ZIP 和解压副本。若 macOS 的登录项、LaunchAgents 或 LaunchDaemons 出现任何本 Skill 条目，立即判定 FAIL、删除条目并回滚；不得把 Mac 作为控制面、调度、健康、自愈、备份或恢复节点。

目标 HEAD 与公开观察 Commit 不同并不单独构成失败；`apply_to_target.py` 只在全部触碰文件 Hash、目标路径缺失和相关工作树清洁均成立时继续，并在回执中明确记录 HEAD 漂移。这样避免无关仓库提交造成假阻塞，同时不允许相关文件静默漂移。

状态页面目标为 `LinzeColin/LinzeHomeHub@fccd7eeeb224107d471fa6b6b54c801135fe1ec3` 的公开观察点。Codex 在真实工作树只按唯一锚点和相关路径 clean 条件应用补丁，运行 `npm run validate` 后复用现有 host-direct rsync；不得新建服务或版本号。
