# Source Inventory

访问日期：2026-07-27。

## 用户公开仓库

已访问 LinzeColin 当前公开的 7 个仓库入口：AgentDatabase、MetaDatabase、KMOS、CodexProject、LinzeHomeHub、Archive、NotionStudyProject。私有仓与未公开文件不可读取，不假装已核验。

主目标仓公开观察点：`LinzeColin/MetaDatabase@522b8bee22b572a0bbe15c9cf0b4aea513594805`；状态目标仓公开观察点：`LinzeColin/LinzeHomeHub@fccd7eeeb224107d471fa6b6b54c801135fe1ec3`。适用 Skill 冻结合同基线：`LinzeColin/AgentDatabase@bfa9b1da006172d877425275b6ae2d16ca652ba3`。使用 Verifier v0.0.2.2、Teleiosis v0.0.0.2、Persona Distiller Group、Domain Dual Plane、Goal-to-Delivery 和 Output Skill 的边界；未取得独立执行面时不伪造 PASS。

MetaDatabase 相关文件 Hash 已在公开观察点重新获取：根 `AGENTS.md`、`README.md`、`LICENSE`、`Stock_Skill/AGENTS.md`、`Stock_Skill/README.md` 与 `Stock_Skill/REGISTRY.json`；落库前仍由 fail-closed preflight 对真实工作树逐字节复核。LinzeHomeHub 只对 `status/collector/collect.py` 与 `status/web/index.html` 使用“相关路径清洁＋唯一精确锚点”前置条件；公开 Commit 仅为审计线索。

## 冻结同行参考

| 项目 | Tag/Version | Commit | License | 状态 |
|---|---|---|---|---|
| Qlib | v0.9.7 | da920b7f954f48ab1bb64117c976710de198373e | MIT | REFERENCE_ONLY |
| scikit-learn | 1.9.0 | 77def0ed6e3beab57244885d2a584470e96c103d | BSD-3-Clause | REFERENCE_ONLY |
| MAPIE | v1.4.1 | c4dedb1f0ff742d7e01d828fe982a713b4397145 | BSD-3-Clause | DEFERRED |
| skfolio | v0.20.1 | d3e884bbfd78dd6b63513d8a295af0c045989911 | BSD-3-Clause | OUT_OF_SCOPE |
| XGBoost | v3.3.0 | d5cd2b40725d55747447f66e4a24f9a2c341b0bf | Apache-2.0 | FUTURE_OFFLINE_TRAINER_ONLY |
| Vega-Lite | v6.4.3 | f4bb2188709204860329aff2aeaf678c0280c315 | BSD-3-Clause | FORMAT_REFERENCE_ONLY |
| Backstage | v1.53.0 | f5ab0da2afc9da5643548e4c808a280619d54716 | Apache-2.0 | STATUS_MODEL_REFERENCE_ONLY |
| OpenTelemetry Semantic Conventions | v1.43.0 | 89aae438b3b3b0a8dd33003c9d70592baf7dbd0d | Apache-2.0 | STATUS_NAMING_REFERENCE_ONLY |
| CloudEvents Spec | ce@v1.0.2 | fc1f6f31f5f011a72183f1bcea20c987cb683ade | Apache-2.0 | HOST_OPTIONAL_WRAPPER_REJECTED_IN_SKILL |

完整官方来源、采用/拒绝理由与研究停止条件见 `THIRD_PARTY_DECISIONS.md`。v0.0.0.1 Runtime 不复制这些项目代码、不导入其包，也不声明为运行依赖。

## 状态宿主复用

复用 `LinzeHomeHub/status/` 已有 OVH cron 采集器、`status/data/snapshot.json` 和 v3 四入口页面；只增加可逆的 collector/web Patch 与一次性状态事实写入工具，在现有“运行”页内嵌业务矩阵并接入健康行动清单，不复制 LinzeHomeHub 源码到 Skill Runtime，不创建新入口、服务、数据库或域名。

## 部署与本机边界

上线画像为 `REMOTE_HOST_EMBEDDED_ONLY`；禁止 macOS Runtime、`launchd` 和本机持久/常驻足迹。该结论由包内 `verify_macos_zero_footprint.py` 验证，不依赖外部项目。
