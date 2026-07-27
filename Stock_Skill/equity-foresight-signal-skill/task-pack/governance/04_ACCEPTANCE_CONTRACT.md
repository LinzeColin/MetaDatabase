# Acceptance Contract

正式候选必须是单一 deterministic ZIP 和 SHA-256；任何字节变化使既有 verdict 失效。目标能力上限：`SHADOW_ONLY`。

工程门槛：全部测试通过；运行和自动模型生命周期的 Agent/LLM/MCP/网络/子进程/第三方依赖为 0；seccomp 与 user/network namespace 通过；同一输入至少 10,000 次结果 Hash 唯一；Fuzz 至少 10,000 次且未捕获异常为 0；PIT/Universe/成本/用途/Candidate/LKG/恶意 ZIP fail closed；DAG 无环无等待；Traceability 完整；ZIP/Manifest/SHA/语法/Secret/路径检查通过。

v0.0.0.1 不申请 `OUTCOME_PROVEN` 或 Decision Support；`OUTCOME_NOT_PROVEN / SHADOW_ONLY` 是本版本合格结果，不是工程 FAIL。

封包前对所有适用 Skill 方法执行至少三次确定性契约应用，并生成同时绑定精确 Subject、冻结 Acceptance Contract 与统一 Release Oracle 的 `PREPACKAGING_REVIEW_CLOSURE.json`。该回执明确 `external_independence_claim=false`、不构成外部独立 verdict 或 Outcome 证明；其用途是证明封包前方法闭合。Codex 不得重新执行、委托或等待复审，只核验证明 Hash 与冻结测试，且不得新建或修改 `0.0.0.1` 版本号。

新增硬门：`macos_runtime_install_permitted=false`；`macos_launchd_units=0`；`local_persistent_files_after_invocation=0`；`local_persistent_bytes_after_invocation=0`；`resident_background_processes_after_invocation=0`。`verify_macos_zero_footprint.py` 必须 PASS，并由 `run_release_oracles.py` 和最终 Manifest 追踪。

业务基线治理硬门：`build_host_status_payload()` 必须输出 `efs.business_baseline_matrix.v1`；五条纵向切片均具有非空阶段、状态、上下游、耦合控制和下一动作；依赖图无环；矩阵 Hash 与外层 Status Payload 绑定；`status_endpoint=status.linzezhang.com`；`self_network_transport=false`、`self_persistence=false`、Agent/LLM/网络计数全部为 0。篡改 Canonical Facts、Requirement R-014 或矩阵汇总必须 fail closed。

Status 落地硬门：`LinzeHomeHub` 两个目标文件必须通过唯一锚点与工作树清洁 preflight；补丁 apply/verify/rollback 必须可逆；全中文 `display_zh` 与机器字段必须一致；Host writer 的 Agent/LLM/网络计数为 0 且拒绝 macOS；缺失/损坏状态事实不得拖垮原采集器；不得新增 daemon、数据库或域名。
