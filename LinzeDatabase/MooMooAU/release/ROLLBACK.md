# Rollback Plan

## 代码和容器

- 回退到上一已验证 Git Commit 和容器 Digest；
- 关闭新 Feature Flag；
- 不回退或覆盖已归档 Raw；
- 重新运行合成和受影响 Acceptance。

## Processed

- current 指针退回上一 Parser；
- 错误版本保留隔离以支持审计，不供下游消费；
- 修复后生成新版本，不原地改写。

## M3

- 发现错误后立即设置 `m3_enabled=false`、`mutation_budget=0`；
- 精确记录受影响 Message ID 的私有 HMAC；
- 若消息仍可由 Gmail 恢复，使用独立受保护 Recovery Workflow 精确 `messages.untrash`；
- 不自动 Thread Untrash；
- Gmail 已永久清理时，从私有 Canonical Raw 恢复证据，但不能伪称恢复至原邮箱状态。

## Timeline

- 新 Asset 上传或验证失败时保留上一已验证 Asset；
- 若错误 Asset 已替换，从最近已验证 Processed Snapshot 即时重绘并替换；
- 不恢复历史图片仓。

## Secret

- OAuth/GitHub App 暴露：撤销并重授权；
- age Identity 暴露：停止新写入，为新数据开启新 Epoch；
- PDF Password 暴露：轮换可用账户资料/Secret，并评估日志；
- Secret 轮换前 M3 默认关闭。
