# MooMooAU Archive Roadmap v1.0.25

当前唯一工作单元：Stage 7 / T0705 protected GA first-import recovery subphase diagnostic。

| Gate | 状态 | 证据 |
|---|---|---|
| T0702 / S7AC-002 | PASS / frozen | protected receipt |
| T0703 / S7AC-003 | PASS / frozen | protected receipt + failed lineage |
| T0704 / S7AC-004 | PASS / frozen | protected receipt + failed lineage |
| T0705 attempts 1–6 | FAILED / six heads frozen | six immutable ledgers |
| sixth private effects | zero commits and zero path changes | read-only connected-repository verification |
| sixth failure boundary | after Raw recovery/classification, within first-import recovery, before document-envelope construction or Processed write | committed phase ordering |
| exact real-data root cause | UNKNOWN | no inference beyond evidence |
| first-import subphase diagnostic | local candidate PASS | focused regression oracles |
| next protected rehearsal | AUTHORIZED / NOT_RUN | one-task successor Run Contract |
| exact closure if diagnostic fails | AUTHORIZED / NOT_RUN / maximum one | bounded successor Run Contract |
| live 04:30 schedule | disabled until protected PASS | committed workflow hold |
| T0706 and later | unauthorized | current Run Contract |

执行顺序：

1. 验证 v1.0.24、T0702–T0704 receipts、六份 T0705 ledger/schema 和 successor Run Contract。
2. 验证固定 first-import 子阶段枚举、公开输出脱敏、生产路径不变与全部累计门禁。
3. 经正常 PR/main 交付候选，设置只指向新 exact-main head 的 one-shot authority。
4. 只执行一次 attempt-1 `SCHEDULE_REHEARSAL`，rerun 0；六个失败 head 永不重跑。
5. 若 diagnostic 失败，冻结该 head，只交付一个精确 repair-or-PASS closure 并运行一次；不做
   相同 head rerun。
6. PASS 后独立核验恢复、零误伤、exact-message Trash budget 1 与单 Timeline，再通过 closure
   delivery 绑定 receipt 并启用已提交 schedule。
7. 停止在 T0706 前，不做最终发布。
