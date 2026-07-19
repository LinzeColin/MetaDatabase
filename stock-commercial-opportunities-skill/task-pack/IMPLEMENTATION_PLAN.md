# 实施计划与 Run Contracts

## 1. 原子任务

| ID | 任务 | 输入 | 产物 | 验收/停止 |
|---|---|---|---|---|
| R00 | v1/v2 谱系盘点 | 原 ZIP/summary | hashes + source inventory | byte hash 固定；冲突即停 |
| R01 | 股票同类研究 | 官方/GitHub/产品页 | research report + matrix | 页面已打开；不以 snippet 结论 |
| P01 | 定位与触发 | 用户 job + negatives | name/description/lanes | 股票专用；个人建议不触发 |
| M01 | 商业机制 | theme/driver | value-chain contract | payer/value pool/bottleneck/substitute |
| M02 | 证券身份 | issuer candidates | normalized identity fields | identity 不清不排名 |
| E01 | 来源/claim 模型 | official source hierarchy | source/claim schemas | URL/access/period/units 可追踪 |
| E02 | E0–E5 | evidence signals | conservative derivation | score 不升级 maturity |
| S01 | Scorer | weights/risks/signals | standard-library CLI | advance/diligence/reject fixtures |
| V01 | Deliverable validator | JSON contract | relationship/safety gates | public/private/MNPI/advice fail closed |
| V02 | Skill validator | package contract | structure/link/cache gate | strict 0 error/0 warning |
| A01 | Templates | contracts | intake/card/ledger/note | 可直接填写、无真实股票 |
| Q01 | Trigger/quality evals | boundaries/rubric | JSONL + benchmark CSV | 12 positive/10 negative/8 quality |
| T01 | Regression tests | scripts/fixtures | unit + CLI suite | 全部 PASS；无 cache |
| D01 | 任务包一致性 | all design artifacts | docs/version/changelog | 无旧 ID/旧状态漂移 |
| B01 | Release | clean task-pack | manifest + ZIP + SHA | unzip + clean-room tests |
| G01 | Remote backup | isolated worktree | commit/PR/main | remote main independently recoverable |
| C01 | 精确本地清理 | verified remote evidence | delete exact task artifacts/worktree | 不触碰 session/其他项目；记录限制 |

依赖：`R00,R01 → P/M/E → S/V/A/Q/T → D → B → G → C`。任何未通过任务不得用下游产物反向宣称 PASS。

## 2. RC-DETERMINISTIC

- Goal：G1/G2。
- Scope：`task-pack/**`。
- Validation：29+ tests、3 CLI、JSON/JSONL/CSV/YAML、links、AST imports、cache/secret/path scan。
- Rollback：撤销当前 task-pack diff。
- Stop：真实市场事实进入 fixture、阻断测试失败或需要外部账号。

## 3. RC-RELEASE

- Goal：G3。
- Preconditions：RC-DETERMINISTIC PASS。
- Actions：重建 `MANIFEST.sha256`；创建 v3 ZIP；生成 SHA256SUMS；解压到临时目录；从解压副本重复 strict/test。
- Stop：ZIP 结构、hash、路径可移植性或解压测试失败。

## 4. RC-REMOTE-BACKUP

- Goal：G4。
- Preconditions：公开安全扫描、G3 PASS、isolated worktree。
- Actions：commit → push branch → PR → merge → 从 GitHub `main` 临时 sparse clone/下载 → hash/test。
- Rollback：合并前关闭 PR/删分支；合并后用新 commit 修复，不重写公开历史。
- Stop：仓库可见性/许可不符、secret/path 命中、remote verification 失败。

## 5. RC-CLEANUP

- Goal：在远端可恢复后最小化本地负担。
- Preconditions：远端 main commit 可解析；独立恢复 G3 PASS；精确清理清单已解析。
- Actions：删除原 download/task workspace/temp cache；收 worktree/branch；`git gc`（禁止 `--prune=now`）；提交 memory 删除请求 note。
- 禁止：删除活动 Codex session、直接改 MEMORY、清空共享 repo、广泛 glob、sudo、VACUUM live DB。
- 完成表达：精确目标已删；Git/活动 session/允许的 memory request note 等不可或不应即时清除项单独披露。

## 6. RC-SEMANTIC（未来）

- Goal：G5，不安装条件下显式加载源码做 trigger/A-B。
- Cases：22 trigger；Q01/Q04/Q05/Q08 paired outputs。
- Gate：recall/specificity ≥90%；关键质量 3 项提升；安全不退化；无 E0/E1 overclaim；成本无理由 ≤2.5x。
- Writes：只保存公开安全 benchmark 与原始评估证据；不改 Skill，除非开启下一 Run。

## 7. RC-INSTALL（未来且当前禁止）

只有新的明确用户授权可开启。必须重新检查 collision、目标根、backup、staging、discovery、rollback。当前包完成不推导安装权限。
