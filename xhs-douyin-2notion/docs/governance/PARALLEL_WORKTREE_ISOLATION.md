# Parallel Worktree Isolation — Owner Directive

## 目的

MetaDatabase 中其他子项目可能长期开发。x2n 不修改、不恢复、不暂存、不提交其他子项目的文件，也不把外部主树状态吸收进当前分支。并行继续的依据是 Git worktree 文件系统隔离和机器检查的路径零重叠，不是忽略脏状态。

## 默认与显式模式

- 默认模式仍要求 MetaDatabase 主工作树在 `main` 且 clean。
- Owner 已明确要求与长期外部开发隔离并行；只有显式传入 `--allow-external-main-dirty` 才启用并行隔离模式。
- 该参数不授权修改主树，也不把外部脏状态判为健康；它只证明外部状态不会污染本 Run。

## 并行隔离 PASS 条件

1. 当前工作目录必须是登记的 x2n Phase worktree/branch。
2. 当前 worktree 的 changed paths 必须位于 `xhs-douyin-2notion/`；唯一父级例外是根 README 单一项目索引改名。Owner 短名迁移期间，旧前缀只能出现为删除项，任何新增或修改都 FAIL。
3. 主工作树必须存在并保持 `main` 分支。
4. 主工作树中任何 dirty path 都不得等于或位于当前 x2n 路径；短名迁移期间也必须检查 Owner Change Event 登记的旧前缀，二者 overlap 都必须为 0。
5. Evidence 只记录外部 dirty path 数量与 overlap `0`，不得复制外部路径、diff 或内容。
6. 本 Phase 不 merge/rebase moving `main`，不使用主树文件作为输入；未来 Stage Review 在独立 Run 对 `origin/main` 做受控同步/冲突检查。

任一条件不满足即 FAIL。`--allow-external-main-dirty` 未显式传入时，主树有任意 dirty path 仍 FAIL。

## 风险与回滚

- 风险：外部主树违规长期存在、主分支推进导致未来集成冲突、误把容忍解释为健康。
- 控制：零重叠检查、当前 worktree changed-scope 检查、aggregate-only Evidence、Stage Review 前受控同步。
- 回滚：移除显式参数即可恢复严格 clean-main 门禁；不需要修改或清理任何外部项目。

## 非授权事项

- 不授权在 MetaDatabase 主树写文件；
- 不授权恢复、stash、commit 或删除 EEI/其他子项目改动；
- 不授权 push、Stage 1、真实账号或产品执行；
- 不改变“谁开的谁收”责任。
