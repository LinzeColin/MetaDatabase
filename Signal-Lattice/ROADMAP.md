# Signal Lattice v0.0.0.1.40｜北极星修补 Roadmap

## S0｜Status 与移动仓库协调

读取 Status 和目标仓规则，获取最新 integration base，逐项分类 `satisfied / apply / adapt / equivalent / conflict / blocked / obsolete`。保留上游更优实现，不以旧文件覆盖等价新代码。

## S1｜修补落库

应用 v0.0.0.1.40 修补 overlay：完成真实推荐引擎、Skill Adapter、来源同步、市场输入、动态 API/UI、部署与公网验收合同。不得删除或覆盖目标仓已有 `Signal-Lattice/Stock_Skill/`。

## S2｜环境与数据绑定

在 OVH 注入 runtime.env、Cloudflare Tunnel Token、合法市场数据与外部 Skill 输出路径。凭证只进入 `/etc/signal-lattice/credentials/`，不得写入 Git。

## S3｜原子部署

构建确定性 Wheel，安装到 `/opt/signal-lattice/releases/0.0.0.1.40/`，原子切换 `current`，安装 systemd 并启动 API、Worker、同步、演化、备份和 Status 定时任务。

## S4｜北极星核心链路

即时验证：Skill 输出和市场快照摄取 → 证据独立性 → 量化硬门 → BUY/ADD/HOLD/REDUCE/SELL/WATCH/AVOID 或 NO_ACTION → Journal/Outbox/Status。禁止真实时间 Soak。

## S5｜公网与恢复

安装或复用 Cloudflare Tunnel，验证 `https://signal-lattice.linzezhang.com` 的 TLS、中文 UI、API、版本和安全头；执行 SQLite 备份恢复、systemd 自愈和目标状态证据生成。

## S6｜强制交付证明

完成 13×9 Status Closure，生成并核验 `DELIVERY_RESULT.json`。只有 `completion_claim=DEPLOYED_AND_PUBLICLY_VERIFIED` 才可向 Owner 提供完工结论和公网 URL。
