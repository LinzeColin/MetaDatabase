# MooMooAU Archive Roadmap v1.0.29

当前唯一工作单元：Stage 7 / T0705 protected GA format-preflight recovery successor。

| Gate | 状态 | 证据 |
|---|---|---|
| T0702 / S7AC-002 | PASS / frozen | protected receipt |
| T0703 / S7AC-003 | PASS / frozen | protected receipt + failed lineage |
| T0704 / S7AC-004 | PASS / frozen | protected receipt + failed lineage |
| T0705 protected attempts 1–9 | FAILED / frozen | nine immutable ledgers |
| v1.0.28 candidate preflight | FAILED before protected Environment | immutable preflight ledger |
| preflight remote effects | Secret/Gmail/private calls and mutations all zero | failed-job evidence |
| formatter root cause | one file would be reformatted | sanitized Ruff output |
| v1.0.29 runtime delta | Ruff formatter output only | exact diff |
| canonical Git Blob recovery | Fixture/history replay/fault injection PASS | focused tests |
| next protected rehearsal | AUTHORIZED / NOT_RUN / maximum one | one-task successor Run Contract |
| live 04:30 schedule | disabled until protected PASS | committed workflow hold |
| T0706 and later | unauthorized | current Run Contract |

执行顺序：

1. 验证不可变 v1.0.28、T0702–T0704 receipts、九份 protected failure ledger/schema、preflight
   ledger/schema 与 successor Run Contract。
2. 运行 workflow 同构的 Ruff format/check、strict mypy、Fixture、历史回放和故障注入；不等待
   真实时间或 Soak，不要求全量测试。
3. 经正常 PR/main 交付 format-only successor，设置只指向新 exact-main head 的 one-shot
   authority。
4. 只执行一次 attempt-1 `SCHEDULE_REHEARSAL`，rerun 0；所有失败 head 永不重跑。
5. PASS 后独立核验恢复、零误伤、exact-message Trash budget 1 与单 Timeline，再通过 closure
   delivery 绑定 receipt 并启用已提交 schedule。
6. 停止在 T0706 前，不做最终发布。
