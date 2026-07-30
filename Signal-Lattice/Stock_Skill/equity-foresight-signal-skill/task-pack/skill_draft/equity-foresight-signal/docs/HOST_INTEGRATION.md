# 宿主集成合同｜股势前瞻

## 最短链路

```text
宿主准备 Evidence Snapshot
→ prepare_bundle()
→ evaluate_prepared() / evaluate_suite()
→ ForecastSignalEnvelope
→ build_host_status_payload()
→ 宿主持久化、展示和状态传输
```

生产调用不得先让 Agent 阅读 `SKILL.md` 再推理。`SKILL.md` 只负责安装和治理，预测计算直接调用确定性 Python 函数。

## API

- `prepare_bundle(bundle)`：完整校验并形成不可变 Prepared Bundle。
- `evaluate_prepared(request, prepared)`：单周期推断。
- `prepare_suite({5: bundle5, 20: bundle20, 60: bundle60})`：冻结多周期套件。
- `evaluate_suite(requests, suite)`：分别输出各周期结果，不生成跨周期万能分数。
- `health_snapshot(bundle, as_of=...)`：无墙钟健康快照。
- `build_host_status_payload(as_of=..., bundle=..., outcome_report=..., promotion_decision=...)`：状态事实，不自行传输。
- `compare_candidate_to_lkg()`、`assess_candidate_promotion()`：只比较和判定资格，不执行晋级。
- `build_recovery_plan()`：只返回宿主执行计划，不修改状态。

## 数据与持久化

- Skill 不创建第二个权威数据库。
- 低延迟队列、游标、幂等和 Runtime Journal 由宿主现有 OVH/SQLite 层负责。
- 完成态结构化事实由宿主进入 Private-Database。
- 大文件和二进制制品进入 R2，Private-Database 只保存引用、Hash、版本和恢复事实。
- 状态由宿主发送到 `status.linzezhang.com`。

## 故障路径

- 数据缺失/过期/冲突：`ABSTAIN`，不猜测补齐。
- Bundle 或 Hash 失败：阻断发布，保留 LKG。
- Candidate 不兼容：拒绝原位刷新。
- LKG 过期或损坏：宿主从既有权威备份恢复，再以显式 `as_of` 运行健康检查。
- Outcome 失败：保持 `SHADOW_ONLY`，不中断后续非阻塞研究，也不开放 Decision Support。

## 部署形态

v0 是无状态库和 CLI，独立域名与专属部署节点均为 `N/A`；只允许既有远程 Linux/OVH 宿主进程按需嵌入。不需要 Docker 服务、systemd daemon、数据库迁移、Blue-Green 或 Canary。宿主如已有这些能力，只对宿主集成做可逆发布；不得为了方法论完整给本节点新建运行面。部署画像固定为远程宿主嵌入：禁止 macOS Runtime、`launchd`、LaunchAgent/LaunchDaemon、本机登录项、本机持久缓存/日志/数据库/状态与常驻进程。Owner 的 Mac 不参与生产调度、健康检查、自愈、备份、恢复或状态采集。

## 资源语义

“上线后不占用本机资源”在本合同中精确定义为：Owner 本机不承载生产执行；显式调用结束后本机持久文件、持久字节、缓存、日志、状态和常驻后台进程均为 0。任何程序在执行瞬间都会使用短暂 CPU/RAM，因此该瞬时资源不被伪报为 0。生产执行的短暂资源由既有远程宿主管理，且不创建本 Skill 专属 daemon。

## 业务基线纵向切片与 Status 矩阵

`build_host_status_payload()` 必须同时返回 `business_baseline_matrix`。该矩阵是宿主展示和持久化的最小白箱治理合同，不是新的控制面或数据库。

| 业务线 | 阶段 | 主要状态 | 上游/下游 | 耦合控制 |
|---|---|---|---|---|
| 证据与PIT输入 | S1 输入控制 | CONTROLLED / DEGRADED / BLOCKED | → 预测 | PIT、Universe、许可与 Hash 绑定 |
| 方向、幅度与时机预测 | S2 Shadow 推断 | SHADOW_READY / BLOCKED_BY_UPSTREAM | 输入 → Outcome | 模型集 Hash、周期隔离、ABSTAIN |
| 样本外结果与证伪 | S3 Outcome 验证 | VALIDATED / FAILED_SHADOW_ONLY / NOT_AVAILABLE | 预测 → 生命周期 | 报告 Hash、Null Model、禁止自动晋级 |
| Candidate、LKG与发布边界 | S4 生命周期治理 | HOST_APPROVAL_ELIGIBLE / LOCKED_SHADOW_ONLY | Outcome → Status | Candidate/LKG Hash、宿主审批、回滚 |
| 状态登记、展示与恢复事实 | S5 状态与恢复 | READY_FOR_HOST_TRANSPORT | 汇聚全部上游 | 矩阵 Hash、宿主传输、无自持久化 |

矩阵逐行包含机器字段与 `display_zh` 全中文展示字段，并包含 `stage`、`phase`、`status`、`depends_on`、`downstream`、`coupling_controls`、`blocking_reasons`、`next_action` 和证据 Hash；依赖图必须无环。宿主至少以矩阵表格形式登记到 `status.linzezhang.com`，可在其上扩展时间线或拓扑图，但不得修改事实语义。Skill 自身不联网、不写数据库、不创建守护进程。

## 既有 LinzeStatus 接入

任务包包含 `status_integration/`，精确修改 `LinzeHomeHub/status/collector/collect.py` 与 `status/web/index.html`：采集器只读宿主状态文件并校验外层/矩阵 Hash，页面增加“业务线”入口和五行矩阵。缺失或损坏状态事实不会阻断其他项目状态。远程宿主事实路径固定为 `/srv/linze/apps/status/data/efs_business_baseline.json`；复用既有每 15 分钟 cron，不创建新的调度、服务、数据库或域名。`write_status_fact.py` 在 macOS 上强制拒绝运行。
