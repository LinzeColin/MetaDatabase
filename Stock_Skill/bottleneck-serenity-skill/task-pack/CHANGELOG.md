# Task Pack Changelog

## Unreleased — v0.0.0.1

### Stage 0

- 建立 `bottleneck-serenity-skill` 专用 worktree，并恢复 canonical 主树到干净 `main`。
- 冻结全局稳定 ID `bottleneck-serenity-skill`。
- 冻结机器版本 `0.0.0.1` 与展示/release 版本 `v0.0.0.1`。
- 定义 source-only、禁止本机安装、禁止交易执行与公开安全边界。
- 创建 compact `5+1` Task Pack。
- 将后续工作拆为单 Task run，并为每个 Stage 定义整体复审、整改、重审和上传门。
- 完成 Task Pack 结构、身份、版本、Task ID、阶段门、公开路径和 registry 回归自检。
- 完成 Stage 0 整体复审，锁定 subject digest
  `37452ef7fe3cdef60ffcdbf9c448b82b79537c01b2f6819936900c5d4ab9f863`。
- 按 `BSS-S0-P2-T002` 整改 6 个 P1 与 1 个 P2 finding，等待独立重审关闭。
- `BSS-S0-P2-T003` 在整改后 subject
  `d2794667d739d30012faf8f28889e27574772d53a6b70eca62308acef28883e4` 上重审，verdict `FAIL`。
- `BSS-S0-P2-T004` 仅整改五个未关闭 finding；Builder 状态更新为
  `FIXED_PENDING_REREVIEW`，等待 `BSS-S0-P2-T005` 在新 subject 上独立关闭。
- `BSS-S0-P2-T005` 在 subject
  `b97ef4030e9bb23581ca22dc89560a738c583dff6eeb4e5ce037ce670528edcd` 上完成第二轮整体重审，
  关闭三项 finding、保留两项并新增一项，verdict `FAIL`。
- `BSS-S0-P2-T006` 只整改三项 OPEN finding；Builder 状态更新为
  `FIXED_PENDING_REREVIEW`，等待 `BSS-S0-P2-T007` 独立关闭。
- `BSS-S0-P2-T007` 在 subject
  `849caf740442f5450db016462b030f9c22b15507c3c805571960b4b6da5ac5d5` 上完成第三轮整体重审，
  关闭一项、保留两项，verdict `FAIL`。
- `BSS-S0-P2-T008` 只整改两项 OPEN finding；Builder 状态更新为
  `FIXED_PENDING_REREVIEW`，等待 `BSS-S0-P2-T009` 独立关闭。
- `BSS-S0-P2-T009` 在 subject
  `1fbfff05462e03b514edb6bf9ba434cc50b645ec02a45291a393953485ca2315` 上完成第四轮整体重审；
  关闭 `S0-R001/R011`，新增 release/manifest 封印图不可执行的 `S0-R012`，verdict `FAIL`。
- `BSS-S0-P2-T010` 只整改 `S0-R012`：冻结 task manifest、release、sums/registry、backup manifest 的
  单向 DAG，首次 registry 激活的真实 SHA 门，以及 Review 候选 → Publish source freeze → derived render →
  staged-tree replay → upload 的封印顺序。
- `BSS-S0-P2-T011` 在 subject
  `f17ad7dfaa2088f645e37a88ce415ee3d0e672ebe07361b1f69d9a810a7636ad` 上完成第五轮整体重审；
  `S0-R012` 与全部历史 finding 回归 PASS，ledger 零未关闭 finding，Stage Review verdict `PASS`。

## Stage review ledger

状态：`OPEN` → `FIXED_PENDING_REREVIEW` → `CLOSED`。Builder 不得把自己的修复直接标为 `CLOSED`。

