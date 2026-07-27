# CB-430 Fault Recovery Matrix

本卡是 `v0.0.0.5` 的本地、确定性、无凭据闭环，不是生产恢复或云端激活声明。

| 核心面 | 固定 case | 成功判据 |
| --- | --- | --- |
| fake clock | 日频窗口前/窗口内、release/incident/recovery、空事件 | pending、sync once 或 noop 精确一致 |
| 历史与 crash-cut | replay、persist-before-cursor、lease、outbox/canonical unknown outcome | loss=0；duplicate execution/side effect=0；不覆盖 canonical |
| 进程恢复 | service/runtime/channel | 仅 bounded probe-driven recovery，public listener=0 |
| backup/restore | isolated restore | logical digest equal、network disabled、不可 promote |
| 资源自愈 | resource floor | 一次 allowlisted action 后进入 hysteresis，禁止 infinite retry |

`canonical-fault-recovery-matrix.js` 固定 14 条 receipt，任何普通字段漂移、重复、loss、
wait、provider 调用、控制面/运维模型调用或 macOS launchd dependency 均立即拒绝。
它不替代现有组件测试；`validate_cb430.py` 同时运行 canonical sync、durable inbox/outbox、
scheduler、cloud supervisor、canonical backup 与 operations policy 的真实本地 test slices。

post-deploy matrix 的 trigger 是 `manual_or_ci`，状态是 `manual_or_ci_nonblocking`：
没有 timer 安装、没有真实时间等待、没有 deployment mutation，`timer_installation` 和
`external_recovery_execution` 都是 `activation_pending`。因此它可在真实权限和 Subject
已具备时作为可复跑计划，当前绝不声称 Provider 或服务恢复已发生。
