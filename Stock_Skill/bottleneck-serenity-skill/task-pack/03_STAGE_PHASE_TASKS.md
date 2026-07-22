# Stage, Phase, and Tasks

## 状态定义

- `DONE`：Task 的验收证据已产生。
- `ACTIVE`：当前 run 唯一允许执行的 Task。
- `PENDING`：前置门通过后可执行。
- `CONDITIONAL`：只有复审发现问题时执行。
- `BLOCKED`：存在无法在当前权限/证据内解决的阻塞。

任一时刻最多一个 `ACTIVE`。非 Review Task 的自身验证失败时只在该 Task 内修复，不自动扩大范围；
Review/Re-review 的 verdict 为 `FAIL` 时，必须按文末确定性复审循环另建或启用 Remediation/Re-review，
评审者不得在同一 run 顺手整改。

## Stage 0 — Governance baseline and authoritative Task Pack

| Task ID | Phase | 目标 | 验收证据 | 状态 |
|---|---|---|---|---|
| `BSS-S0-P0-T001` | Preflight | 恢复 canonical 主树并建立专用 worktree/branch | 主树 `main` 干净；任务 worktree 干净且 HEAD=`origin/main` | `DONE` |
| `BSS-S0-P1-T001` | Contract | 创建 compact `5+1` Task Pack | 六文件存在、内部自检通过、无项目实现变更 | `DONE` |
| `BSS-S0-P2-T001` | Review | 对 Stage 0 全部事实、范围、架构、Task 与门进行整体复审 | 逐项复审结论和问题清单 | `DONE` |
| `BSS-S0-P2-T002` | Remediation | 只修复 Stage 0 复审发现的问题 | 全部 finding 达到 `FIXED_PENDING_REREVIEW` 并通过回归 | `DONE` |
| `BSS-S0-P2-T003` | Re-review | 整体重跑 Stage 0 复审 | 发现追溯/ledger/oracle/权威标注/循环路由缺陷，verdict FAIL | `DONE` |
| `BSS-S0-P2-T004` | Remediation 2 | 只修复重审未关闭与新增 finding | `S0-R001/R003/R008/R009/R010` 达到 `FIXED_PENDING_REREVIEW` | `DONE` |
| `BSS-S0-P2-T005` | Re-review 2 | 对第二轮整改后的完整 Stage 0 重审 | 发现 Producer 责任、Stage 4 终态路由与 digest 算法缺陷，verdict FAIL | `DONE` |
| `BSS-S0-P2-T006` | Remediation 3 | 只修复第三轮重审未关闭与新增 finding | `S0-R001/R010/R011` 达到 `FIXED_PENDING_REREVIEW` | `DONE` |
| `BSS-S0-P2-T007` | Re-review 3 | 对第三轮整改后的完整 Stage 0 重审 | Producer 语义仍矛盾且 digest 缺 Root 时 fail-open，verdict FAIL | `DONE` |
| `BSS-S0-P2-T008` | Remediation 4 | 只修复第四轮重审未关闭 finding | `S0-R001/R011` 达到 `FIXED_PENDING_REREVIEW` | `DONE` |
| `BSS-S0-P2-T009` | Re-review 4 | 对第四轮整改后的完整 Stage 0 重审 | 关闭 `S0-R001/R011`，发现 release/manifest 封印图不可执行，verdict FAIL | `DONE` |
| `BSS-S0-P2-T010` | Remediation 5 | 只修复 release/manifest 所有权与最终封印顺序 | `S0-R012` 达到 `FIXED_PENDING_REREVIEW`，相关 Oracle 可执行且无环 | `DONE` |
| `BSS-S0-P2-T011` | Re-review 5 | 对第五轮整改后的完整 Stage 0 重审 | `S0-R012` CLOSED；ledger 零未关闭 finding、Stage Review gate PASS | `DONE` |
| `BSS-S0-P3-T001` | Publish | 封印 Stage 0 Task Pack、统一提交并创建 draft PR | manifest/拟提交树 replay PASS；commit 后干净；远端 diff 一致 | `PENDING` |

## Stage 1 — Registry version-model capability

本 Stage 只升级 registry 能力，不登记新 Skill，确保每个上传点都保持现有项目有效。

| Task ID | Phase | 目标 | 验收证据 | 状态 |
|---|---|---|---|---|
| `BSS-S1-P1-T001` | Design | 把 registry schema 升级为显式 `semver`/`numeric-quad` 模型 | schema 决策、兼容矩阵、现有条目无语义漂移 | `PENDING` |
| `BSS-S1-P1-T002` | Implement | 更新 validator 与 registry 现有条目 | 现有 `3.0.0`、哈希、路径保持一致；validator PASS | `PENDING` |
| `BSS-S1-P2-T001` | Test | 增加 validator 隔离测试与失败用例 | 合法/非法 scheme、四段版本、空 archive、fail-closed 全覆盖 | `PENDING` |
| `BSS-S1-P2-T002` | Docs | 同步根与 `Stock_Skill` 的版本模型说明 | 文档、registry、validator 术语一致 | `PENDING` |
| `BSS-S1-P2-T003` | CI | 新增 path-filtered Stock Skill validation workflow | PR/main 自动运行 registry、tests、manifest 与公开安全门 | `PENDING` |
| `BSS-S1-P3-T001` | Review | 整体复审 Stage 1 | 兼容性与回归清单 | `PENDING` |
| `BSS-S1-P3-T002` | Remediation | 修复 Stage 1 复审问题 | 问题关闭与重测 | `CONDITIONAL` |
| `BSS-S1-P3-T003` | Re-review | 复审整改后的完整 Stage 1 | Stage gate PASS | `CONDITIONAL` |
| `BSS-S1-P4-T001` | Publish | 封印 Stage 1 source 并统一 commit/push 到 draft PR | manifest/拟提交树 replay、远端 Stage diff 与 CI 状态 | `PENDING` |

