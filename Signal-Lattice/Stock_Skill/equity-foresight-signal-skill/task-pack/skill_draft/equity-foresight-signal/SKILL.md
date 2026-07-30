---
name: equity-foresight-signal
description: 将宿主提供的 point-in-time 股票、衍生品、资金代理、基本面和事件证据转换为可审计的上涨概率、涨跌幅分布、障碍触及时机、可靠性与拒绝预测结果；生产链路必须直接运行确定性代码，不得用 LLM 或 Agent 计算分数。
---

# 股势前瞻（Equity Foresight Signal）

## 身份与边界

- Stable ID：`equity-foresight-signal`
- 目标版本：`0.0.0.1`
- 分发形态：`SOURCE_ONLY`
- 目标位置：`MetaDatabase/Stock_Skill/equity-foresight-signal-skill/`
- 形态：被现有系统调用的股票预测节点 Skill，不是独立软件、数据库、前端、服务或交易系统。
- 本文件只用于安装、集成、治理和人工触发说明。生产预测必须直接调用 Python API 或 CLI，不得依赖 Agent 持续在线。

## 适用场景

用于以下请求：

1. 在明确 `as_of`、标的、市场日历、预测周期、标签和成本口径后，计算未来净正收益概率。
2. 同时输出历史基准概率、概率增量、P10/P50/P90 涨跌幅、上行/下行/到期未触及概率和时间窗口。
3. 对价格、基本面、事件、期权、期货、利率信用、资金代理和宏观状态使用独立 Evidence Expert，并保留来源和时间谱系。
4. 回放历史预测、验证概率校准、区间覆盖、时机质量、成本压力和模型漂移。
5. 数据、模型、Universe、许可证或证据不足时返回 `ABSTAIN`。

不用于：

- 保证收益、确定性荐股或精确日期承诺；
- 自动下单、仓位管理、借券或券商连接；
- 让 LLM 猜测缺失数据、权重或“主力资金”；
- 将工程测试冒充真实样本外 Alpha；
- 将 13F、COT、short volume 等不同延迟和经济含义的数据混成单一“主力资金”字段。

## 指标语义

主指标：

```text
EFS-H = 100 × 经样本外校准的 P(未来 H 个交易日净收益 > hurdle)
```

必须独立展示：

- `efs_score`：0–100 的绝对上涨概率分数；
- `baseline_prob`：同资产、同周期、同状态的冻结基准概率；
- `probability_lift`：相对基准的概率增量；
- `expected_move`：P10、P50、P90；
- `economic_edge`：扣除完整成本后的期望收益；
- `barrier_up / barrier_down / timeout`；
- `timing_window`；
- `reliability / data_quality / sample_support / evidence_maturity`；
- `abstain` 与机器可读原因。

`EFS=70` 不代表存在 Alpha；当 `baseline_prob=71%` 时，概率增量仍为负。

## 强制工作流

1. **FRAME**：冻结标的永久 ID、Universe Snapshot、`as_of`、5D/20D/60D 周期、交易日历、标签、成交价格、hurdle 和成本。
2. **VALIDATE**：验证 `effective_at / published_at / ingested_at`、revision、来源、许可证、哈希、模型适用范围和数据新鲜度。
3. **INFER**：只运行已哈希绑定的确定性 Forecast Bundle；缺少 Expert 时只能使用预先登记的 admissible expert set。
4. **CALIBRATE**：只使用冻结的样本外校准器；未经校准不得称为概率。
5. **ESTIMATE**：分别计算方向、幅度、经济 Edge、竞争风险时机和可靠性。
6. **AUDIT**：检查分布外、专家分歧、样本支持、数据冲突、成本与能力状态。
7. **DECIDE**：输出 `FORECAST` 或 `ABSTAIN`；本 Skill 不生成订单。
8. **RECORD**：返回确定性 `ForecastSignalEnvelope` 和宿主可渲染的可视化 Payload。

## 运行命令

从 Skill 根目录执行：

