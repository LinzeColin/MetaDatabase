# MooMooAU Archive Roadmap v1.0.17

当前唯一工作单元：Stage 7 / T0704 protected Release Asset redirect repair。

| Gate | 当前状态 | 证据 |
|---|---|---|
| T0702 / S7AC-002 | PASS | 不可变 protected receipt |
| T0703 / S7AC-003 | PASS | 不可变 protected receipt + failed-head ledger |
| T0704 首次 exact-main attempt | FAILED / frozen | run `30175241669`、attempt 1、rerun 0、加密 repair state |
| processed-current | unchanged | 独立前后 path + blob identity |
| T0704 302 修复 | PASS（本地） | 18 项 T0704 测试中的 302、恶意跳转与 zero-asset replay |
| 新 exact-main repair attempt | 待运行 | one new-head dispatch、attempt 1、rerun 0 |
| T0704 / S7AC-004 | FAILED / incomplete | 只能由新的 protected PASS receipt 闭合 |
| T0705 及以后 | 未授权 | 本轮停止条件 |

执行顺序：

1. 校验 v1.0.16 predecessor、T0702/T0703 receipts、T0704 failed-attempt ledger 与修复 Run Contract。
2. 合入唯一受控 repair candidate，确认 exact-main CI 全绿且失败 head 无 rerun。
3. protected job 从 encrypted repair state 恢复相同 snapshot root；candidate 与 snapshot 只读恢复，
   不重复写入。
4. Asset API 若返回 `200` 则直接恢复；若返回 `302`，仅执行一次无 Authorization 的受控
   GitHub release-asset 跳转。
5. 验证 processed-current unchanged、candidate/snapshot new commits 0、Gmail mutation 0、
   live Timeline min=max=1 且 round-trip recovery 100%。
6. 固化 T0704 结果并停止；不进入 T0705。
