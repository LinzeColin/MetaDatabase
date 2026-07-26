# Restore and verify

本文件定义当前 source/release 验证、Stage Publish proposed-tree replay 与最终 clean checkout 恢复。任何
source、release、SHA、manifest 或 registry 冲突都必须报告 `UNKNOWN`，不得用占位制品或计划命令冒充证据。

## 当前制品状态

机器版本：`0.0.0.1`；展示/release label：`v0.0.0.1`。

当前 source tree 必须同时具有：

- registry claim `bottleneck-serenity-skill=0.0.0.1`；
- `scripts/build_release.py`、`scripts/refresh_task_manifest.py`、`scripts/audit_license_similarity.py`、
  `scripts/validate_completion_audit.py`、`LICENSE_SIMILARITY_AUDIT.json` 与
  `COMPLETION_AUDIT.json`；
- `releases/bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip` 与 `releases/SHA256SUMS`；
- `task-pack/MANIFEST.sha256` 与 `BACKUP_MANIFEST.sha256`。

commit `e88f6afd1c025c32bf0ba4b0c3f6ff9250083335` 已完成 Stage 2 Publish；其 staged/latest-main replay 与
无凭据 HTTPS clean sparse clone 均恢复当时 sealed release SHA，remote/PR head 与两项 CI 通过。Stage 3
deterministic validation、Trigger eval、Security、Historical E2E、独立 Forward test 与整体 Review 随后在
本地完成并刷新 candidate DAG，但没有上传。T005 Re-review 2 verdict=`FAIL`：
`S3-R003`–`S3-R008` 中除 `S3-R001/R002` 外均已关闭；T005 复验确认 current v18 actual-return exact
replay、双 judge `24/24 PASS` 与 plain/ZIP public-safety gate 成立，但 company/URL presentation
变体及 allow/exclude-context 语义仍 fail open。T006 已补齐两个 presentation 面各 15 类 durable
negative、合法 role-neutral positive、四条 allowed/六条 excluded context 精确绑定与 post-execution
helper amendment。T007 Re-review 3 在 228-path/238-file frozen subject 上判定 `FAIL`：unknown
embedded/lowercase issuer 仍可穿透，合法 role-neutral prose/template 被误杀，v18 时序证据仅为
host-local，canonical/ZIP 各有 10 个 top-level `session` 对象，且许可发现面存在 target-count
冲突。T008 已完成五项整改。T009 在 244-path/254-file frozen subject 上独立重审后判定 `FAIL`：
`S3-R001/R002/R008/R009` 仍为 `OPEN`，新增 `S3-R011`；`S3-R010` 已关闭并恢复
`ACC-S2-010`。T010 已把五项 finding 推进为 `FIXED_PENDING_REREVIEW`；T011 随后在
269-path/279-file frozen subject 上独立重审并判定 `FAIL`：未知 issuer presentation、合法
role-neutral prose、私有 metadata 同义键、provider provenance 真实性及 README legacy file-count
许可口径仍有五项未关闭缺口；`S3-R011` 追溯问题已关闭。T012 已补齐共享 presentation Oracle、
需要 T013 现场执行的 v23 provider-generation protocol、semantic private-metadata safety gate 与
README owner-facing count Oracle。T013 现场 v23 provider-generation 与四仓 fresh full-history
复验关闭 `S3-R002/R010`；但新鲜呈现与 private-metadata 泛化探针使 `S3-R001/R008/R009` 保持
`OPEN`，Re-review 6 verdict=`FAIL`。T014 已用独立冻结 `223/223` presentation 盲测与
29-case/58-surface public-safety 盲测完成整改；三项 finding 仅为 `FIXED_PENDING_REREVIEW`。
T015 在 277-path/287-file 新双 digest subject 上独立重审仍判 `FAIL`：presentation 新 blind set
仅 `66/100` binary、`62/100` strict，public-safety 新 48-case/96-surface set 仅 `78/96`；
`S3-R001/R008/R009` 回到 `OPEN`。T016 已补齐 bounded presentation slots 与
neutral-container private-metadata ancestry；175/85/58 presentation durable matrices 及 T015
已知 public-safety case/plain-ZIP controls 均通过。T017 在 278-path/288-file 新双 digest subject
上独立重审仍判 `FAIL`：presentation 第九组仅 `67/100` binary、`62/100` strict，public-safety
72-case/144-surface set 仅 `67/72` / `134/144`，current-tree v23 live witness 也因 provider
usage limit 缺少 exact return/host replay。T018 已补齐 presentation comparison/noun-source/
on-upon/inline-designation 语义、public-safety 结构层/public-reference/plaintext 边界，并在 current
30-file production-only projection 中取得 fresh live exact return 与 host replay PASS。
T019 在 289-file Task Pack / 28-path Stage source 新双 digest subject 上独立重审仍判 `FAIL`：
presentation 每面仅 `144/216` binary、`99/216` strict；public-safety 84 个 plain/ZIP 判定仅
`72/84`。current-tree v23 fresh live witness 以 28,010-byte exact return 与 host replay PASS，
因此 `S3-R002` CLOSED；`S3-R001/R008/R009` 为 `OPEN`。T020 已将 T019 的
192 REJECT / 24 ACCEPT presentation set 与 42-case public-safety set 固化为 durable controls；
source presentation `216/216`、public-safety plain/ZIP `84/84` 均通过，rollback mutants 也分别
恢复漏检或误杀。T021 在 290-file Task Pack / 30-path Stage source 上独立重审仍判 `FAIL`：
presentation 每面仅 `214/282` binary、`144/282` strict；public-safety 64 个 plain/ZIP 判定仅
`50/64`；README 与 LICENSE 的 280-file prose 又与 canonical 282-target report/marker 冲突。
T022 已将该 presentation 冻结集修至 source/release 每面 `282/282` strict，将 public-safety
冻结集修至 `64/64`，并把四份 owner-facing current claims、collector 与 full-history report
统一为 283 targets；对应 mutants 均被杀死。T023 随后在 291-file Task Pack / 32-path Stage
source 新双 digest subject 上独立重审并判定 `FAIL`：presentation fresh set 每面仅
`286/408` binary，public-safety 108 surfaces 仅 `84/108`，current-tree v23 live host exact
replay exit=`1`。因此 `S3-R001/R002/R008/R009` 为 `OPEN`、`ACC-S3-002/006` FAIL、
`ACC-S3-009=FAIL_EVIDENCE`；283-target exact set 与四仓 full-history 重算 PASS，故
`S3-R010` `CLOSED`、`ACC-S2-010` PASS。唯一下一 Task 是
`BSS-S3-P3-T024 — Remediation 12`。T024 随后用 18×31=`558/558` exact presentation、
5 个特殊 legal-name case、16 个 role-neutral controls、`172/172` frozen 与 `44/44` fresh
public-safety plain-ZIP matrices完成四项整改；current binding、stored Forward 与 T023 exact
output 的 current presentation/host replay PASS。fresh live 两次尝试均按 1,800 秒合同 fail-closed
timeout，未被冒充为 closure evidence；current license set/report/markers 为 284 targets。
`S3-R001/R002/R008/R009` 仅为 `FIXED_PENDING_REREVIEW`。T025 随后按用户“不复审、避免 live
time-soak”指令完成机械 Acceptance closure：不启 reviewer、不修改功能实现、不声称 live PASS；
frozen 双 digest、T024 已知失败样本、stored independent Forward、current binding/witness controls
与完整自动门全部通过。四项 finding 已关闭，Stage 3 acceptance verdict=`PASS`。T001 随后按用户
“中间 phase 完成不需要上传”的指令执行 local-seal Publish：从 accepted frozen source 重建
license/manifest/release/registry/backup DAG，并在 staged proposed tree 与全新 clean replay 全门一致后
创建本地 seal commit。Stage 4 Audit 随后对 39 Source IDs、44 ACC、82 Tasks、36 findings 与 11 项
仓库/用户规则完成 A/B-only exact-set 验证；当前 Source=`32 satisfied + 7 terminal-pending`，
ACC=`38 satisfied + 6 not-due`，C/MISSING=`0`。该证据不证明 push、PR/CI、merge 或 runtime 安装；
T002 Release readiness 随后从当时 `origin/main` 构造 39-path allowlisted overlay candidate，并在
worktree 与独立 clean Git restore 通过 245 tests、public-safety `378/795/417`、license
`284/2,485/0/5/1`、291-entry manifest、双 deterministic build 与三 SHA consumer 检查。Mechanical
final gate 又在 `origin/main=d10f5086…` 的最新 upstream-safe overlay candidate 上完成同等全门复验，
ledger=`36/36 CLOSED`；未启 reviewer/live provider。唯一下一 Task 是
`BSS-S4-P3-T001 — Publish`；最终上传仍由该 Task 负责。

