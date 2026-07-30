# Signal Lattice v0.0.0.1.40｜北极星部署修复入口

本版本是对已落库但未形成公网成果的 Signal Lattice 的**严格修补版本**。目标不是再次交付代码骨架，而是把现有代码修复成用户可直接访问的软件聚合中心，并强制完成公网 URL 与 Status 收尾证明。

- 目标仓库：`LinzeColin/MetaDatabase`
- 目标路径：`Signal-Lattice/`
- 软件入口：`https://signal-lattice.linzezhang.com`
- 权威监控：`https://status.linzezhang.com`
- 运行节点：OVH Linux
- 当前阶段：`SEALED_TASKPACK`；Build Agent 开始执行后进入 `BUILD_LAST_MILE`
- 运行边界：零 Agent、零模型 Token、禁止自动交易、禁止 macOS/launchd 常驻

## 用户最终应该看到什么

1. 一个可打开的中文网站，而不是任务包或 GitHub 文件目录；
2. 动态摄取平权股票 Skill 输出和 Point-in-time 市场快照；
3. 对证据来源去重，展示共识、分歧、风险与量化硬门；
4. 硬门全部通过时提供供人执行的 BUY/ADD/HOLD/REDUCE/SELL/WATCH/AVOID 建议；
5. 任一关键证据不足时明确输出 `NO_ACTION`；
6. 永远不自动向券商下单。

## Build Agent 唯一执行顺序

1. 读取本文件、`CODEX_LAST_MILE_PROMPT.txt`、`CANONICAL_STATE.json` 和修补包根目录的 `PATCH_EXECUTION_CONTRACT.json`；
2. 执行修补包 `apply_patch.py --apply`，不得修改版本号；
3. 在目标仓运行冻结测试；
4. 准备 `/etc/signal-lattice/runtime.env` 和 Cloudflare Tunnel Token 文件；
5. 运行：

```bash
sudo SIGNAL_LATTICE_APPLY=1 bash Signal-Lattice/scripts/deploy_northstar.sh
```

6. 只有以下文件为 PASS，才允许报告“完工”：

```text
/var/lib/signal-lattice/artifacts/public_release.json
/var/lib/signal-lattice/artifacts/status_closure.json
/var/lib/signal-lattice/artifacts/DELIVERY_RESULT.json
```

7. 最终回复 Owner 时必须提供：

```text
https://signal-lattice.linzezhang.com
https://status.linzezhang.com
DELIVERY_RESULT.json 的 SHA-256
```

没有可点击公网链接或 `DELIVERY_RESULT.json`，即视为**未完成**。