## Stage 2 — Canonical Skill migration and registration

| Task ID | Phase | 目标 | 验收证据 | 状态 |
|---|---|---|---|---|
| `BSS-S2-P1-T001` | Initialize | 用 skill-creator 初始化最终稳定 ID 的 canonical Skill 骨架 | frontmatter 与目录名一致；无无关占位文件 | `PENDING` |
| `BSS-S2-P1-T002` | Import | 导入 scripts/references/schemas/templates/evals/examples/tests | 文件清单与输入源包逐项映射，无静默遗漏 | `PENDING` |
| `BSS-S2-P1-T003` | Rename | 完成 current source 的全局身份、事件和调用改名 | 旧身份 token 零残留；行为语义不变 | `PENDING` |
| `BSS-S2-P1-T004` | Semantic parity | 审计核心逻辑 diff 与版本影响 | 只允许身份/工程化变化；核心逻辑变化已停止并获用户决定 | `PENDING` |
| `BSS-S2-P2-T001` | Metadata | 重构 `SKILL.md`、生成 `agents/openai.yaml`、安置 provenance/notice | skill-creator validation PASS；项目/Skill 边界清晰 | `PENDING` |
| `BSS-S2-P2-T002` | Project | 创建外层 AGENTS/README/VERSION/CHANGELOG/SOURCE_INVENTORY/LICENSE/RESTORE | source-only、归属、版本与恢复说明完整 | `PENDING` |
| `BSS-S2-P2-T003` | Registry prep | 用隔离 fixture 冻结新 entry 字段、路径与发现面计划，不激活 registry | fixture 全字段/路径/version scheme 校验 PASS；active registry 未写入占位值 | `PENDING` |
| `BSS-S2-P2-T004` | Release/activate | 实现 build/verify、构建候选，并用真实 SHA 原子激活 registry/hash DAG/发现面 | 候选双构建同 SHA；ZIP、两个 manifest、registry、SOURCE_INVENTORY 全门 PASS | `PENDING` |
| `BSS-S2-P3-T001` | Test | 运行结构、单元、schema、hash、registry 回归 | 所有命令 PASS | `PENDING` |
| `BSS-S2-P4-T001` | Review | 整体复审 Stage 2 | 迁移、身份、版本、遗漏和恢复性清单 | `PENDING` |
| `BSS-S2-P4-T002` | Remediation | 修复 Stage 2 复审问题 | 问题关闭与全量回归 | `CONDITIONAL` |
| `BSS-S2-P4-T003` | Re-review | 复审整改后的完整 Stage 2 | Stage gate PASS | `CONDITIONAL` |
| `BSS-S2-P5-T001` | Publish | 封印 source，重建 current release/hash DAG 并 commit/push | staged-tree replay 得同 SHA；manifest/registry/远端 CI 一致 | `PENDING` |

## Stage 3 — Behavioral quality, safety, and historical E2E

| Task ID | Phase | 目标 | 验收证据 | 状态 |
|---|---|---|---|---|
| `BSS-S3-P1-T001` | Deterministic | 重跑全部脚本、单测、schema/example 与边界用例 | 可复现日志，全 PASS | `PENDING` |
| `BSS-S3-P1-T002` | Trigger eval | 评测正触发、负控制与鲁棒性 case | 预期触发/不触发 100% 符合；无交易执行 | `PENDING` |
| `BSS-S3-P1-T003` | Security | 扫描 secrets、绝对路径、网络/券商/下单能力和 prompt injection 边界 | 零高风险发现或有已验修复 | `PENDING` |
| `BSS-S3-P2-T001` | Historical E2E | 运行截至 `2024-12-31` 的历史主题案例 | source cutoff、claim ledger、输出 schema、无未来泄漏 | `PENDING` |
| `BSS-S3-P2-T002` | Forward test | 用最小泄漏上下文进行独立 Skill forward-test | 原始 prompt/output/trace 与 rubric 结论 | `PENDING` |
| `BSS-S3-P3-T001` | Review | 整体复审 Stage 3 | 行为、证据、安全与泛化清单 | `PENDING` |
| `BSS-S3-P3-T002` | Remediation | 修复 Stage 3 复审问题 | 问题关闭与全部相关评测重跑 | `CONDITIONAL` |
| `BSS-S3-P3-T003` | Re-review | 复审整改后的完整 Stage 3 | Stage gate PASS | `CONDITIONAL` |
| `BSS-S3-P4-T001` | Publish | 封印行为验收 source，重建 release/hash DAG 并 commit/push | staged-tree replay 得同 SHA；manifest/registry/远端 CI 一致 | `PENDING` |