## 从 GitHub 恢复 source project

最终合并后，用无凭据 HTTPS sparse clone 恢复：

```bash
restore_root=$(mktemp -d)
git clone --filter=blob:none --sparse https://github.com/LinzeColin/MetaDatabase.git "$restore_root/MetaDatabase"
cd "$restore_root/MetaDatabase"
git sparse-checkout set --skip-checks Stock_Skill .github/workflows/stock-skill-validation.yml AGENTS.md README.md LICENSE
git checkout <sealed-commit>
```

`<sealed-commit>` 必须替换为实际合并/封印 commit；不得使用未经记录的 moving branch 代替验收基准。

## 当前可执行的 source 验证

从仓根执行：

```bash
test "$(tr -d '\n' < Stock_Skill/bottleneck-serenity-skill/VERSION)" = "0.0.0.1"
test "$(tr -d '\n' < Stock_Skill/bottleneck-serenity-skill/task-pack/VERSION)" = "0.0.0.1"

python3 -B Stock_Skill/scripts/validate_registry.py
python3 -B Stock_Skill/bottleneck-serenity-skill/scripts/audit_license_similarity.py --verify-targets
python3 -B Stock_Skill/bottleneck-serenity-skill/scripts/validate_completion_audit.py --check

SKILL=Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill
python3 -B "$SKILL/scripts/validate_skill.py" "$SKILL"
python3 -B "$SKILL/scripts/validate_trigger_evals.py"
python3 -B "$SKILL/scripts/validate_security_evals.py"
python3 -B "$SKILL/scripts/validate_historical_e2e.py"
python3 -B "$SKILL/scripts/validate_forward_test.py"
python3 -B -m unittest discover -s "$SKILL/tests" -p 'test_*.py' -v
python3 -B Stock_Skill/scripts/run_unittests.py
python3 -B Stock_Skill/scripts/validate_public_safety.py
python3 -B Stock_Skill/bottleneck-serenity-skill/scripts/refresh_task_manifest.py --check
```

