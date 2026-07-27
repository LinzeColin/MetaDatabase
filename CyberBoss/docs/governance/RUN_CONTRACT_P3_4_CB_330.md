# Run Contract — P3.4 / CB-330

## 1. 目标

在 Owner 锁定产品版本 `v0.0.0.5`、设计基线 `v0.0.0.4` 与既有
Private-Database / Cloudflare R2 / OCI 责任边界均不变的前提下，完成一个可复跑、
本地确定性的 Runtime SQLite 在线快照、对象副本模拟与隔离恢复薄层。

实现使用 Node 已内置的 `node:sqlite` `DatabaseSync.serialize()` 取得 SQLite
一致映像；它是本 Run 对冻结包中 `sqlite3.Connection.backup()` 的等价在线快照
实现，并由并发写入边界、`PRAGMA integrity_check` 和 logical digest 恢复测试证明。
它不复制活跃 DB/WAL 文件作为唯一备份，也不建立在线双写数据库。R2 与 OCI 仅可
写入明确传入的本地 simulator root，真实 R2/OCI SDK、HTTP、credential、timer 与
Provider 请求均不存在。

上游锚点是已关闭的 CB-320 closure
`202e99cee168f0a2fb618e22819bc350e7f5261c`。本 Run 只处理 P3.4 / CB-330；
下一原生节点为 CB-340。

## 2. TaskPack 与 Skill Router

- TaskPack：`v0.0.0.7`；ZIP SHA-256：
  `77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`。
- Task boundary Router 选择 `output-skill`，模式
  `NATIVE_IF_PRESENT_ELSE_EMBEDDED`，最多一个轻量 Skill body。
- 本机有该轻量 Skill，因此只加载一次其正文；若缺失仅允许冻结
  `machine/skill_microplaybooks.json` fallback，网络获取为 `false`；实际 Skill body load 为 `1`，
  不递归加载其它 Skill。
- 不加载 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究；没有
  真实时间等待。

## 3. 最小范围、唯一事实源与激活边界

- 唯一输入 policy 是既有
  `implementation-kit/config/identity-scope.policy.json`：R2 只能是
  `cyberboss-cold` / `ovh-singapore-vps-1/`，OCI 只能是 symbolic
  `oci-bucket-name` / `cyberboss-cold-backup/ovh-singapore-vps-1/`，且均禁止
  public access。不得创建第二个对象 scope、第二数据库或平行事实源。
- 备份只含 Runtime SQLite 与恢复需要的非秘密 `config_references`。普通 bundle
  明确排除 Codex auth、WeChat cookie/token、credentials、workspace cache 和
  build artifacts；快照、manifest、CLI 输出与 closure evidence 都扫描并拒绝
  private key、Bearer、GitHub/OpenAI/WeChat shaped secret 和绝对运行路径。
- manifest 固定为 `cyberboss.backup-manifest.v3`，包含 `source_commit`、
  `schema_version`、`created_at`、SQLite integrity、逐表 logical count/digest、
  archive SHA-256、R2/OCI state 与所有真实操作/LLM counter。写入采用临时目录、
  file fsync、目录 fsync 与 atomic rename；crash cut 只能留下无 bundle 或完整
  bundle。
- R2/OCI local receipt 只能是 `simulator_verified`，并明确
  `real_remote_receipt=false`、real Provider operations=`0`。只有真实远端 object
  hash、metadata 和隔离 restore receipt 三者齐全才可能使用 `verified`；本 Run
  没有这些证据，所以真实 R2 是 `hazard_blocked`、OCI 是
  `activation_pending`，绝不伪绿。
- Private-Database 不 clone、不读写真实数据；日频/重大事件同步和 Status 的真实
  publication 都仍为 `activation_pending`。不调用 Cloudflare Access/DNS/Analytics，
  不新增 macOS `launchd` 依赖，控制面与运维模型调用永久为 `0`。

## 4. 验收、输出与验证

映射 critical Oracle 为 `FA-AC-012`、`FA-AC-013`、`FA-AC-028`：

1. **FA-AC-012**：两个 SQLite handle 在确定性 serialize 边界执行写入；快照的
   `integrity=ok`、schema/table logical digest 固定，isolated restore digest 与
   manifest 完全相等，恢复不提升为运行库。
2. **FA-AC-013**：R2/OCI 两个 local simulator 对象都有冻结 prefix、archive/
   manifest hash 和 metadata 比对；collision fail closed；无真实 receipt 时只保留
   `activation_pending`/`hazard_blocked`，不将 simulator 作为真实远端验证。
3. **FA-AC-028**：敏感 Runtime image、scope drift、manifest/archive tamper、
   允许网络的 restore、无效 CLI 参数均 fail closed，且没有 secret、完整私聊或
   运行时绝对路径进入输出。
4. 在 credential-name-scrubbed 临时环境中运行模块测试、CLI 测试、syntax、既有
   frozen external-adapter fixture、`npm run check`、完整 App regression、identity/
   config、DAG、traceability、no-wait 与 TaskPack validation。

实施输出为 backup manifest、R2/OCI local simulator receipts 与 isolated restore
report；它们均是临时 fixture，不进入仓库，也不声明真实全云激活。

## 5. 允许修改与封口边界

实施阶段仅允许：

- `CyberBoss/app/src/services/backup/canonical-backup-runtime.js`
- `CyberBoss/app/scripts/canonical-backup-runtime.js`
- `CyberBoss/app/test/canonical-backup-runtime.test.js`
- `CyberBoss/tests/canonical-backup-runtime.test.js`
- 本 Run Contract 与 `CyberBoss/scripts/validate_cb330.py`

封口阶段仅允许 `CHANGELOG.md`、`README.md`、`HANDOFF.md`、
`machine/facts/task_state.json` 与
`docs/evidence/CB-330/{summary,subject}.json`。不变更任何产品、设计或
TaskPack 版本。

## 6. 风险、回滚与停止条件

- 真正 R2/OCI upload 必须在以后获得 Owner 授权、精确最小 write scope、真实对象
  metadata/hash 与隔离恢复 receipt 后另行执行；本 Run 不读取或保存这些 credential。
- 回滚是禁用未来 systemd timer（本 Run 不安装或启用 timer）、保留最后一个 local
  verified snapshot，并只隔离 hash 不同的对象；不删除最后好快照。
- 遇到 integrity/hash mismatch、secret 入备份、remote 无验证却标绿、SQLite
  非一致快照、真实 Provider mutation、Private-Database clone、macOS `launchd`、
  任何控制面/运维 LLM 调用、第二数据源或第二数据库，即停止并拒绝封口。
