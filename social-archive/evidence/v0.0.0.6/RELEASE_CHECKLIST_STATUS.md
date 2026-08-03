# v0.0.0.6 Release Checklist Status

Against `10_ACCEPTANCE/RELEASE_CHECKLIST.md`. **Overall: not releasable.** Six items cannot be ticked, and every one of them traces to a gate that needs the Owner.

| # | Item | Status | Basis |
|---|---|---|---|
| 1 | Version 与 Tag 一致 | **BLOCKED** | `VERSION`, both manifests and all `machine/*.json` now read `0.0.0.6`, and the five contracts that still stamped `v0.0.0.5` were corrected. No tag exists, because tagging is deliberately deferred until the pack completes. |
| 2 | main 是唯一活动长期分支 | **NOT MET** | `origin` carries at least eight long-lived branches (`codex/*`, `claude/*`). None are mine except `claude/social-archive-v0-0-0-6-eaad48`, which is local only. Cleaning other sessions' branches is theirs to do. |
| 3 | 无 Open PR | **PASS** | `gh pr list --state open` returns 0. |
| 4 | 实现目录无旧名称 | **PASS** | `xhs-douyin-2notion/` is absent; `scripts/check_brand.py` reports PASS with no hits. |
| 5 | 来源 Commit 和镜像 Digest 全部锁定 | **PASS** | Production images pinned: `social-archive/core:0.0.0.6` `sha256:1deb565c93c4a726c3ee2ccb0ecf6bde68f48b36ea1df19f56e411259cc910f7`, `social-archive/cli-tools:0.0.0.6` `sha256:cb09c71f7974c3bf52be1d25ea2f0789b6d301d1e8379daaa83c187dabd92640`. |
| 6 | 未知许可证组件未启用 | **PASS** | `machine/third_party_lock.json` holds one reference-only entry, explicitly `default_enabled: false` with no code reuse. No GPL/AGPL enters the first-party core. |
| 7 | 无付费依赖 | **PASS** | Production `/health` reports `paid_api_allowed: false`. |
| 8 | 数据库备份与恢复点存在 | **PASS** | Cold backup produced two verified remote copies and two verified recovery descriptors; both R2 and OCI restore to the same plaintext hash. |
| 9 | 本版本定向测试通过 | **PASS** | Full application regression 310 passed. Sealed pack verify PASS on a clean extraction: 0 failures, 395 manifest entries, 97 candidate tests. |
| 10 | 对应真实 Canary 通过 | **BLOCKED** | The four-platform Owner Canary has not run. The extension is not installed in the Owner's logged-in Chrome and no browser is reachable from the agent session. |
| 11 | GitHub/R2/OCI 回执通过 | **PARTIAL** | R2 and OCI: 17/17 real artifacts plus a write/readback/delete canary. GitHub third copy: blocked on a fine-grained token for the recreated vault. |
| 12 | 三目标恢复通过 | **BLOCKED** | R2 and OCI recover for real with identical hashes. GitHub fails closed with `GITHUB_RECEIPT_REPOSITORY_MISMATCH`, correctly, because the historical receipt belongs to the deleted vault. |
| 13 | 秘密扫描通过 | **PASS** | `scripts/secret_scan.py` PASS, no hits. No secret value entered the terminal, evidence or Git at any point. |
| 14 | UI 错误状态通过 | **PARTIAL** | Destination error states verified live: Notion reports `needs_user_action` with a specific next action, and an unavailable destination is reported in `skipped_destination_ids` rather than dropped. Browser-rendered error states were not exercised. |
| 15 | 升级/回滚通过 | **PARTIAL** | Upgrade proven: the v0.0.0.5 to v0.0.0.6 cutover ran with all containers healthy. Rollback drilled but not executed: the source tarball extracts to a complete, correctly pinned v0.0.0.5 tree. The prebuilt `:0.0.0.5` images no longer exist, so rollback costs a rebuild. |
| 16 | Release Notes 列出已知降级 | **PASS** | `evidence/v0.0.0.6/VALIDATION_REPORT.md` lists all nine non-PASS tasks grouped under four root causes. |
| 17 | 部署后 Smoke 通过 | **PASS** | Credential-free public smoke: library 302 at the Access boundary, health and pairing status 200, three business routes 401, status projection 200. `doctor.sh --self-test` passes 28 deployment-contract checks. |
| 18 | 证据 Manifest 已封存 | **PASS** | All 32 tasks carry `RESULT.json` and `COMMAND_LOG.json` at v0.0.0.6 with zero inconsistencies; index at `evidence/v0.0.0.6/EVIDENCE_INDEX.json`. |

## Blocking summary

Items 1, 10, 12 and the partials in 11, 14, 15 all reduce to the same four Owner-gated root causes recorded in the validation report: the extension install, the vault fine-grained token, the Notion Integration token, and host disk capacity.

Item 2 is the one exception — it is not blocked by a credential, but the extra long-lived branches belong to other sessions, and under the workspace rule that whoever opened something closes it, they are not mine to delete.
