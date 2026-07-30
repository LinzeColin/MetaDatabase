# Signal Lattice｜股票 Skill 聚合、协调与投资决策网站

Signal Lattice 是部署在 OVH、通过 Cloudflare 暴露公网入口的中文股票决策聚合中心。它以平权方式接入股票研究 Skill，把异构输出规范化为可追溯的 Signal、Claim、Evidence、Conflict、Quant Gate 和 Recommendation Snapshot，再形成供人执行的投资建议或严格 `NO_ACTION`。

## 北极星链路

```text
GitHub 最新 Skill 与外部系统研究制品
→ 只读来源跟踪与确定性 Adapter
→ 证据去重、共识与冲突协调
→ Point-in-time、费用、样本外、过拟合、流动性、容量和组合风险硬门
→ 人工投资建议或 NO_ACTION
→ 中文网站与 Status Tier-0
```

## 软件入口

- 公网软件：`https://signal-lattice.linzezhang.com`
- 权威监控：`https://status.linzezhang.com`
- OVH 内部 API：`127.0.0.1:8787`

部署完成必须由 `scripts/verify_public_release.py` 实际访问公网 URL，并由 `scripts/build_delivery_result.py` 生成 `DEPLOYED_AND_PUBLICLY_VERIFIED` 收据。代码落库、systemd 文件存在或本地测试通过都不能替代公网成果。

## 安全边界

- 运行期 Agent、LLM、模型 API 与 Token：0；
- 自动券商交易：永久关闭；
- 任何建议都标记 `human_execution_only=true`；
- 数据、来源、License、证据独立性或量化硬门失败时强制 `NO_ACTION`；
- macOS、本机和 launchd 不承载任何运行组件。

## 可选市场数据适配

任务包提供 `scripts/moomoo_market_snapshot.py`，可在目标环境已运行 Moomoo OpenD、且 Owner 明确确认数据许可时，将报价转换为 Signal Lattice 的 Point-in-time 市场快照。它不是核心运行依赖，也不会自动安装或绕过许可门；未绑定合法数据时系统保持 `NO_ACTION`。
