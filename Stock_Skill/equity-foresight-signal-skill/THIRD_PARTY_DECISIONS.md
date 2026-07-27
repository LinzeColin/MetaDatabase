# 第三方复用决策

访问日期：2026-07-27。

## v0.0.0.1 运行结论

本版本的推断、训练、校准、回放、状态、恢复计划与封包验证全部使用 Python 标准库：

```text
runtime_third_party_dependency = 0
agent_framework_dependency = 0
llm_sdk_dependency = 0
mcp_dependency = 0
```

没有第三方源码、二进制、模型或前端 Runtime 被复制、修改或捆绑进本版本。


## 用户自有状态宿主

`LinzeColin/LinzeHomeHub@fccd7eeeb224107d471fa6b6b54c801135fe1ec3`（MIT）不是第三方 Runtime 依赖，而是既有展示宿主。本任务仅通过唯一精确锚点、可逆 Patch 和原仓 `npm run validate/build` 接入 `status/collector/collect.py` 与 `status/web/index.html`；不复制其框架、依赖或前端 Runtime 进 Skill，不新建状态服务。

## 冻结同行与采用裁决

| 项目 | 冻结版本 / Tag | 冻结 Commit | 许可证 | 借鉴机制 | v0.0.0.1 决策与拒绝理由 |
|---|---|---|---|---|---|
| Microsoft Qlib | `v0.9.7` | `da920b7f954f48ab1bb64117c976710de198373e` | MIT | 数据—训练—回测—评价的松耦合工作流 | `REFERENCE_ONLY`；完整平台会引入缓存、数据层、服务面和大量依赖，污染嵌入式无状态节点边界 |
| scikit-learn | `1.9.0` | `77def0ed6e3beab57244885d2a584470e96c103d` | BSD-3-Clause | 概率校准、Brier score、可靠性图语义 | `REFERENCE_ONLY`；当前 Canonical JSON 与标准库运行核心已满足 v0，导入其运行栈会扩大供应链和跨版本面 |
| MAPIE | `v1.4.1` | `c4dedb1f0ff742d7e01d828fe982a713b4397145` | BSD-3-Clause | Conformal / 模型无关不确定性与风险控制接口 | `DEFERRED`；只有真实 PIT Outcome 证明预测层有增量价值后，才在新版本单独评估覆盖保证 |
| skfolio | `v0.20.1` | `d3e884bbfd78dd6b63513d8a295af0c045989911` | BSD-3-Clause | 时间序列交叉验证与组合压力测试 | `DEFERRED_OUT_OF_SCOPE`；本 Skill 不承担组合优化、仓位或订单执行 |
| XGBoost | `v3.3.0` | `d5cd2b40725d55747447f66e4a24f9a2c341b0bf` | Apache-2.0 | 非线性离线 Trainer 候选 | `FUTURE_OFFLINE_TRAINER_ONLY`；v0 不捆绑原生库、GPU/OMP Runtime 或模型反序列化面，且旧基线尚未证明 Outcome |
| Vega-Lite | `v6.4.3` | `f4bb2188709204860329aff2aeaf678c0280c315` | BSD-3-Clause | 声明式可视化语法 | `FORMAT_REFERENCE_ONLY`；Skill 仅输出受约束数据/图表 Payload，由宿主选择渲染器，不捆绑 JavaScript Runtime |
| Backstage | `v1.53.0` | `f5ab0da2afc9da5643548e4c808a280619d54716` | Apache-2.0 | 软件实体的稳定身份、Owner 和显式关系图 | `STATUS_MODEL_REFERENCE_ONLY`；借鉴“实体＋关系＋单一事实源”机制完善业务纵向切片矩阵，不引入其前端、Catalog Backend、数据库或插件 Runtime |
| OpenTelemetry Semantic Conventions | `v1.43.0` | `89aae438b3b3b0a8dd33003c9d70592baf7dbd0d` | Apache-2.0 | 稳定服务身份、版本、环境和资源属性命名 | `STATUS_NAMING_REFERENCE_ONLY`；保留 `stable_id/runtime_version/as_of` 等显式身份字段，不引入 SDK、Collector、Exporter 或网络遥测链路 |
| CloudEvents Spec | `ce@v1.0.2` | `fc1f6f31f5f011a72183f1bcea20c987cb683ade` | Apache-2.0 | 跨系统事件外层元数据与 JSON 互操作 | `HOST_OPTIONAL_WRAPPER_REJECTED_IN_SKILL`；Skill 不负责传输，强制加入事件封装会污染 0 网络边界；宿主需要事件总线时可在现有状态 Payload 外部封装 |

