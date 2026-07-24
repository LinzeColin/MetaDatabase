# MooMooAU Task Pack v1.0.8 — T0703 受保护执行包

本包直接继承不可变 `v1.0.7`，不改变 `v1.0.1` 的 34 RQ、34 AC、58 Task、DAG、Kill
Criteria 或零误伤边界。T0702/S7AC-002 的真实 protected PASS 回执保持不变。

本 Run Contract 只授权 T0703：

1. 受控交付精确候选到 `main`，但这不是最终发布；
2. 复用已验证的 `moomooau-beta` Environment、Beta config、单一 private 数据仓绑定与
   GitHub App；
3. 在既有六项 Secret 之外只增加 classification/parser 两项公开安全空注册表；
4. 空注册表不得伪造规则或 parser profile，只能生成显式 `SAFE_DEFERRED` Processed；
5. 最多处理一个确定性验证候选，完整 Raw 读取预算为 1；
6. Raw 与 Processed 都必须 age 加密写入唯一 private 仓，并从远端恢复验证；
7. 远端恢复完成后再次验证同一来源，只允许一次精确 `users.messages.trash`；
8. workflow 仅接受 owner、`main`、GitHub-hosted、attempt 1、exact SHA；
9. GitHub rerun、第二次 T0703 dispatch、Timeline、T0704、GA、schedule、最终验收和最终发布
   均不在本 Run Contract。

包构建时 T0703 protected Oracle 仍为 `NOT_RUN`。只有精确 first-attempt GitHub Actions
回执可把 T0703/S7AC-003 提升为 PASS；本地测试、授权或 elapsed time 都不能替代该回执。
