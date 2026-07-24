# MooMooAU Task Pack v1.0.11 — T0703 可选 token 回显恢复候选

本包直接继承不可变 `v1.0.10`，不改变 `v1.0.1` 的 34 RQ、34 AC、58 Task、DAG、Kill
Criteria 或零误伤边界。T0702/S7AC-002 的 protected PASS 回执保持不变。

T0703 已真实执行三个不同 exact-main SHA 的 attempt 1。三次 authority gate 与 identity
cleanup 均通过，M3 job 均失败，且均未使用 GitHub rerun。后验只读核验观察到 private 仓新增
commit 0、MooMooAU Raw/Processed/Timeline 路径写入 0、Gmail Trash 新增消息 0、source
mutation 0。三个失败 head 均禁止 rerun 或 redispatch。

第三次失败仅公开 `GITHUB_APP_TOKEN` / `RESPONSE_SCOPE_REJECTED`，不声称日志未证明的精确远端
根因。固定在官方 GitHub OpenAPI commit
`5c88ff6bc3c36a12ccd69b8e0fee479b7202188a` 的 installation-token schema 只要求 `token` 与
`expires_at`；`repositories`、`permissions` 和 `repository_selection` 都是可选响应字段。

本 Run Contract 只授权一个新恢复候选：

1. 响应若提供 scope 回显，仍须逐项精确匹配目标仓与最小权限；
2. 响应若省略 repository 回显，必须用该 installation token 执行有界
   `GET /installation/repositories?per_page=2`，并证明总数和唯一 Repository ID 都精确匹配；
3. token 最长一小时有效期以有界 GitHub `Date` 响应头为参考，不以请求前客户端时钟误判；
4. 任一回显漂移、仓库探测失败、Date 不可信或 TTL 超限均销毁 token 并 fail closed；
5. 其他 authentication、authorization、transport、content boundary、Raw/Processed recovery、
   second verification 与 Trash 错误仍整次 fail closed；
6. 受控交付一个全新 exact candidate 到 `main`，随后只 dispatch 该 SHA 的 attempt 1 一次；
7. 最多一个确定性验证候选；Raw 与 Processed 均须 age 加密并从唯一 private remote 恢复；
8. 远端恢复后再次验证同一来源，只允许一次精确 `users.messages.trash`；
9. Timeline、T0704、Blue-Green、GA、schedule、最终验收和最终发布均不在本 Run Contract。

包构建时 T0703 protected Oracle 仍为 `FAILED`，新候选尚未运行。只有该新 exact candidate 的
aggregate-only protected receipt 可把 T0703/S7AC-003 提升为 PASS。
