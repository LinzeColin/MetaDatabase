# MooMooAU Task Pack v1.0.10 — T0703 App 安装恢复候选

本包直接继承不可变 `v1.0.9`，不改变 `v1.0.1` 的 34 RQ、34 AC、58 Task、DAG、Kill
Criteria 或零误伤边界。T0702/S7AC-002 的 protected PASS 回执保持不变。

T0703 已真实执行两个不同 exact-main SHA 的 attempt 1。两次 authority gate 与 identity
cleanup 均通过，M3 job 均失败；两次均未使用 GitHub rerun。后验只读核验观察到 private 仓新增
commit 0、MooMooAU Raw/Processed/Timeline 路径写入 0、Gmail Trash 新增消息 0、source
mutation 0。两个失败 head 均禁止 rerun 或 redispatch。

第二次失败的公开封闭边界是 `GITHUB_APP_TOKEN`；当时 M3 v1 公开诊断没有输出安全的安装令牌失败
分类，因此不声称更精确根因。Owner 随后确认 MooMooAU GitHub App 已安装并链接唯一 private 数据仓。

本 Run Contract 只授权一个新恢复候选：

1. 保留已通过测试的逐消息 `MessageMetadataUnverifiable` quarantine；
2. M3 与 T0702 一样捕获封闭 `InstallationTokenFailureClass`，不输出 App、installation 或 private
   仓标识；
3. authentication、authorization、transport、content boundary、global discovery、Raw/Processed
   recovery、second verification 与 Trash 错误仍整次 fail closed；
4. 复用 `moomooau-beta`、八项 exact Secret name 与 Owner 已确认的 App/private 仓链接；
5. 受控交付一个全新 exact candidate 到 `main`，随后只 dispatch 该 SHA 的 attempt 1 一次；
6. 最多一个确定性验证候选；Raw 与 Processed 均须 age 加密并从 private remote 恢复；
7. 远端恢复后再次验证同一来源，只允许一次精确 `users.messages.trash`；
8. Timeline、T0704、Blue-Green、GA、schedule、最终验收和最终发布均不在本 Run Contract。

包构建时 T0703 protected Oracle 仍为 `FAILED`，恢复候选尚未运行。只有该新 exact candidate 的
aggregate-only protected receipt 可把 T0703/S7AC-003 提升为 PASS。
