# Restore and verify

本文件定义当前 source/release 验证、Stage Publish proposed-tree replay 与最终 clean checkout 恢复。任何
source、release、SHA、manifest 或 registry 冲突都必须报告 `UNKNOWN`，不得用占位制品或计划命令冒充证据。

## 当前制品状态

机器版本：`0.0.0.1`；展示/release label：`v0.0.0.1`。

当前 source tree 必须同时具有：

- registry claim `bottleneck-serenity-skill=0.0.0.1`；
- `scripts/build_release.py`、`scripts/audit_license_similarity.py` 与 `LICENSE_SIMILARITY_AUDIT.json`；
- `releases/bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip` 与 `releases/SHA256SUMS`；
- `task-pack/MANIFEST.sha256` 与 `BACKUP_MANIFEST.sha256`。

这些制品证明 Stage 2 candidate activation，不提前证明 GitHub Publish、merge 或 runtime 安装。T005 已在
新双 digest subject 上关闭机器接口 finding `S2-R001`；许可 finding `S2-R002` 与 ledger 25/25 均为
`CLOSED`，Stage 2 Review verdict=`PASS`。最终 sealed release 仍须由下一 Task P5 Publish 从复审通过的
frozen source 重建，并完成 staged/proposed-tree 与最终 clean-checkout 恢复证据。

## 从 GitHub 恢复 source project

最终合并后，用无凭据 HTTPS sparse clone 恢复：

```bash
restore_root=$(mktemp -d)
git clone --filter=blob:none --sparse https://github.com/LinzeColin/MetaDatabase.git "$restore_root/MetaDatabase"
cd "$restore_root/MetaDatabase"
git sparse-checkout set Stock_Skill .github/workflows/stock-skill-validation.yml AGENTS.md README.md LICENSE
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

SKILL=Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill
python3 -B "$SKILL/scripts/validate_skill.py" "$SKILL"
python3 -B -m unittest discover -s "$SKILL/tests" -p 'test_*.py' -v
python3 -B Stock_Skill/scripts/run_unittests.py
python3 -B Stock_Skill/scripts/validate_public_safety.py
```

还必须执行 `.github/workflows/stock-skill-validation.yml` 中全部四个原始 `run` blocks，不能用近似命令替代；
其中 hash block 会验证所有 task manifests 与 `SHA256SUMS` 的 canonical path、声明集合和实算 SHA。

Registry validator 必须同时输出既有 `stock-commercial-opportunities=3.0.0 (v3)` 与
`bottleneck-serenity-skill=0.0.0.1 (v0.0.0.1)`；缺任一项均不得继续恢复。

`--verify-targets` 是无网络快速门：它验证冻结算法/四仓 metadata、报告内部计数，并要求报告列出的 39 个
canonical path、SHA-256 与 byte count 精确等于 current tree。许可重审或最终验收还必须提供四个无凭据、
非 shallow 的完整 clone，用各自 `NAME=PATH` 传给四个 `--upstream`，再运行 `--verify-report`；审计器逐仓
验证 public origin、冻结 commit、LICENSE/COPYING history，扫描该 commit 全部可达 Git blob，并要求重算
结果与 committed report byte-identical。clone 只作外部只读证据，路径和上游文本不得写入报告或仓库。

## Proposed-tree replay（Stage Publish）

只有 Stage Review/Re-review PASS、ledger 零未关闭 finding、全部 Stage source 已稳定后才能执行：

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
