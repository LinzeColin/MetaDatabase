# Source inventory and lineage

Canonical repository path：`Stock_Skill/stock-commercial-opportunities-skill/`。
The collection index `Stock_Skill/REGISTRY.json` declares `3.0.0` (v3) as current and treats v1/v2 as archive-only; its validator must agree with both `VERSION` files and the release hashes below.

| Version | Artifact | SHA-256 | Role |
|---|---|---|---|
| 1.0.0 | `archives/research-high-roi-content_codex-skill-task-pack_v1.0.0.zip` | `73f6934529b401a33271e8bc2f2bf7c89979a2dbb56e92e5abb4e8ff2fc40792` | 原始高 ROI 内容研究任务包 |
| 2.0.0 | `archives/commercial-opportunity-decomposition_codex-skill-task-pack_v2.0.0.zip` | `01c3d8b069d488cddb4fa3c85959a89bd9b5d072c4b1437cced03073e0442fc4` | 通用商业机会拆解任务包 |
| 2.0.0 | `archives/commercial-opportunity-decomposition_v2_research-summary.zh-CN.md` | 在 `BACKUP_MANIFEST.sha256` 中 | v2 研究与改进摘要 |
| 3.0.0 | `task-pack/` | 在 `task-pack/MANIFEST.sha256` 中 | 股票商业机会拆解可读源码 |
| 3.0.0 | `releases/stock-commercial-opportunities_codex-skill-task-pack_v3.0.0.zip` | `3cc89dc510e33c9e341c18e7925c219dda3218c7947f4341414f0c3cba2a0c6d` | 可移植发布包；canonical copy 同见 `releases/SHA256SUMS` |

## Public-safe posture

- v1/v2 解包扫描未发现 token、private key、email、会话文件、账户或客户原始数据。
- v1 含一个非敏感历史构建路径 `/home/oai/skills`；作为不可变谱系保留，不作为当前环境事实。
- v3 不包含本机 `/Users/...` 路径、Codex 会话、Memory、浏览器/账号状态或 GitHub token。
- 所有金融示例为合成 fixtures；不得当成真实投资机会或市场数据。