## Stage 4 — Final acceptance, release, merge, and cleanup

| Task ID | Phase | 目标 | 验收证据 | 状态 |
|---|---|---|---|---|
| `BSS-S4-P1-T001` | Audit | 按所有显式要求完成逐项 completion audit | 每项有权威证据，弱/缺失证据不判完成 | `PENDING` |
| `BSS-S4-P1-T002` | Release readiness | 构建最终候选 release/manifests 并跑完整验收矩阵 | 候选全量 PASS、公开安全扫描 PASS、恢复演练 PASS | `PENDING` |
| `BSS-S4-P2-T001` | Review | 对整个 Stage 4 与全项目做最终整体复审 | ledger 零未关闭 finding，PR diff 可解释 | `PENDING` |
| `BSS-S4-P2-T002` | Remediation | 修复最终复审问题 | 问题关闭与受影响门重跑 | `CONDITIONAL` |
| `BSS-S4-P2-T003` | Re-review | 最终重审 | Final gate PASS | `CONDITIONAL` |
| `BSS-S4-P3-T001` | Publish | 最终封印、重建 release/hash DAG、commit/push、PR ready、CI、merge | staged-tree/clean replay 同 SHA；GitHub main 含最终内容，PR closed | `PENDING` |
| `BSS-S4-P3-T002` | Cleanup | 删除本任务 worktree、local/remote branch，prune metadata，运行安全 `git gc` | 主树 main/clean；任务资源全部回收 | `PENDING` |

## 复审与上传状态机

```text
Phase tasks complete
  -> Stage Review
    -> issues? Remediation -> Re-review (循环直到 PASS)
    -> no issues / PASS
      -> Stage Publish seal
        -> freeze source -> task manifest
        -> rebuild release (Stage 2–4) -> sums/registry -> backup manifest
        -> staged/proposed-tree replay
        -> one Stage commit + push
```

- Stage 0 首次上传时创建一个 draft PR。
- Stage 1–3 只在各自 Stage gate PASS 后向同一 draft PR push。
- Stage 4 最终 gate PASS 后把 PR 标记 ready、等待 CI、合并并执行清理。
- Stage 4 的 `Publish` 包含最终交付语义（PR ready、CI、merge/close）；其成功后唯一后续是 Cleanup。
- Release/Readiness 只产候选；含 release 的 Stage Publish 必须从 Review 后 frozen source 重建并验证
  current release。候选与已封印 release 不得混称。
- task manifest → release → sums/registry → backup manifest 必须单向生成；backup manifest 最后生成。
- Stage Publish 在 commit/push 前必须 clean replay staged/proposed tree；seal 后 source 改动必须在同一
  Publish Task 重新封印。Git/PR/CI/merge/cleanup 证据是外部叶子，不反写 release。
- seal 不得预写尚未发生的外部动作。非终态 Stage 的 Publish 行由下一 Stage 首个本地 Task 依据远端证据
  更新为 `DONE`；Stage 4 Publish/Cleanup 以 GitHub 与清理命令为最终证据，不为回写状态制造递归 PR。
- 任何 Phase 中途、复审未完成或 ledger 仍有非 `CLOSED` finding 时禁止 push。
- 每次 Review 在 `CHANGELOG.md` ledger 记录 subject digest 和 finding；整改后状态只能先到
  `FIXED_PENDING_REREVIEW`，只有后续 Re-review 可以改成 `CLOSED`。

## 确定性复审循环与 Task ID 分配

1. Review/Re-review `PASS` 时不创建整改 Task，下一许可动作才是本 Stage 的 Publish。
2. Review/Re-review `FAIL` 时，该评审 Task 只记录 digest、finding、verdict 与路由，然后结束；不得同 run 整改。
3. 优先启用本 Stage 同一 review Phase 中最早一对尚未使用的 `CONDITIONAL` Remediation/Re-review，
   将两者改为 `PENDING`；Publish 保持 `PENDING`。
4. 若没有未使用的条件 Task 对，则在同一 Stage、同一 review Phase 追加一对 Task。首个新编号是该
   `BSS-S<stage>-P<phase>` 已有三位数 Task suffix 的最大值加一，第二个再加一；前者固定为
   Remediation，后者固定为 Re-review。例如 P2 已有 `T001`–`T003` 时，只能追加 `T004/T005`。
5. ID 只追加、不复用、不重排；启用或追加 Task 后必须同步追溯表、ledger、Run Contract 与 manifest。
   唯一下一 Task 是新/启用的 Remediation；其状态只能先到 `FIXED_PENDING_REREVIEW`，随后才允许对应
   Re-review。
6. Re-review 再次 `FAIL` 时重复第 2–5 步。任一非 `CLOSED` finding 存在时不得进入 Publish 或下一 Stage。