还必须执行 `.github/workflows/stock-skill-validation.yml` 中全部四个原始 `run` blocks，不能用近似命令替代；
其中 hash block 会验证所有 task manifests 与 `SHA256SUMS` 的 canonical path、声明集合和实算 SHA。

Registry validator 必须同时输出既有 `stock-commercial-opportunities=3.0.0 (v3)` 与
`bottleneck-serenity-skill=0.0.0.1 (v0.0.0.1)`；缺任一项均不得继续恢复。

`--verify-targets` 是无网络快速门：它验证冻结算法/四仓 metadata、报告内部计数，并要求报告动态列出的
<!-- CURRENT_LICENSE_TARGET_COUNT=284 -->
284 个
canonical path、SHA-256 与 byte count 精确等于 current tree。许可重审或最终验收还必须提供四个无凭据、
非 shallow 的完整 clone，用各自 `NAME=PATH` 传给四个 `--upstream`，再运行 `--verify-report`；审计器逐仓
验证 public origin、冻结 commit、LICENSE/COPYING history，扫描该 commit 全部可达 Git blob，并要求重算
结果与 committed report byte-identical。clone 只作外部只读证据，路径和上游文本不得写入报告或仓库。

T007 记录的 owner-facing target-count 冲突已由 T008 统一为 committed report 的 current count，并由
durable 文档一致性 Oracle 约束；T009 已独立关闭 `S3-R010`，`ACC-S2-010` 恢复 PASS；T010 current
canonical count 当时为 `271`；T012 加入 presentation Oracle 与 live-witness protocol 后，current count
为 `278`，四仓完整历史结论仍为 exact/four-line/token20=`0/5/1`。

