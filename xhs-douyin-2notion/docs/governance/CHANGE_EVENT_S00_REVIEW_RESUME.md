# Owner Change Event — CE-X2N-20260720-S00-REVIEW-RESUME

## Owner 决策

Owner 明确要求恢复 x2n 的长期目标并继续推进；现有共享 GitHub 认证材料由其他并行 Agent 使用，必须保持原样，不得由 x2n 读取、显示、删除、轮换、撤销、修改或写入证据。Owner 接受该共享材料继续存在的外部残余风险，并明确要求不再以“必须轮换该材料”暂停 x2n。

本事件不保存材料值、账号、Scope、标识、Remote URL、本机路径或 Provider 页面内容。

## 对原阻断的精确定性

`INC-X2N-S00-P05-001` 的触发是临时只读源码副本出现凭据形态 Remote。临时副本已删除，受影响产品/Runtime 文件为 0，项目当前树、项目历史、私有根与仓库 Remote 必须再次证明凭据形态命中为 0。

因此，本事件不把共享材料声明为“已撤销”“已过期”或“无风险”，也不使用 `WAIVED_WITH_OWNER_DECISION` 覆盖仓库/Runtime 内的 Secret 泄漏。它只把共享材料划为 x2n 外部、Owner 管理的并行基础设施，并以“x2n 零接触＋匿名公开源码研究补偿控制＋Owner 接受外部残余风险”替代原来的生命周期变更要求。

`04_ACCEPTANCE_CONTRACT_TRACEABILITY.md` 中 Secret/CDN 不可 waiver 的规则保持不变：未来只要 Secret、Cookie、认证 Remote 或 CDN 值进入 x2n Repo、History、Runtime、Evidence 或 Artifact，仍必须 Fail Closed，不能引用本事件放行。

## 补偿控制

- x2n 不读取、请求、显示、保存、使用或改变共享认证材料，也不修改全局 Git 配置或 Credential Helper。
- 未来公开源码研究只能匿名 HTTPS；每条命令隔离 global/system Git config、禁用 Credential Helper 与交互认证，并仅传入 allowlist 环境变量。
- 临时源码只位于 `X2N_DATA_ROOT` 的独立研究 Run，审计完成必须删除；不得接收为产品输出或 Runtime Dependency。
- G0 Resume 必须证明当前树、历史、私有根、产品/Runtime 引用和仓库认证 Remote 均为 0 命中。
- 本事件只解决 `INC-X2N-S00-P05-001`；不授权真实账号、平台调用、媒体、Notion、模型或绕过行为。

机器策略：`machine/policy/external_auth_material_isolation_policy.json`。

## 授权范围

- 授权单一 `STG.X2N.0.REVIEW.RESUME`，不执行新 DAG Task。
- 若完整 Resume 通过，可签发 G0、上传整个 Stage 0，并将下一 Run 路由到 `TSK.x2n.foundation.001`。
- 本 Run 不执行 Stage 1；Stage 1 仍须另开单 Task Run。

## 回滚与 Stop

- 回滚只可恢复 G0 阻断，不得触碰共享认证材料。
- 任一补偿控制未知或扫描非 0，Resume 失败并保持 G0 阻断。
- 任何文件、日志或工具输出出现材料值时立即停止、脱敏且不得提交。
