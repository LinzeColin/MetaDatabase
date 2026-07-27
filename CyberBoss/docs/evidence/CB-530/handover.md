# CB-530 交接收据

P5.4 已将 final immutable release、R2/OCI backup、R2 isolated restore、每日 Linux
timer、Cloudflare Access continuity、Status refresh 与 no-clone Private-Database sync
绑定到同一份脱敏 closure。产品版本固定为 `v0.0.0.5`，设计基线仍是 `v0.0.0.4`。

当前 release 为 `25670bf32c6d27e3668fcf59bc9ab754035e161d`，完整 source archive
SHA-256 为 `2673993b0ced81ae6fe7878dcb5cf220f622d7a4e713261d5421bbb69e711d0b`；
有效 `previous` release 已保留，供已有 rollback contract 使用。

`backup_5233145600b2b004151de2bb` 是本 Run 的最新可恢复点。R2 的 runtime 和
manifest 两个精确对象均已 PUT/GET 哈希匹配，并在 network-disabled、non-promoted
位置完成 SQLite integrity/logical digest 恢复。OCI 两个对象的 PUT/ETag/metadata 已
实测；日常 write-only PAR 的读回保持明确 pending。为确认灾备副本与 R2 snapshot
字节一致，Owner 临时 ObjectRead PAR 对本次 runtime 对象进行一次 SHA-256 读取后已撤销，
它不改变日常权限模型。

后续原生节点是 `CB-540`。仍未解决的非本节点项是：真实 WeChat credential、最小 Access
service-token scope、Analytics 与自动 tunnel/self-heal。它们均保持明确 pending，不影响
已验证 backup/restore 的真值，也不构成 `FORMAL_FINAL_ACCEPTANCE`。
