# Canonical Facts

- 产品：股势前瞻 / Equity Foresight Signal；Stable ID：`equity-foresight-signal`；Version：`0.0.0.1`。
- 目标仓：`LinzeColin/MetaDatabase@522b8bee22b572a0bbe15c9cf0b4aea513594805`。
- 项目路径：`Stock_Skill/equity-foresight-signal-skill/`；Skill 路径：`task-pack/skill_draft/equity-foresight-signal/`。
- 形态：`SOURCE_ONLY`、嵌入式、无状态、确定性节点；不是独立系统、数据库、服务、前端或执行器。
- v0.0.0.1 只授权 `RESEARCH` 与 `SHADOW`；能力上限 `SHADOW_ONLY`；Outcome `OUTCOME_NOT_PROVEN`。
- Runtime、离线训练、评测、Candidate/LKG 比较、状态和恢复计划：0 Agent、0 LLM Token、0 网络、0 第三方 Python 依赖。
- 宿主负责数据获取、调度、持久化、Private-Database/R2/D1/OCI、状态传输、渲染和显式 LKG 激活。
- 旧 SPY/VIX 5D/20D/60D 负向基线是不可删除回归事实。
- `ENGINEERING_PASS` 不等于 `OUTCOME_PROVEN`。

- 部署画像：`REMOTE_HOST_EMBEDDED_ONLY`；禁止 macOS Runtime、`launchd` 和本机安装。
- 部署与域名：无独立域名、无专属部署节点；仅由既有远程 Linux 宿主进程按需嵌入调用，状态传输归宿主所有。
- 显式调用结束后，Owner 本机持久文件、持久字节、缓存、日志、状态与常驻进程均为 0；执行瞬间临时 CPU/RAM 不伪称为 0。

- 目标 Commit 是公开观察点；落库权威前置条件是所有将触碰文件的精确 Hash、路径缺失条件和工作树清洁状态。若 HEAD 仅因无关路径前移而相关内容完全一致，可继续；任何相关字节漂移立即 fail closed。

- 状态展示目标：`LinzeColin/LinzeHomeHub@fccd7eeeb224107d471fa6b6b54c801135fe1ec3`（公开观察点）；只修改既有 collector/web 两个文件，状态事实位于 OVH `/srv/linze/apps/status/data/efs_business_baseline.json`，复用既有 15 分钟 cron。
- Status 适配不新增 daemon、数据库、域名、Agent、LLM 或 macOS 运行项；全中文展示字段与机器字段由同一矩阵 Hash 绑定。
