# ABD Gmail Token Storage｜S06/P01

本文件定义 Gmail OAuth token 的最小存储合同。它不含 token、client secret、真实 recipient、真实主机路径、授权链接或账户资料；这些值不得进入 Git、日志、JUnit、Evidence、命令历史或本仓库。

## 机器可读合同

```json
{
  "contract_id": "ABD-GMAIL-TOKEN-STORAGE-S06-P01",
  "schema_version": "1.0.0",
  "backend": "AGE_CLI",
  "ciphertext_format": "age-encryption.org/v1",
  "age_binary": "ABSOLUTE_TRUSTED_HOST_PATH_OUTSIDE_REPOSITORY",
  "recipient": "RUNTIME_PUBLIC_RECIPIENT_OUTSIDE_REPOSITORY",
  "identity": "HOST_SECRET_OUTSIDE_REPOSITORY",
  "token_path": "OUTSIDE_REPOSITORY_RUNTIME_SECRET_PATH_WITH_AGE_SUFFIX",
  "required_file_mode": "0600",
  "repository_token_write": "PROHIBITED",
  "private_database_raw_token_write": "PROHIBITED",
  "ephemeral_state_and_pkce": "SERVER_SIDE_SINGLE_USE_MEMORY_ONLY",
  "encryption_failure_action": "DISABLE_GMAIL_CONTINUE_CORE",
  "real_time_soak_required": false,
  "core_deployment_wait_behavior": "NONE_GMAIL_REMAINS_DISABLED_UNTIL_IMMEDIATE_GATES_PASS",
  "runtime_claim": "IMPLEMENTED_INTERFACE_NOT_RUNTIME_TOKEN_PROOF"
}
```

## 即时门与上线行为

Gmail 模块的启用只依赖可即时复核的门：精确 `gmail.modify` scope、一次性 `state`、PKCE S256、精确 HTTPS redirect URI、受信任 `age` 二进制、外部 recipient/identity、仓外 `.age` 文件、`0600` 权限、方法白名单和后续阶段的读回/恢复证据。任何一项缺失或失败，模块立即保持关闭，核心开发、构建、部署和影子运行继续。

没有“等待 N 小时/天”的 soak 门，也不得把运行时长、历史收益或观察期伪造成 token 或 Gmail 就绪证明。`age` 子进程的短时失败关闭保护只是避免挂死的执行上限，不是观察窗口或上线等待条件。

## 存储与恢复边界

- 运行时由受信任的绝对主机路径调用 `age -r <recipient>`；代码不通过 shell 拼接命令，也不记录 stderr。
- token cipher text 仅写入仓库外、非 symlink 的运行时秘密路径，原子替换后权限必须为 `0600`。
- 解密 identity 只能由主机秘密面提供，不能写入 Private-Database、Evidence、配置提交、环境快照或测试夹具。
- 仅允许合成 token 在离线测试中由注入的假进程验证控制流；本 Phase 未拥有、读取、加密或保存真实 token。
- token 泄漏、`age` 失败、路径进入仓库、权限不正确、scope 变宽/变窄或 callback 校验失败时，关闭 Gmail，并按安全事故合同保留无秘密诊断。

真实 Gmail 启用仍需要所有者在系统浏览器完成一次明确 consent，以及后续 S06/P02–P04 的保存、扫描、垃圾箱与恢复门；这些门不得被本文件或任何真实时间 soak 替代。
