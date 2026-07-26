# MooMooAU Archive Roadmap v1.0.33

当前唯一工作单元：Stage 7 / T0705 Raw canonical Git Blob recovery。

| Gate | 状态 | 证据 |
|---|---|---|
| T0702 / S7AC-002 | PASS / frozen | protected receipt |
| T0703 / S7AC-003 | PASS / frozen | protected receipt + failed lineage |
| T0704 / S7AC-004 | PASS / frozen | protected receipt + failed lineage |
| T0705 protected attempts 1–12 | FAILED / frozen | twelve immutable ledgers |
| v1.0.28 candidate validation | FAILED before protected Environment | immutable preflight ledger |
| v1.0.29 authority context | FAILED before checkout | immutable authority-context ledger |
| v1.0.30 schedule planning | FAILED before Gmail API/data mutation | immutable schedule-planning ledger |
| v1.0.31 App authentication | FAILED before repository resolution | immutable authentication-clock ledger |
| v1.0.32 Raw recovery | FAILED before Timeline/checkpoint | immutable Raw-recovery ledger |
| all failed heads | rerun 0 / redispatch 0 | schema-bound ledgers |
| v1.0.33 data-plane delta | Raw recovery adapter only | exact diff + fault injection |
| Raw recovery source | metadata-addressed Git Blob | canonical size/SHA/age checks |
| rehearsal planner clock | historical fixture, RunPlanner only | Run Contract + fixture test |
| next protected rehearsal | AUTHORIZED / NOT_RUN / maximum one | one-task successor Run Contract |
| live 04:30 schedule | live UTC; disabled until protected PASS | committed workflow hold |
| T0706 and later | unauthorized | current Run Contract |

执行顺序：

1. 验证不可变 v1.0.32、T0702–T0704 receipts、十二份 protected failure ledger/schema、两份
   pre-Secret ledger/schema 与 successor Run Contract。
2. 用 Contents raw-media 差异 Fixture、metadata-addressed Git Blob Fixture、revision drift
   故障注入和 `2026-07-26T19:00:00Z` planner Fake Clock 即时验证；不等待真实时间、Soak、
   观察窗口或全量测试。
3. 经 PR/main 交付 successor；仅在精确 merge SHA 存在后设置 repository-scope one-shot variable。
4. 只执行一次 attempt-1 `SCHEDULE_REHEARSAL`，rerun 0；authority 消耗后立即删除变量。
5. PASS 后独立核验恢复、零误伤、exact-message Trash budget 1 与单 Timeline，再通过 closure
   delivery 绑定 receipt 并启用真实时钟的已提交 schedule。
6. 停止在 T0706 前，不做最终发布。
