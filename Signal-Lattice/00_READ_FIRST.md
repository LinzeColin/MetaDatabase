# 先读：Signal Lattice V19 15 秒发行

本目录已经包含完整设计、源码、配置、页面、预构建 wheel、测试、安装切换、公开验收与回滚。开发工作已在任务包内完成；Codex 不承担需求分析、编码、修复、重构或重新验收设计。

唯一待执行链路：

1. 将任务包 `repo_overlay/` 原样覆盖到 `MetaDatabase` 根目录，仅提交 `Signal-Lattice` 范围并推送 `main`。
2. 使用既有 Signal Lattice 主机访问方式更新仓库，在主机执行 `sudo bash Signal-Lattice/scripts/deploy_v19_15s.sh`。
3. 只以 `/var/lib/signal-lattice-v19/deployment/DELIVERY_RESULT.json` 的 `PASS` 与公网报告验收为完成；失败时返回 `FAILURE_FACTS.txt`，不得临场改代码。

冻结边界：裁决契约始终为 `v0.0.0.19`；应用发行是 `v0.0.0.1.42`，两者不是同一版本层。永久只读影子研究，禁止任何交易副作用。
