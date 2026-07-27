# CB-440 Immutable Release Candidate Card

该 card 描述一个本地 deterministic candidate contract，不是活跃 release、真实安装、
真实 canary、DNS/Access 变更或服务切换的声明。

| 面 | 固定判据 |
| --- | --- |
| provenance | CB-430 closure/tree、`app/package-lock.json` 与 source-lock 哈希固定 |
| slots | candidate/current/previous 均 immutable；candidate 不切换 current |
| flags | 7 个 MVP flags enabled；Claude、attachments、full-content、autonomous mutation disabled |
| migration | additive/backward-read local fixture；destructive migration=false |
| requests | 5 read-only + reject + cancel + reversible mutation，共 8 条 request-count predicates |
| rollback | P0/P1 → `previous`，`immediate_pointer_restore_no_wait`，current 保持不变 |
| operator | 8 条 command contract；live steps require authority，当前均 activation_pending |

候选 manifest、operator runbook 与 canary receipt 中 network/provider operations、deployment
mutations、control-plane/operations LLM calls、real-time waits 均为 `0`，也没有 macOS
launchd dependency。R2 保持 `hazard_blocked`；真实 candidate installation、current switch、
live request-count Canary 与 rollback 保持 `activation_pending`，由 Stage 5 的受权 activation
任务重新验证，不能因本地 fixture 伪绿。
