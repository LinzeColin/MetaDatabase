# Software Supply Chain

## 依赖策略

- Python 版本和包依赖固定；
- 使用 lockfile 和 hash；
- 构建不可变容器并固定 Digest；
- 生产 Workflow 不运行 `pip install latest`；
- 第三方 GitHub Actions 使用完整 Commit SHA；
- 优先官方 Actions，减少第三方数量；
- 生成 SPDX/CycloneDX SBOM。

## 自动检查

- CodeQL；
- Dependency Review；
- OSV/pip-audit；
- Secret Scan；
- License/来源清单；
- Action SHA 检查；
- Container vulnerability scan；
- Reproducible build digest compare；
- Provenance / in-toto 风格材料与产物摘要。

## Patch 生命周期

| 严重度 | 默认处置 |
|---|---|
| Critical | 立即阻止生产，回退安全版本或补丁 |
| High | 阻止新发布；在最短可行窗口修复 |
| Medium | 下一个维护周期，记录风险 |
| Low | 与常规依赖更新合并 |

不允许“忽略所有告警”。例外必须有受影响范围、可利用性证据、补偿控制、到期日和回滚。

## Build Provenance

公开代码/容器发布记录：源 Commit、lockfile、构建器、测试结果、SBOM、Digest。私有数据批次只发布脱敏 Evidence Root 和恢复结论，不公开数据摘要细节。
