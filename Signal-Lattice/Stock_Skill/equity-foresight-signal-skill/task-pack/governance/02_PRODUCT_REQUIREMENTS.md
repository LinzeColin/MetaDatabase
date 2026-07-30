# 产品需求

目标：以最小运行面，为现有股票系统提供可审计的方向概率、幅度与时机节点。

- O1：消除概率、幅度、可靠性和交易指令混用；输出语义全部由机器合同验证。
- O2：杜绝 Agent/LLM 运行依赖；静态、seccomp、network namespace 与调用计数全部为 0。
- O3：防止未来信息、错误 Universe 和无证据晋级；违规输入 fail closed，Candidate 永不自动替换 LKG。
- O4：控制成本；标准库 Runtime、无独立服务/数据库、无付费数据强依赖。

范围：PIT 输入、单标的/冻结 Universe、5D/20D/60D、EFS/Baseline/Lift、幅度、经济 Edge、障碍时机、Reliability、ABSTAIN、OOS/holdout 证据结构、Candidate/LKG、状态和可视化 Payload、确定性训练与封包。

非目标：实时抓取、付费数据捆绑、独立 UI/登录/搜索/上传、数据库/队列/daemon、在线自改模型、券商/订单/仓位/组合、Decision Support、收益保证和生产级 7×24 已证明声明。

Kill Criteria：真实 Outcome 不优于 null model、2×成本后 Edge 消失、结果只在单一时期成立、PIT/Universe/许可不可重建、新数据无增量，或必须膨胀为独立系统时，保持 `SHADOW_ONLY` 并停止当前版本扩张。

- O5：上线后 Owner 本机零持久、零常驻足迹；macOS 安装与 `launchd` 永久禁止。验收阈值：launchd units=0、调用后持久文件=0、持久字节=0、遗留后台进程=0。
- 部署节点：仅既有远程宿主嵌入；本 Skill 不建立专属 systemd、Docker、域名或数据库。

- O6：上线后提供业务基线纵向切片白箱治理。任务包必须把矩阵可逆接入既有 LinzeStatus；`status.linzezhang.com` 至少全中文展示每条业务线的阶段、阶段环节、状态、上下游、耦合控制、阻塞原因、下一动作和证据 Hash。矩阵由 Runtime 确定性生成，宿主一次性原子写入状态事实；复用既有 cron 与 v3 四入口静态页，保留四个一级入口，在“运行”页内嵌治理区块并接入健康行动清单，不新增一级入口、daemon、数据库、域名、Agent 或 LLM。
