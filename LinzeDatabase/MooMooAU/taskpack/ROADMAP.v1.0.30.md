# MooMooAU Archive Roadmap v1.0.30

当前唯一工作单元：Stage 7 / T0705 protected GA one-shot authority scope recovery。

| Gate | 状态 | 证据 |
|---|---|---|
| T0702 / S7AC-002 | PASS / frozen | protected receipt |
| T0703 / S7AC-003 | PASS / frozen | protected receipt + failed lineage |
| T0704 / S7AC-004 | PASS / frozen | protected receipt + failed lineage |
| T0705 protected attempts 1–9 | FAILED / frozen | nine immutable ledgers |
| v1.0.28 candidate validation | FAILED before protected Environment | immutable preflight ledger |
| v1.0.29 authority context | FAILED before checkout | immutable authority-context ledger |
| both pre-Secret failures | Secret/Gmail/private calls and mutations all zero | schema-bound ledgers |
| v1.0.30 runtime data-plane delta | none | exact diff |
| one-shot authority | repository scope after exact main merge | Run Contract |
| next protected rehearsal | AUTHORIZED / NOT_RUN / maximum one | one-task successor Run Contract |
| live 04:30 schedule | disabled until protected PASS | committed workflow hold |
| T0706 and later | unauthorized | current Run Contract |

执行顺序：

1. 验证不可变 v1.0.29、T0702–T0704 receipts、九份 protected failure ledger/schema、两份
   pre-Secret ledger/schema 与 successor Run Contract。
2. 使用 workflow 同构 Ruff、strict mypy、Fixture、历史回放和故障注入即时验证；不等待真实时间、
   Soak 或全量测试。
3. 经 PR/main 交付 successor；仅在精确 merge SHA 存在后设置 repository-scope one-shot variable。
4. 只执行一次 attempt-1 `SCHEDULE_REHEARSAL`，rerun 0；authority 消耗后立即删除变量。
5. PASS 后独立核验恢复、零误伤、exact-message Trash budget 1 与单 Timeline，再通过 closure
   delivery 绑定 receipt 并启用已提交 schedule。
6. 停止在 T0706 前，不做最终发布。
