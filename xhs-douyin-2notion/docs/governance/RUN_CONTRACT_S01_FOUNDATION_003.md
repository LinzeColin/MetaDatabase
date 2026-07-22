# Run Contract — RUN-X2N-S01-F003

## 目标

执行唯一 DAG Task `TSK.x2n.foundation.003`：把已冻结的 `1.0` Canonical Contract
落为仓库外 Private Runtime、SQLite WAL Canonical Store、可前进/降级的 Migration、
Outbox/Lease、Backup/Restore 与启动恢复原语。SQLite 是唯一真相源；本 Run 不实现
任何浏览器、平台或 Sink 副作用。

## 最小范围

- 只修改 `xhs-douyin-2notion/**`，继续使用既有 Stage 1 隔离 worktree；Task base
  固定为 `ae17e377090ef3bc1123d2512cda0daef9efe1cb`。
- `X2N_DATA_ROOT` 必须精确解析为
  `${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion`，且位于 Git 外；没有默认目录、
  任意路径参数、符号链接逃逸或对下载父目录其他条目的读取/导入。
- Runtime 根和所有目录保持 Owner-only；DB、WAL/SHM、Backup 和私有 marker 不得
  进入 Repo、Build、Evidence 或命令输出。
- SQLite 启用 WAL、FK、busy timeout 和完整性检查；Schema 覆盖 Content、Relation、
  Observation、Artifact、Taxonomy、Classification、Checkpoint、Request Ledger、
  Outbox、Sink Receipt、Notion Mapping 与 Media Lease 的持久边界。
- Artifact/Observation/Classification/Receipt 采用追加语义；一级分类只能由 Owner
  Contract 写入；Content/Relation/Outbox 以稳定唯一键实现重复无副作用。
- 迁移降级前强制生成并验证本地恢复备份；Restore 必须校验备份 Hash、Schema、
  `integrity_check` 与逻辑记录摘要后再原子替换。
- 使用纯合成、无账号、无 Secret、无媒体 URL、无本机路径的 80 条和 10k 规模输入
  验证幂等、并发、Migration 与恢复。

## 非范围

不实现 `TSK.x2n.foundation.004` 的 MV3 Side Panel、Native Host、Local API 或真实
Job Worker；不访问真实账号、浏览器、六平台、Notion、模型或媒体；不渲染 Markdown，
不写真实 Sink，不下载或导入 MediaCrawler/Crawler 输出，不触碰共享认证材料、全局
Git 配置、其他子项目或长期开发 worktree。

## Acceptance 解释

1. `ACC.x2n.data.001`：本 Run 完成 SQLite Schema/FK/Unique/append-only、零 orphan
   和 `PRAGMA integrity_check=ok`，从 Contract-only 推进为 Store scope PASS。
2. `ACC.x2n.data.002`：80 条合成 Canonical 输入连续两次及 100 个并发重复请求新增
   重复 Content/Relation/Artifact/Outbox 均为 `0`；Markdown、Notion 和 Owner Alpha
   80 仍为下游 `NOT_RUN`，不得冒充端到端产品 PASS。
3. `ACC.x2n.data.004`：10k 合成 DB 完成 Backup、Forward、Backward、Restore、损坏/
   Hash mismatch 故障注入与兼容读取，数据丢失和不可读记录均为 `0`。同盘 Backup
   只证明本地恢复能力，不冒充异地灾备或 Release Gate。

## 验证命令

```bash
python3.12 -B scripts/verify_foundation_003.py --verify-worktree --allow-external-main-dirty
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Owner 私有空库初始化只有在上述合成/Chaos 验收通过后才运行，并只输出聚合状态：

```bash
X2N_DOWNLOAD_DESTINATION="$X2N_DOWNLOAD_DESTINATION" \
X2N_DATA_ROOT="$X2N_DATA_ROOT" \
PYTHONPATH="apps/companion/src:packages/contracts/src" \
python3.12 -B -m x2n_companion.runtime_cli init
```

## 风险、回滚与停止条件

- 根目录位于 Repo 内、解析关系不精确、任一目录为符号链接、权限不满足 Owner-only、
  Migration 无已验证降级/恢复、DB/WAL/SHM 或本机路径进入 Git 时立即 Fail Closed。
- Duplicate conflict、FK orphan、Artifact 覆盖、未备份降级、备份 Hash/完整性不匹配、
  部分事务或恢复后逻辑摘要变化均阻断 Task 完成。
- 代码回滚为 revert 本 Task 单一未上传 commit；当前 Owner DB 是零内容 Schema 空库，
  不声称已有 Owner 灾备副本，也不自动删除。若需降级，必须先现场生成并验证 Backup
  后再迁移；既有 Owner input/recovery 文件和父目录其他条目不变。
- 本 Task 完成后只允许本地 commit；Stage 1 必须等待 Foundation004–005 与 G1
  Review/Fix/Re-acceptance 全部通过后才可 push。
