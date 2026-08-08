# Run Contract — S6-T1 最终独立验收

## 目标

在 `S5-T4` 完成后，由与 Builder 和 S4-T3A 审查者分离的 Verifier 对受控私有 Candidate 做最终裁决。该阶段才是原冻结 `S4-T3` 期待的正式 15/15 验收位置。

## 不可协商输入

- `S5-T1` Saved Version、`S5-T2` 脱敏配置、`S5-T3` 真实链路/回滚、`S5-T4` 脱敏投影的精确身份与证据；
- 每个 `R-001` 到 `R-015` 的冻结 Oracle、阈值与真实 evidence record；
- source commit/tree、build 或 Saved Version identity、配置存在性、测试 ID、证据摘要或受治理引用；
- `PWB-S4-S5-SEQUENCE-001` 完整性检查结果。

## 验收

- 15/15 requirement 均有真实、精确 Subject 绑定的证据；
- `P0=0`、`P1=0`、`UNKNOWN=0`、`NOT_RUN=0`、`WAIVED=0`；
- 独立 Verifier 可追溯且未在审查中改产品；
- 任一失败按 FAIL 记录，不能降级为条件 PASS。

## 明确不在范围

- 不以 S4-T3A、Builder 预检或静态合同校验代替最终 PASS；
- 不更改产品、任务包、Secret、素材权利或公开 audience；
- 不上传 GitHub。

## 输出与停止条件

输出是针对精确 Candidate 的最终 PASS/FAIL、完整 traceability 与证据索引。只有 PASS 才能进入 `S6-T2` 公开 audience 确认；否则保持或恢复私有访问，按冻结回滚程序处理。
