# 决策记录与默认值

## 已确认决策

| 项目 | v3 决策 | 理由 |
|---|---|---|
| 中文显示名 | 股票商业机会拆解 | 明确是 listed-equity research triage |
| 稳定调用 ID | `stock-commercial-opportunities` | 用户已接受新 ID |
| 项目目录 | `stock-commercial-opportunities-skill/` | 源码/谱系/恢复证据单独管理 |
| 版本 | `3.0.0` | 从泛商业机会到股票研究的破坏性变化 |
| 本地安装 | 禁止；`NOT_INSTALLED` | 用户明确要求本地不安装 |
| 谱系 | 完整保留 v1/v2 原 ZIP + v3 源码/release | 可审计、可恢复、无信息丢失 |
| 仓库边界 | MetaDatabase public-visible + proprietary | 必须 public-safe；不等于开源许可 |
| Lanes | `SCREEN / ATTRIBUTE / UNDERWRITE` | 按证据深度和研究预算路由 |
| 候选数量 | 初筛最多 8，深拆最多 3，最终可 0 | 避免固定 Top N 填充 |
| 状态 | REJECT / SCREEN_FLAG / WATCHLIST / DILIGENCE_NEXT / ADVANCE_RESEARCH / NO_QUALIFIED_CANDIDATE | 全部是研究优先级，不是交易动作 |
| 证据成熟度 | E0–E5 | 与 score/risk/confidence 分离 |
| 示例 | synthetic issuer + `DEMO` exchange | 防止示例成为现实荐股或过期市场事实 |
| 脚本依赖 | Python 标准库 | 可移植、低依赖、易恢复 |
| 外部动作 | 默认只读 | 账户、付费数据、发布、交易需独立授权 |

## 默认参数

| 参数 | 默认值 | 改变条件 |
|---|---|---|
| language | `zh-CN` | 用户明确要求 |
| output visibility | `private` | 明确公开且完成许可/脱敏检查 |
| lane | `ATTRIBUTE` | 只有 broad universe 用 SCREEN；E3+ 才考虑 UNDERWRITE |
| direction | neutral research queue | 用户明确 long/short/watchlist 且边界合法 |
| research cap | 3–6 独立来源家族；连续两轮新增决定性信息 <10% 即停 | 高风险冲突需增加官方核验 |
| candidate cap | SCREEN 8；ATTRIBUTE/UNDERWRITE 3 | 用户给更小 universe |
| next diligence | 1 个最高 VOI | 独立且协调成本低时才并行 |
| as-of | 同次运行日期 | 历史复盘 |
| current fields | provider + timestamp | 不可得则 UNKNOWN/STALE |
| source priority | exchange/regulator/filing → IR → primary data → market/consensus → media → social/synthetic | 合法用户材料可单独标注 |

## 无待确认阻断项

ID、中文名、项目目录、备份目标和不安装边界均已由用户确认。未来只有以下变化需要新授权：安装、连接账户/付费数据、真实交易、对外发布、使用私有投资材料或改变仓库可见性。