| Finding | Severity | Reviewed subject | Remediation Task | 状态 | Remediation evidence | Closure evidence |
|---|---|---|---|---|---|---|
| `S0-R001` 端到端追溯缺失 | `P1` | `1fbfff05...a2315` | `BSS-S0-P2-T008` | `CLOSED` | Producer=首次建立完整验收能力/主制品集合的稳定 Owner；例行刷新派生 hash 不转移，责任性变更才转移 | `BSS-S0-P2-T009 — Producer 稳定性、44 行映射与引用复验 PASS` |
| `S0-R002` Task Pack 未封印 | `P1` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 新增 `VERSION`、完整 manifest 与 digest 规则 | `BSS-S0-P2-T003 — 文件集合、哈希与锁定 digest PASS` |
| `S0-R003` finding/等级规则缺失 | `P1` | `b97ef403...8edcd` | `BSS-S0-P2-T004` | `CLOSED` | ledger 显式记录整改 Task、整改证据、状态与独立关闭证据 | `BSS-S0-P2-T005 — 七列 schema、状态与关闭 Owner 复验 PASS` |
| `S0-R004` Stock Skill 无 CI | `P1` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 加入 `BSS-S1-P2-T003`、`ACC-S1-006` 与专用 workflow 契约 | `BSS-S0-P2-T003 — Task/ACC/架构三处一致` |
| `S0-R005` release/恢复契约不足 | `P1` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 冻结 ZIP root/payload/order/time/mode/build/verify/restore | `BSS-S0-P2-T003 — release/restore 条款逐项 PASS` |
| `S0-R006` 许可与核心逻辑门缺失 | `P1` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 加入许可归属、项目文件、语义审计 Task 与 Acceptance | `BSS-S0-P2-T003 — REQ/Task/ACC 映射 PASS` |
| `S0-R007` 假设/四段版本规则不完整 | `P2` | `d2794667...883e4` | `BSS-S0-P2-T002` | `CLOSED` | 加入假设冻结点与无前导零 numeric-quad 正则 | `BSS-S0-P2-T003 — 生命周期与正则复验 PASS` |
| `S0-R008` Stage 0 worktree Oracle 冲突 | `P1` | `b97ef403...8edcd` | `BSS-S0-P2-T004` | `CLOSED` | pre-publish 仅要求本项目 scoped changes；Publish commit 后才要求干净 | `BSS-S0-P2-T005 — main clean、8 个 changed file 全在本项目，复验 PASS` |
| `S0-R009` 需求权威等级过高 | `P2` | `b97ef403...8edcd` | `BSS-S0-P2-T004` | `CLOSED` | 新增 `DERIVED`/`SOURCE_MANDATED`，修正 `REQ-022/REQ-023` 与证据 | `BSS-S0-P2-T005 — taxonomy 与两行 authority 复验 PASS` |
| `S0-R010` 重审失败后无合法循环 Task | `P1` | `849caf74...ac5d5` | `BSS-S0-P2-T006` | `CLOSED` | Stage 4 终态 Phase 改为 `Publish`，明确其交付/合并语义及成功后进入 Cleanup | `BSS-S0-P2-T007 — 五 Stage 正常/失败路由复验 PASS` |
| `S0-R011` subject digest 算法缺失 | `P1` | `1fbfff05...a2315` | `BSS-S0-P2-T008` | `CLOSED` | 参考实现检查 Root/manifest/非空 subject，并拒绝 Root/entry symlink 与非普通文件；六类负例非零 | `BSS-S0-P2-T009 — 双实现同 digest，八类负例全部 fail closed` |
| `S0-R012` release/manifest 封印图不可执行 | `P1` | `f17ad7df...7636ad` | `BSS-S0-P2-T010` | `CLOSED` | task manifest 不越 Root；release SHA 只进入 sums/registry/backup；首次 registry 激活等待真实 SHA；backup 最后生成；Publish 从 frozen source 重建并 staged-tree/clean replay；外部终态证据不反写 | `BSS-S0-P2-T011 — DAG/反向边、双构建、三消费面、原子激活与 proposed-tree replay 全 PASS` |

### Pending

- `BSS-S0-P3-T001` 统一封印并上传 Stage 0、创建 draft PR；必须先同步最新 `origin/main`，完成
  proposed-tree replay、post-commit clean、远端 diff 与 PR 状态验证。Stage 1 在 Publish PASS 前不可执行。
