# 第三方依赖与许可边界

访问日期：2026-07-27。

v0.0.0.1 的推断、训练、校准、回放、状态、恢复计划和验收工具全部使用 Python 标准库，第三方运行依赖为 0。未捆绑 Qlib、scikit-learn、XGBoost、MAPIE、skfolio、Vega-Lite、Backstage、OpenTelemetry、CloudEvents、LLM SDK、Agent Framework 或 MCP Runtime。

冻结参考集合：

| 项目 | 版本 | Commit | License | 边界 |
|---|---|---|---|---|
| Qlib | v0.9.7 | da920b7f954f48ab1bb64117c976710de198373e | MIT | 架构参考，不作为 Runtime |
| scikit-learn | 1.9.0 | 77def0ed6e3beab57244885d2a584470e96c103d | BSD-3-Clause | 校准/评分语义参考 |
| MAPIE | v1.4.1 | c4dedb1f0ff742d7e01d828fe982a713b4397145 | BSD-3-Clause | 新版本条件式评估 |
| skfolio | v0.20.1 | d3e884bbfd78dd6b63513d8a295af0c045989911 | BSD-3-Clause | 组合范围外 |
| XGBoost | v3.3.0 | d5cd2b40725d55747447f66e4a24f9a2c341b0bf | Apache-2.0 | 未来离线 Trainer 候选 |
| Vega-Lite | v6.4.3 | f4bb2188709204860329aff2aeaf678c0280c315 | BSD-3-Clause | 仅格式参考 |
| Backstage | v1.53.0 | f5ab0da2afc9da5643548e4c808a280619d54716 | Apache-2.0 | 业务实体身份与关系图参考，不引入 Catalog 平台 |
| OpenTelemetry Semantic Conventions | v1.43.0 | 89aae438b3b3b0a8dd33003c9d70592baf7dbd0d | Apache-2.0 | 稳定服务身份与属性命名参考，不引入遥测 Runtime |
| CloudEvents Spec | ce@v1.0.2 | fc1f6f31f5f011a72183f1bcea20c987cb683ade | Apache-2.0 | 宿主可选封装；Skill 内拒绝传输耦合 |

详细官方来源、复用决策、拒绝理由和研究停止条件见根目录 `THIRD_PARTY_DECISIONS.md`。任何未来采用必须进入新版本，锁定版本/commit、许可证、精确复用范围、修改义务、数据许可与回滚路径。
