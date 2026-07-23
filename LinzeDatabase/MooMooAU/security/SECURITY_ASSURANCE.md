# Security Assurance Plan

## 1. 设计阶段

- Threat Model 与数据分类；
- 最小权限与 endpoint allowlist；
- Raw/Processed/Public 三层边界；
- 破坏性 M3 前置恢复证明；
- Feature Flag、Mutation Budget、Kill Criteria；
- 无模型数据路径。

## 2. 构建阶段

- Python 类型检查、Ruff、格式化；
- 安全编码：参数化 API、路径内容寻址、资源限制、异常脱敏；
- 依赖 lockfile、Hash 校验、SBOM；
- Third-party Actions 固定完整 Commit SHA；
- 容器 Digest 固定，不在生产运行时安装浮动依赖；
- Secret scanning、CodeQL、依赖审计。

## 3. 测试阶段

- Unit、Contract、Property、Fuzz、Integration、E2E；
- 邮件伪造、Thread 混合、禁止端点；
- 文件攻击、Prompt Injection、路径和公式；
- 公开脱敏扫描；
- 权限越界和 Fork/PR Secret 隔离；
- Chaos、Recovery、Load、Capacity；
- 不同模型独立安全互审。

## 4. 发布阶段

- Alpha 合成；
- Beta Raw-only；
- M3 Canary Mutation Budget=1；
- Blue-Green Parser/Timeline；
- GA 前必须完成真实 Recovery Key 抽样恢复；
- 所有 Gate 证据写为机器可读、公开脱敏形式。

## 5. 维护阶段

| 项目 | 节奏 | SLA/动作 |
|---|---|---|
| Critical/High 依赖漏洞 | 每次 CI + 每周 | 无接受风险则阻止合并/发布 |
| Gmail/GitHub API 变化 | 每日契约测试 + 发布前 | 降级 Raw-only 或停止 M3 |
| Sender Registry | 新候选出现时 | 保持原邮件不动，证据更新后回补 |
| Recovery Drill | 每季度与密钥变化后 | 100% 恢复，否则 KILL-005 |
| Capacity | 每周 | Yellow 限制衍生数据；Red 停回填 |
| Secret 轮换 | 暴露/权限变化/政策要求 | 新 Epoch，停止受影响路径 |
| Parser Drift | 每次新模板 | Blue-Green，旧 current 可回退 |

## 6. 审批和回滚

- 普通可逆代码变更：自动测试通过后 PR；
- Gmail 权限、M3、密钥、公开字段变更：安全审查 + Canary；
- 任何 Kill：自动关闭破坏性 Flag；
- Raw 永不覆盖或为回滚而删除；
- Processed current 和容器 Digest 可回退；
- Gmail 尚未永久清理时可按精确 Message ID untrash，但不作为正常流程。
