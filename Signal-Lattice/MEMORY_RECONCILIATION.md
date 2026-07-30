# Signal Lattice｜上下文校准

## ACTIVE

- 版本锁定为 `v0.0.0.1.40`；当前状态由 `CANONICAL_STATE.json` 声明为 `SEALED_TASKPACK`。
- Owner 已明确授权最终开发任务包交付；授权范围仅为任务包封存，不等于正式生产发布 PASS。
- 产品范围、Acceptance、Task DAG、版本和运行边界已冻结。
- 运行期保持零 Agent、零模型 Token、禁止自动交易、禁止上游写回、禁止 macOS 常驻和 launchd。
- Status 是运行状态只读投影与首尾控制入口，不是第二业务事实源。
- Build Agent 只承担目标仓写权限、真实凭证、供应商控制台、真实网络、环境兼容、部署和收尾。

## SUPERSEDED

- 早于 `v0.0.0.1.40` 且未绑定当前任务包的测试数、Manifest、Subject Hash 和 PASS 声明不得作为当前证据。
- “未满足连续两轮静默收敛不得交付任务包”已被 Owner 最新的明确交付授权覆盖；该覆盖不改变正式发布 fail-closed 门。

## CONFLICT

- 无未解决的产品合同冲突。

## UNVERIFIED／环境绑定

- 精确固定 checkout／worktree／bundle 生成的 Upstream Seal；
- 目标仓、OVH、Cloudflare、Private-Database、R2、OCI 和 Status 的真实凭证与环境；
- FROZEN_CANDIDATE 与独立正式发布验收。

以上均已转化为 `machine/facts/residual_environment_tasks.json` 中的确定性最后一公里任务，不需要 Build Agent 重新研究。