```bash
python3 -B -m equity_foresight_signal self-check
python3 -B -m equity_foresight_signal validate-bundle fixtures/bundle.json
python3 -B -m equity_foresight_signal evaluate fixtures/request.json fixtures/bundle.json
python3 -B -m equity_foresight_signal validate-dataset fixtures/pit_dataset.json
python3 -B -m equity_foresight_signal train-direction fixtures/pit_dataset.json fixtures/training_config.json
python3 -B -m equity_foresight_signal audit-runtime
python3 -B tools/run_release_oracles.py --output /tmp/efs-release-oracles.json
```

## 0 Agent、0 LLM Token 合同

正常、异常、降级、训练、评测、比较、恢复和中文解释路径必须满足：

```text
agent_invocations_total = 0
llm_requests_total = 0
llm_input_tokens_total = 0
llm_output_tokens_total = 0
```

运行代码不得导入 Agent/LLM/MCP 框架，不得联网下载模型，不得在失败时调用聊天模型。解释只能来自受测模板。
v0.0.0.1 的全部发布授权路径只使用 Python 标准库；Decision Support 与其签名验权适配器不包含在本版本，任何请求必须 fail closed。

## 能力状态

- `ENGINEERING_VALIDATED`：仅证明工程合同。
- `OOS_VALIDATED`：冻结样本外证据通过，但仍不允许自动晋级。
- `OUTCOME_PROVEN`：独立 untouched holdout 与成本压力通过，仍需宿主单独批准。
- `SHADOW_ONLY`：工程可运行但预测有效性未证明或失败。

上一轮 SPY/VIX 基线在 5D、20D、60D 均未超过 rolling baseline，因此当前能力声明必须保持 `OUTCOME_NOT_PROVEN / SHADOW_ONLY`。

## 宿主职责

宿主负责数据获取、调度、持久化、状态传输、Private-Database 同步、R2/D1/OCI 冷备、可视化渲染和 LKG 激活。Skill 只生成纯函数结果、健康快照、状态 Payload 和不执行的恢复计划，不自行写库、联网、重试、晋级或回滚。

## 部署与本机零足迹

- 部署画像：`REMOTE_HOST_EMBEDDED_ONLY`；禁止 macOS Runtime 安装和执行。
- 全生命周期禁止 `launchd`、LaunchAgent、LaunchDaemon、登录项、后台 helper 和本机常驻进程。
- 不得写入 `$HOME`、`~/Library`、XDG cache/config/state/data、本机日志、数据库或模型缓存。
- 显式调用完成后，本机持久文件、持久字节和常驻后台进程必须均为 0；执行瞬间临时 CPU/RAM 不伪称为 0。
- 运行 `python3 -B tools/verify_macos_zero_footprint.py` 机械验证以上边界。

## 业务基线纵向切片与状态展示

`build_host_status_payload()` 必须返回 `efs.business_baseline_matrix.v1`，固定覆盖：证据与 PIT 输入、方向/幅度/时机预测、样本外 Outcome、Candidate/LKG 生命周期、状态/恢复五条纵向切片。每条记录包含阶段、阶段环节、状态、上游、下游、耦合控制、阻塞原因、下一动作、证据 Hash 和与机器字段绑定的全中文 `display_zh`；依赖图必须无环。任务包提供既有 LinzeStatus 的可逆 collector/web 补丁和一次性 Host writer，在 `status.linzezhang.com` 展示矩阵；复用既有 cron 与 v3 四入口静态页，保留四个一级入口，在“运行”页内嵌治理区块并接入健康行动清单，不新增一级入口、daemon、数据库、域名、Agent 或 LLM。Skill 只生成事实，不联网、不持久化、不创建控制面。

## 封包前复审关闭合同

Product Design、Verifier、Teleiosis、Persona Distiller/Group 等开发期方法在封包前完成并关闭；它们不属于运行依赖，也不得由开发 Agent 重新执行、委托或等待。开发 Agent 只核验包内证明 Hash，运行冻结的确定性测试，并完成目标仓兼容性、落库、CI、部署、commit、push、PR/merge 与备份。不得创建或修改版本号；本任务唯一版本为 `0.0.0.1`。包内复审证据不声称外部独立 SubAgent verdict，不能用于提升 `SHADOW_ONLY / OUTCOME_NOT_PROVEN` 能力上限。
