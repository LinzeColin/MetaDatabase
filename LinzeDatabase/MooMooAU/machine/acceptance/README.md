# Final Acceptance control plane

本目录实现冻结 AC-001–AC-034 的 fail-closed 证明层，不改变原始 Oracle、threshold、verification 或
evidence path。

两种模式必须分开：

- `validate_acceptance.py` 默认只验证 34 份 evidence 的 schema、冻结契约、traceability、test entry、
  source hash 和确定性重建；结构完整但最终 Oracle 未运行时返回 0，并输出 `status=BLOCKED`。
- `validate_acceptance.py --require-pass` 是最终发布门。任一 Oracle 未运行、失败，或任一关联 task 仍为
  `PARTIAL/NOT_RUN/BLOCKED` 时返回 1。结构错误返回 2。

冻结的每个 `tests/acceptance/test_ac_NNN.py` 都调用最终发布门，因此当前 0/34 的真实状态会形成明确
pytest failure，而不是 missing-file collection error 或虚假绿色。

Evidence 只能由 `build_evidence.py` 从冻结契约、traceability、test entry、task evidence 和可选的
hash-bound Oracle observation 确定性生成。禁止手改结果或创建无来源的 PASS。
