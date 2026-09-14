# Signal Lattice

当前候选：**应用 v0.0.0.2.9｜裁决契约 v0.0.0.2｜采集每 60 秒｜页面每 30 秒轮询｜行情最大新鲜度 180 秒**。

Signal Lattice 是永久只读的投研系统。每个分支独立给出方向结论，再按各分支对整体的历史贡献度动态加权，汇总成一个投资结论；样本不足 8 期时退回等权（COLD_START_EQUAL），权重照常真实参与汇总。系统不打开交易上下文、不下单、不登录券商账户、不修改权限——`AUTOMATIC_TRADING` 在配置层永久禁用。

当前已实现的分支为 `S1_MOMENTUM_ROTATION` 与 `S2_OVERSOLD_REBOUND`（均自 Alpha 项目移植并做样本外 walk-forward 复算）。v19 登记的另外 6 个分支尚未实现，在报告中以 `UNIMPLEMENTED` 标出、权重 0、明确排除，不参与任何结论。

## 本候选解决的第一阶段问题

- 行情来自新浪 / 腾讯 / 天天基金的免密钥公开接口，不再使用冻结 fixture；
- systemd timer 每 60 秒采集一轮，页面每 30 秒轮询 `/api/v1/report/latest`；
- 行情超过 180 秒未推进即判定过期并阻断，不以旧结论冒充实时结论；
- “观察 Tick”与“Decision Episode”分离，材料未变化不新增决策样本；
- 白箱账本落在 state_dir 的 JSON 文件，跨刷新、进程重启和次日保留；
- 六 Skill 独立结论、贡献、成熟样本、正确/相反/无效和影子权重可读取；
- 20/60 交易日成熟后才评价 Skill；影子权重不反向修改冻结的 V19 中央裁决；
- 行情与历史 K 线仅使用公开免密钥只读接口（新浪 / 腾讯 / 天天基金），不接券商网关、不持有任何行情凭证；
- 回测强制下一交易日生效、扣除切换摩擦、对比现金与宽基，并保留 `NOT_ISSUED`，不会把本地或短样本绿灯写成盈利证明。

## 当前真实状态

- 本地候选测试与本地端到端：由任务包内证据记录；
- VPS-3、公网部署、Owner 亲手使用：`NOT_RUN`；
- 真实 20/60 日前向收益：`PENDING`；
- 盈利资格：`NOT_ISSUED`；
- 跨币种候选必须提供按报价日期对齐的 `fx_to_base` 链，才能折算到 AUD；缺失即排除，不以固定 FX 费用替代实际汇率路径；
- `Serenity-Alipay/`：不在本候选 payload 中，零改动。

## 运行入口

完整源码位于 `Signal-Lattice/v19_release/`。部署入口仍为：

```bash
sudo bash Signal-Lattice/scripts/deploy_v19_15s.sh
```

部署成功只能由现有 VPS-3 上的真实公网验收和 `DELIVERY_RESULT.json` 证明。
