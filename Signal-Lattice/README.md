# Signal Lattice

当前候选：**应用 v0.0.0.1.43｜裁决契约 v0.0.0.19｜页面/API 每秒确认｜报价与报告每 15 秒观察｜正式复核每小时**。

Signal Lattice 是永久只读影子研究系统。它让六个 Canonical 投研方法在中央赢家冻结前分别审视候选宇宙，再发布一个且仅一个 100.0%/0.0% 的影子赢家。系统不打开交易上下文、不下单、不登录券商账户、不修改权限。

## 本候选解决的第一阶段问题

- 页面每秒调用真实 `/api/v1/heartbeat`，不再只做浏览器倒计时；
- 报价与既有结论每 15 秒观察和刷新；
- “观察 Tick”与“Decision Episode”分离，材料未变化不新增决策样本；
- SQLite 白箱账本跨刷新、进程重启和次日保留；
- 六 Skill 独立结论、贡献、成熟样本、正确/相反/无效和影子权重可读取；
- 20/60 交易日成熟后才评价 Skill；影子权重不反向修改冻结的 V19 中央裁决；
- MooMoo OpenD 历史行情仅使用只读 QuoteContext 导出；
- 回测强制下一交易日生效、扣除切换摩擦、对比现金与宽基，并保留 `NOT_ISSUED`，不会把本地或短样本绿灯写成盈利证明。

## 当前真实状态

- 本地候选测试与本地端到端：由任务包内证据记录；
- VPS-3、公网部署、Owner 亲手使用：`NOT_RUN`；
- 真实 20/60 日前向收益：`PENDING`；
- 盈利资格：`NOT_ISSUED`；
- `Serenity-Alipay/`：不在本候选 payload 中，零改动。

## 运行入口

完整源码位于 `Signal-Lattice/v19_release/`。部署入口仍为：

```bash
sudo bash Signal-Lattice/scripts/deploy_v19_15s.sh
```

部署成功只能由现有 VPS-3 上的真实公网验收和 `DELIVERY_RESULT.json` 证明。
