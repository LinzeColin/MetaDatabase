# S4/S5 验收顺序增补 — PWB-S4-S5-SEQUENCE-001

## 结论

冻结任务包的验收拓扑有一个可复核的顺序环：`S4-T3` 要求 Saved Candidate 和 15/15 的真实证据，但 `S5-T1` 又以 `S4-T3` 为前置；其中 R-003、R-009、R-012、R-014、R-015 的真实证据还分别依赖 S5-T1 至 S5-T4。若保持原顺序，任何一方都不能先取得正式 PASS。

本增补只重排证据采集与最终裁决的时序。它不重写任务包、不变更五张视觉真值、不降低任何 Oracle 或阈值，也不把本地测试、`UNKNOWN`、`NOT_RUN` 或 `WAIVED` 变成产品通过。

机器可读真源是 [ACCEPTANCE_SEQUENCE_ADDENDUM.json](./ACCEPTANCE_SEQUENCE_ADDENDUM.json)。它将冻结任务包的五个关键文件以 SHA-256 绑定，并包含全 15 项的原始任务映射。

## Owner 授权边界

本记录依据本线程 Owner 的“全部授权 不允许任何block”创建，但仅涵盖显式的验收顺序修复。它不授权：

- 放弃或改写任何需求、Oracle、阈值或证据；
- 将 Builder 预检称为独立产品 PASS；
- 修改冻结任务包原件；
- 配置 Secret、创建/公开 Sites Version、公开部署、使用未获授权素材或写入用户数据。

既有 `OWNER_APPROVAL.json` 中的公开素材、隐私、provider 和生产副作用条件仍然完整生效。

## 新的受控时序

```text
S4-T1/S4-T2
      │
      ▼
S4-T3A 独立候选就绪审查（非最终验收）
      │  仅允许私有采证
      ▼
S5-T1 私有 Saved Version
      ▼
S5-T2 私有候选配置与权利/隐私门
      ▼
S5-T3 受控私有部署、真实链路与回滚采证
      ▼
S5-T4 脱敏运维投影采证
      ▼
S6-T1 独立最终验收（15/15，P0/P1/UNKNOWN/NOT_RUN/WAIVED 均为 0）
      ▼
S6-T2 才可确认公开 audience
```

`S4-T3A` 的结果只能是 `READINESS_PASS` 或 `BLOCKED`，不是 S4 的 15/15 产品 PASS。它只允许下一阶段创建一个私有、可丢弃的采证 Candidate。`S5-T3` 仍在受控私有访问下执行；任何公开 audience 变更都必须等到 `S6-T1` 的独立最终 PASS 之后。

## S5-T2 的私有 Origin 引导例外

当前 Sites 平台只在部署后分配稳定 Site URL，而冻结任务包将 Sites production Origin 作为默认 Origin。若私有 Candidate 尚无 URL，`S5-T2-ORIGIN-BOOTSTRAP-001` 允许**仅一次受控私有部署**现有 Saved Version，以获得该 Origin 并继续完成 `APP_ORIGIN` 与 hostname-bound 配置。

它不是 `S5-T3`：必须先即时复核 owner/custom、无外部访客/群组、无 URL 和既有 Saved Version；不得增加受众、域名、用户数据或真实认证/邮件回放；证据只记录 Version 身份、访问事实、URL 存在性或不可逆摘要与 Settings 键级 revision。完成后仍回到 `S5-T2`，直到其正常配置证据完整，才允许真正进入 `S5-T3`。

## 15 项需求的证据采集与裁决

| Requirement | 最早真实 Candidate 采证 | 最终裁决 |
| --- | --- | --- |
| R-001, R-002, R-010 | S5-T1 私有 Saved Version | S6-T1 |
| R-003, R-004, R-005, R-006, R-009, R-011, R-013, R-014 | S5-T3 受控私有部署 | S6-T1 |
| R-008 | S5-T2 私有配置/权利门 | S6-T1 |
| R-007, R-012, R-015 | S5-T4 脱敏运维投影 | S6-T1 |

每一项仍须使用冻结 `ACCEPTANCE_CONTRACT.json` 的原始 Oracle、阈值与 `13_evidence/r-xxx.json` 路径。最终证据必须绑定精确 source commit/tree、build 或 Saved Version、配置身份（仅存在性）、测试 ID、原始证据摘要或受治理引用和独立 Verifier 结果。

## 本地校验与回滚

从 `Personal-WorkBench/` 执行：

```bash
TASKPACK_ROOT=/path/to/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 \
  npm run validate:acceptance-sequence
```

该命令只读任务包与增补，输出 `PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY` 与 `NOT_PRODUCT_ACCEPTANCE`，不会写证据、部署或访问外部服务。

若增补校验失败、任一真实验证失败，或出现 P0/P1/未知证据：保持 Candidate 私有、限制访问并回到上一 Saved Version；不得进入公开 audience，也不得将本增补解释为产品 PASS。
