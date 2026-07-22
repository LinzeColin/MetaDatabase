# Run Contract — RUN-X2N-S01-F002

## 目标

执行唯一 DAG Task `TSK.x2n.foundation.002`：在任何数据库、Native Host、平台
Adapter 或 Sink 实现之前，冻结 `1.0` 版本化 IPC、Canonical、Artifact、Taxonomy、
Sink、Health、Provenance 与 Error Contract，并建立 Python/TypeScript/JSON Schema
三平面对等和 Fail Closed 验证。

## 最小范围

- 只修改 `xhs-douyin-2notion/**`，继续使用现有 Stage 1 隔离 worktree。
- 新增严格 Pydantic models、生成的 JSON Schemas/TypeScript types、错误码 Registry、
  合成 fixtures、精确 dependency locks、NOTICE/SBOM、测试与紧凑证据。
- 所有对象 `schema_version=1.0`；未知版本、动作和字段拒绝，禁止静默兼容。
- 平台媒体只能表示为不透明 `ephemeral_media_ref_id`，Contract 中不存在媒体 URL、
  Header、Cookie、Token、Shell、任意本地路径或任意代理 URL 输入。
- 不读取、显示、使用或修改共享认证材料、全局 Git 配置、其他项目或长期开发目录。

## 非范围

不创建 SQLite Schema/Migration、DB 唯一约束、Native Host Manifest/进程、真实 Job
Ledger、Local API、Side Panel 行为、平台 Adapter、Markdown/Notion 写入、模型或媒体
处理；不执行真实账号、浏览器、平台、Notion、模型或媒体动作。上述产品 Oracle
继续标记 `DOWNSTREAM_NOT_RUN`。

## 验收

1. `ACC.x2n.ext.003` 当前 Contract 范围：Origin 无通配符；未知 Origin/动作/字段/
   版本、超限消息、Shell/Path/任意 URL 注入全部拒绝；重复 `request_id` 的稳定策略
   是相同 Hash 返回既有 Job、冲突 Hash 拒绝。真实 Host/Job Count 留待下游。
2. `ACC.x2n.data.001` 当前 Contract 范围：`content_key`、`relation_key`、
   `artifact_key`、`sink_key` 确定性校验，Artifact 明确 append-only。SQLite FK、
   Migration、`PRAGMA integrity_check` 留待 foundation.003。
3. `ACC.x2n.data.003` 当前 Contract 范围：合成 Markdown/Notion Provenance 必须从
   最终节点连通 Canonical、Observation、Adapter、Artifact、Classification 与 Run；
   真实 Sink/Canary 留待下游。
4. Pydantic round-trip、JSON Schema 生成 `--check`、TypeScript strict compile、错误
   Registry 完整性、Public Fixture 安全边界和所有历史测试通过。
5. 精确锁定并登记全部 Runtime/Build 依赖；install script 为 0，Repo/证据不含
   Private Runtime、Secret、媒体 CDN URL 或本机绝对路径。

## 风险、回滚与停止条件

- Python/TypeScript/Schema 漂移、未知字段被接受、依赖/License 未登记、Acceptance
  被错误宣称为产品 PASS、或 Stage 1 中途上传，均立即 Fail Closed。
- 若 Contract 不能在零持久化媒体 URL 下表达临时媒体引用，或任何破坏性语义仍有
  歧义，则停止，不进入 foundation.003。
- 回滚为 revert 本 Task 的单一未上传 commit，恢复前一 Contract 版本并标记需要迁移；
  本 Run 没有数据迁移或外部状态需要恢复。

## 验证命令

```bash
python3.12 -B scripts/verify_foundation_002.py --verify-worktree --allow-external-main-dirty
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

本 Task 完成后只允许本地 commit；Stage 1 必须等待 G1 Review/Fix/Re-acceptance 后
才可 push。
