# MooMooAU Task Pack v1.0.9 — T0703 修复候选执行包

本包直接继承不可变 `v1.0.8`，不改变 `v1.0.1` 的 34 RQ、34 AC、58 Task、DAG、Kill
Criteria 或零误伤边界。T0702/S7AC-002 的 protected PASS 回执保持不变。

T0703 第一次 exact-main protected M3 attempt 已真实执行：authority gate 与 identity cleanup
通过，M3 job 失败。公开输出仅给出封闭通用失败码，未声称精确根因。只读后验核验观察到 private
仓新增 commit 0、Gmail Trash 新增消息 0、Processed write 0、source mutation 0；失败 head
`f747ddcd…` 禁止 rerun 或 redispatch。

本 Run Contract 只授权一个新修复候选：

1. 将已在 T0702 证明安全的逐消息 `MessageMetadataUnverifiable` 对齐到 M3 quarantine；
2. authentication、authorization、transport、content boundary、global discovery、recovery 等其他
   错误仍整次 fail closed；
3. M3 失败只输出固定枚举 phase，不接收或输出异常文本、邮箱字段、Secret 或 private 仓标识；
4. 复用已配置的 `moomooau-beta`、八项 exact Secret name 和已关联的单一 private 数据仓；
5. 受控交付一个新 exact candidate 到 `main`，随后只 dispatch 该新 SHA 的 attempt 1 一次；
6. 最多一个确定性验证候选；Raw 与 Processed 均须 age 加密并从 private remote 恢复；
7. 远端恢复后再次验证同一来源，只允许一次精确 `users.messages.trash`；
8. Timeline、T0704、Blue-Green、GA、schedule、最终验收和最终发布均不在本 Run Contract。

包构建时 T0703 protected Oracle 为 `FAILED`，修复候选尚未运行。只有新 exact candidate 的
aggregate-only protected receipt 可把 T0703/S7AC-003 提升为 PASS。