## Proposed-tree replay（Stage Publish）

只有适用的 Stage acceptance gate PASS、ledger 零未关闭 finding、全部 Stage source 已稳定后才能执行；
Stage 4 按用户当前指令使用 mechanical gate/revalidation，不启 reviewer：

1. 将完整候选变更加入 index，并确认没有 unmerged 或 intent-to-add entry。
2. 记录 `proposed_tree=$(git write-tree)`；该 tree 是拟提交字节真源，不是工作区近似值。
3. 物化到新临时目录：

   ```bash
   replay_root=$(mktemp -d)
   git archive --format=tar "$proposed_tree" | tar -xf - -C "$replay_root"
   cd "$replay_root"
   ```

4. 在该目录重放 source 验证、四个 workflow 原始 run blocks、两次 clean release build、`--verify`、registry
   validator、task/backup manifests 与公开安全扫描。
5. 两次 build 的 ZIP bytes/SHA 必须相同；任何 source/index 变化都会使 replay seal 失效，必须重新开始。

禁止在 Stage Review 前 staged/push，也禁止把 proposed-tree replay 结果写回已封印 release 输入形成自引用。

## Candidate/sealed release 重建

Release/Activate Task 必须实现以下固定入口：

```bash
cd Stock_Skill/bottleneck-serenity-skill
python3 -B scripts/build_release.py
python3 -B scripts/build_release.py --verify
```

默认输出必须是：

```text
releases/bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip
```

ZIP 只能包含已封印 `task-pack/`，唯一 top-level root 为
`bottleneck-serenity-skill-task-pack-v0.0.0.1/`；entry order、timestamp、compression、mode、type 与 file set
必须逐项符合 `task-pack/02_ARCHITECTURE_DATA_API.md` 的 deterministic release contract。

验证时必须实算并比较同一个 release SHA：

1. release ZIP bytes；
2. `releases/SHA256SUMS` 对应行；
3. `Stock_Skill/REGISTRY.json` 新 entry 的 `release.sha256`；
4. `BACKUP_MANIFEST.sha256` 中 release entry。

其中 task manifest 只覆盖 release 输入，不得保存 Root 外 release SHA；backup manifest 覆盖 outer project 且
排除自身，必须最后生成。任一缺失、重复、不一致、越界或占位值都失败。

维护者只有在六个发现面和全部 project source 已稳定、默认 build 已重建当前 ZIP 后，才可运行
`python3 -B scripts/build_release.py --activate` 刷新三个 SHA 消费面并最后生成 backup manifest。普通验证和
恢复不应重写 activation；只需默认 build 后运行 `--verify`，相同 source 必须得到相同 bytes/SHA。

## 最终干净 sparse-checkout 验收

最终 commit 合并后，在全新的 sparse clone 中重复：

1. checkout 精确 sealed commit；
2. source 验证与四个 workflow 原始 run blocks；
3. `python3 -B scripts/build_release.py` 连续两次；
4. `python3 -B scripts/build_release.py --verify`；
5. release SHA 四消费面、task/backup manifests、registry 与 canonical Skill hash 对比。

proposed tree 与最终 clean checkout 的 release ZIP、manifest 集合、registry projection 和 canonical source hashes
必须全部相等，才能完成 `ACC-S2-011`。恢复成功只证明源码/制品完整与可重建，不代表本机安装、隐式触发、
实时事实、投资结论或交易系统可用。