## 官方来源

- Qlib Release / Commit / License：
  - https://github.com/microsoft/qlib/releases/tag/v0.9.7
  - https://github.com/microsoft/qlib/commit/da920b7f954f48ab1bb64117c976710de198373e
  - https://github.com/microsoft/qlib/blob/da920b7f954f48ab1bb64117c976710de198373e/LICENSE
- scikit-learn Release / Commit / License：
  - https://github.com/scikit-learn/scikit-learn/releases/tag/1.9.0
  - https://github.com/scikit-learn/scikit-learn/commit/77def0ed6e3beab57244885d2a584470e96c103d
  - https://github.com/scikit-learn/scikit-learn/blob/77def0ed6e3beab57244885d2a584470e96c103d/COPYING
- MAPIE Release / Commit / License：
  - https://github.com/scikit-learn-contrib/MAPIE/releases/tag/v1.4.1
  - https://github.com/scikit-learn-contrib/MAPIE/commit/c4dedb1f0ff742d7e01d828fe982a713b4397145
  - https://github.com/scikit-learn-contrib/MAPIE/blob/c4dedb1f0ff742d7e01d828fe982a713b4397145/LICENSE
- skfolio Release / Commit / License：
  - https://github.com/skfolio/skfolio/releases/tag/v0.20.1
  - https://github.com/skfolio/skfolio/commit/d3e884bbfd78dd6b63513d8a295af0c045989911
  - https://github.com/skfolio/skfolio/blob/d3e884bbfd78dd6b63513d8a295af0c045989911/LICENSE
- XGBoost Release / Commit / License：
  - https://github.com/dmlc/xgboost/releases/tag/v3.3.0
  - https://github.com/dmlc/xgboost/commit/d5cd2b40725d55747447f66e4a24f9a2c341b0bf
  - https://github.com/dmlc/xgboost/blob/d5cd2b40725d55747447f66e4a24f9a2c341b0bf/LICENSE
- Vega-Lite Release / Commit / License：
  - https://github.com/vega/vega-lite/releases/tag/v6.4.3
  - https://github.com/vega/vega-lite/commit/f4bb2188709204860329aff2aeaf678c0280c315
  - https://github.com/vega/vega-lite/blob/f4bb2188709204860329aff2aeaf678c0280c315/LICENSE
- Backstage Release / Commit / License / Catalog model：
  - https://github.com/backstage/backstage/releases/tag/v1.53.0
  - https://github.com/backstage/backstage/commit/f5ab0da2afc9da5643548e4c808a280619d54716
  - https://github.com/backstage/backstage/blob/f5ab0da2afc9da5643548e4c808a280619d54716/LICENSE
  - https://backstage.io/docs/features/software-catalog/descriptor-format/
- OpenTelemetry Semantic Conventions Release / Commit / License / service identity：
  - https://github.com/open-telemetry/semantic-conventions/releases/tag/v1.43.0
  - https://github.com/open-telemetry/semantic-conventions/commit/89aae438b3b3b0a8dd33003c9d70592baf7dbd0d
  - https://github.com/open-telemetry/semantic-conventions/blob/89aae438b3b3b0a8dd33003c9d70592baf7dbd0d/LICENSE
  - https://opentelemetry.io/docs/specs/semconv/resource/service/
- CloudEvents Release / Commit / License / specification：
  - https://github.com/cloudevents/spec/releases/tag/ce%40v1.0.2
  - https://github.com/cloudevents/spec/commit/fc1f6f31f5f011a72183f1bcea20c987cb683ade
  - https://github.com/cloudevents/spec/blob/fc1f6f31f5f011a72183f1bcea20c987cb683ade/LICENSE
  - https://github.com/cloudevents/spec/blob/fc1f6f31f5f011a72183f1bcea20c987cb683ade/cloudevents/spec.md

## 研究停止条件

同行集合已覆盖量化平台、概率校准、Conformal 不确定性、时间序列/组合验证、非线性 Trainer、声明式可视化、实体关系目录、可观测身份命名和事件互操作九类机制。最后两次高质量边界复核只强化了“稳定身份＋显式关系＋宿主拥有传输”的既有实现，没有增加新的 v0 Runtime 依赖、权限或风险类别；CloudEvents 反而证明事件封装应留在宿主边界。继续扩展同行数量将增加文档和许可审计成本，却不改变当前架构决策，因此按有界研究停止条件收敛。

任何未来采用必须进入新版本，并重新锁定版本、Tag/commit、许可证、精确复用范围、修改与分发义务、数据许可、SBOM 和回滚路径；浮动 `main` 不构成稳定实施依据。
