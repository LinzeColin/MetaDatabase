# Run Contract — P5.4 / CB-530

## 1. 目标

关闭原生任务 `CB-530`：在已验证的 Linux OVH deployment 上建立一次真实、可恢复的
Runtime SQLite 在线快照，并将同一不可变 snapshot 以固定 scope 写入 Cloudflare R2 与
OCI cold backup；通过 R2 精确对象读回的隔离恢复、OCI provider receipt、可执行的
Linux operator commands 和完整 handover 形成可复跑证据。

产品版本固定为 `v0.0.0.5`，设计基线固定为 `v0.0.0.4`，TaskPack 固定为
`v0.0.0.7`（ZIP SHA-256
`77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`）。上游
closure 是 `CB-520` 的 `1e0ed85c`；本 Run 结束后才可进入 `CB-540`。

## 2. TaskPack Router 与禁止项

- CB-530 boundary Router 的选择是 `output-skill`，模式
  `NATIVE_IF_PRESENT_ELSE_EMBEDDED`，最多一个 lightweight Skill body。
- 本机没有该 native body；只使用冻结的
  `machine/skill_microplaybooks.json` 路径，网络获取为 `false`、递归深度为 `0`、
  实际 Skill body loads 为 `0`。
- 不加载 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究；不创建
  等待节点、不使用 sleep/观察期，也不调用控制面或运维模型。

## 3. 最小范围与执行合同

1. **本地 source（可能修改）**：仅新增可测试的 CB-530 backup/restore protocol、
   Linux systemd unit、focused tests、Run Contract 和 closure evidence/validator。
   不修改 `docs/product_design/v0.0.0.4/**`、TaskPack 或产品版本。
2. **OVH release**：从该 source commit 构建新的 immutable release；`current` 指向
   新 release，`previous` 保持已接受的 CB-520 release。绝不编辑已发布 release。
3. **Runtime DB**：只在缺失时用既有 Runtime spool schema 初始化
   `/var/lib/cyberboss/runtime.db`；不读或备份 Codex auth、WeChat state、workspace cache、
   prompt/result 或 Private-Database payload。在线 snapshot 仍使用既有
   `node:sqlite` serialize 逻辑，必须通过 integrity、archive hash 和 logical digest。
4. **R2**：仅允许 account 内固定 bucket `cyberboss-cold` 和固定 prefix
   `ovh-singapore-vps-1/snapshots/`。若 bucket 不存在，只创建这一冻结名称一次；对象
   只可使用新 backup id 写入 `runtime.sqlite3` 与 `manifest.json`，不得 delete、list
   全局对象、overwrite 或创建第二 bucket。R2 readback 只可读取刚刚写入的精确 key，
   并在 network-disabled isolated restore 中验证 hash/integrity/logical digest。
5. **OCI**：只使用已存在的 root-only write PAR，且只 PUT 到
   `cyberboss-cold-backup/ovh-singapore-vps-1/snapshots/` 下的新 key；不 create/delete
   bucket、不 list、不 overwrite。写回 HTTP receipt/ETag 与本地 SHA-256 必须记录为
   脱敏 evidence。若 PAR 的精确 GET 读回未获授权，保持
   `oci_readback=activation_pending_write_only_par`，绝不把它写成 restore PASS；R2
   readback 是本 Run 的真实 isolated restore Oracle。
6. **持久化**：只安装 Linux `cyberboss-backup.service` + timer；它读取 root-owned
   credential slots，不依赖 macOS 或 launchd。单次 oneshot 只能生成一个 snapshot，
   失败不会删除 last-known-good local/remote backup。
7. **唯一事实源**：不 clone Private-Database，不新建仓库/数据库/Status 产品。备份对象
   是已批准的 R2/OCI disaster-recovery copy，不是业务事实源。

## 4. 验收与验证命令

映射 `FA-AC-012`、`FA-AC-013`、`FA-AC-024`、`FA-AC-029`、`FA-AC-031`：

- focused Node tests、`npm run check`、完整 App regression；
- source/evidence privacy scan、frozen manifest hashes、TaskPack DAG/router validation；
- OVH `systemd-analyze verify`、oneshot start、timer enabled、release current/previous
  pointer、loopback status/Access continuity；
- exact R2 runtime+manifest object PUT/GET and SHA-256 comparison，随后 isolated restore；
- exact OCI runtime+manifest object PUT receipt，失败只降级该 provider state；
- operator start/stop/diagnose/backup/restore/rollback commands 均以真实 exit result
  绑定到 closure Subject，用户可见说明默认中文。

## 5. 风险、回滚与停止边界

- 回滚只切回已验证 `previous` release、disable new backup timer，并保留所有已有
  immutable backup；不删除 remote object、bucket 或 last-good snapshot。
- 任一 scope drift、secret/PII 入 bundle/evidence、remote hash mismatch、restore
  promoted、对象 overwrite/delete、Private-Database clone、非 Linux systemd、Mac
  launchd、或任一 LLM counter 非零，均 fail closed，保留精确 pending/failure receipt。
- 真实微信凭据缺失仍是 channel pending，不能影响 backup/restore 真值，也不能被
  转换为成功的 E2E claim。
