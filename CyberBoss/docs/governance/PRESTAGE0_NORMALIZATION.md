# Prestage 0 Normalization Record

## Source baseline

- TaskPack:
  `CyberBoss_FullCloud_MVP_TaskPack_v0.0.0.3_FINAL_20260726.zip`
- TaskPack SHA-256:
  `6ae91ee1f74b16e660f04d4d06cc744725cd97b9dc8d799c625186449fe3f178`
- Roadmap:
  `CyberBoss_FullCloud_ROADMAP_v0.0.0.3_20260726.md`
- Roadmap SHA-256:
  `22a0ef56caab67c95357d60a3a725947f28a2744cecc79e66cacf638de1707b1`
- ZIP integrity: 71 entries、60 files；原始双层 manifest 全覆盖且全部匹配。

## Owner decisions

| Decision | Canonical result |
|---|---|
| Repository | `LinzeColin/MetaDatabase/CyberBoss/`；禁止独立 repo |
| License | A1；`CyberBoss/` 为 AGPL-3.0-only 子树 |
| Upstream | 固定来源快照；保留法定归属，切断持续技术关系 |
| Workspace | B1；alias=`cyberboss`，默认只写 `CyberBoss/**` |
| Data | `Private-MetaDatabase`，`domain=CyberBoss`，免 clone client |
| Run size | 每个 Run 最多一个 TaskPack phase |
| Publication | PG-0–PG-5 全部通过前禁止 push/PR |
| Final cleanup | merge/PR/branch/worktree/prune/gc 全部完成才算交付 |

## Product scope preserved

- 6 internal Stages：S0–S5；
- 30 Tasks：CB-000–CB-540，每 Stage 5 个；
- 53 Acceptance Oracles；
- Product Stage 1 + Stage 2A；
- 单用户、文本、单 active job、OVH 全云、loopback Codex；
- durable inbox/job/outbox、可重建 SQLite spool、Timeline/Status、
  R2/OCI、确定性测试、请求数 Canary；
- Product Stage 2B/3 仍不属于当前 MVP；
- 无真实时间 Soak 或凭据等待 Gate。

## Governance corrections

1. 代码仓从原包拟创建的独立 `LinzeColin/cyberboss-cloud` 改为
   `LinzeColin/MetaDatabase` + `CyberBoss/`。
2. Task `CB-020` 不再创建仓库；改为验证同仓身份、B1 scope 和最小权限槽位。
3. 运行 release 从 MetaDatabase 固定 commit 的 `CyberBoss/` 子树构建；
   全量完成前使用本地 immutable artifact，不依赖中间 GitHub push。
4. 长期事实从旧 `Private-AgentDatabase/data/cyberboss/...` 改为
   `Private-MetaDatabase`、`domain=CyberBoss`。
5. 禁止 clone Private-Database；canonical adapter 使用
   `private_db_client.py` 协议及其 fake API/manifest 并发测试。
6. workspace 从已迁移的 `CodexProject` 改为 `MetaDatabase`，
   alias=`cyberboss`，写入 scope 默认 `CyberBoss/**`。
7. 上游及 Timeline 依赖改为固定本地 source bundle；禁止 `#main`、remote、
   submodule、自动同步和运行时下载。
8. 修复原包中不存在的 `CB-350`、`CB-360`、`PG-6` 引用，并按现有
   Task/Pass-Gate 重新校正模型评估映射。
9. 增加嵌套 AGPL、NOTICE、修改说明和 Corresponding Source 发布 Gate。
10. 增加全局 Task/PG reference validator 与禁止身份扫描。

## Explicit non-claims

- Prestage 0 没有导入或运行上游代码；
- 没有完成 `CB-000`；
- 没有验证 OVH、微信、Codex auth、Cloudflare、R2、OCI 或 status 集成；
- 没有部署；
- 没有 push、PR、CI、tag 或 release；
- PG-0–PG-5 均未开始。
