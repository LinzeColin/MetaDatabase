# Signal Lattice

当前待上线发行：**应用 v0.0.0.1.42｜裁决契约 v0.0.0.19｜15 秒完整可见结果**。

Signal Lattice 是永久只读影子研究系统。它动态扫描九类市场机会，让六个 Canonical 投研方法在中央赢家产生前分别审视完整候选宇宙，再由中枢发布一个且仅一个 100.0%/0.0% 的影子赢家。系统不登录券商、不打开交易上下文、不下单、不改账户权限。

## 当前发行边界

- 冻结裁决契约：`v0.0.0.19`
- 应用发行：`v0.0.0.1.42`
- 结果周期：每 15 秒一次完整报告；浏览器使用事件流并以 15 秒读取作后备
- 每日第一条有效正式结果：九桶动态完整扫描；扫描进行期间继续每 15 秒发布“降级持有”，完成后恢复正式裁决
- 其余周期：更新现行策略与九桶稳健前沿
- 当前唯一影子状态：MooMooAU / State Street SPDR 标普500 ETF / SPY / 看涨 / 100.0% / ASX / AUD
- 用户可见结构：严格保持 v16 两板块正式报告结构
- 旧 `v0.0.0.1.41` 保留为服务器回滚目标，不再是待激活发行

## 源码与运行入口

完整发行位于 `Signal-Lattice/v19_release/`：

- `src/signal_lattice_v19/`：动态覆盖、六技能方法契约、三路径与中央裁决、15 秒运行循环、只读 API
- `config/`：V19 状态、九桶、六技能路由、成本与风险门
- `web/`：完整正式报告页面
- `deploy/`：systemd、安装切换、回滚和失败事实采集
- `tests/`：冻结结构、只读边界、六技能顺序、候选资格与 15 秒周期验收
- `dist/`：预构建 wheel；部署端只安装，不编写或修复源码

## 上线

服务器上只执行：

```bash
sudo bash Signal-Lattice/scripts/deploy_v19_15s.sh
```

成功证据：

```text
/var/lib/signal-lattice-v19/deployment/DELIVERY_RESULT.json
/var/lib/signal-lattice-v19/deployment/local_acceptance.json
/var/lib/signal-lattice-v19/deployment/public_acceptance.json
```

失败时只采集事实并回滚：

```bash
sudo bash Signal-Lattice/v19_release/deploy/collect_failure_facts.sh
sudo bash Signal-Lattice/v19_release/deploy/rollback.sh
```
