# 股势前瞻 System Card｜v0.0.0.1 正式候选

## 用途与上限

本节点把宿主提供且已版本化的 point-in-time 市场证据转换为方向概率、涨跌幅分布、经济 Edge、障碍触及时机、可靠性和 `ABSTAIN`。它不获取数据、不生成订单、不替代组合风控。发布能力上限为 `SHADOW_ONLY`，真实 Outcome 为 `OUTCOME_NOT_PROVEN`。

## 模型与证据

工程实现使用确定性线性 Logit、冻结校准、分位数与竞争风险时机头；架构允许独立 Price、Fundamental、Event、Option、Futures、Rates/Credit、Flow Proxy、Macro Expert。每个 Expert 绑定特征、Universe、时效、许可证、模型 Hash 和周期。试验次数进入 Trial Manifest；评测报告无自动晋级权。

## 已知证据

工程链路已在当前 Linux x86_64 / Python 3.13 环境通过标准库 Runtime、Fuzz、确定性、seccomp 和 user/network namespace 验证。旧 SPY/VIX 5D/20D/60D 基线均未超过 rolling null model，作为不可删除负向事实。因此本版本不声明稳定 Alpha、Decision Support、生产级 7×24 或收益保证。

## 主要风险

未来数据泄漏、Universe/退市/公司行动偏差、成本与容量低估、多重试验、概率与正期望混用、资金代理误解、分布外高分，以及宿主错误地把 Shadow 输出用于交易。

## 安全措施

Canonical JSON + SHA-256；拒绝 Pickle/Joblib/动态加载；无网络、Secret、Prompt、Agent/LLM/MCP SDK、第三方 Python 依赖、数据库或 daemon；Candidate 不能自动替换 LKG；关键证据缺失或越界一律 fail closed。

## 监控与恢复

宿主保存低频结构化事实：Bundle Hash、能力、过期/冲突、ABSTAIN 原因、漂移、Candidate/LKG 和恢复结论。Skill 只生成状态与恢复计划，不写长期事实、不自行执行回滚。

## 部署与本机资源边界

发布画像为 `REMOTE_HOST_EMBEDDED_ONLY`。本 Skill 不得部署到 macOS，不得创建 `launchd`、LaunchAgent/LaunchDaemon、登录项或后台 helper；不写 `$HOME`、`~/Library`、XDG cache/config/state/data、本机日志、数据库或模型缓存。隔离 HOME/XDG/TMP 的机械 Oracle 要求 self-check、推断和确定性训练结束后：持久文件 0、持久字节 0、遗留后台进程 0。显式函数调用期间必然使用短暂 CPU/RAM，本 System Card 不作物理上不可能的“执行瞬间零内存”声明。

## 业务纵向切片可观测性

Host Status Payload 内嵌可哈希业务基线矩阵，覆盖输入、预测、Outcome、生命周期和状态/恢复五条纵向切片。每条记录明确阶段、阶段环节、当前状态、上游/下游、耦合控制、阻塞原因和下一动作，并提供与机器字段绑定的全中文 `display_zh`。宿主负责在 `status.linzezhang.com` 以矩阵表格为最低展示层；本 Skill 只生成事实，不自行联网或持久化。

接入层只复用既有 LinzeStatus cron 和 v3 四入口静态页面：一个最多 2 MB 的原子状态事实文件、五行业务矩阵、在“运行”页内嵌的治理区块及既有健康行动清单，无新一级入口、daemon、数据库或域名。页面或状态事实异常不改变预测内核，也不允许提升 `SHADOW_ONLY`。
