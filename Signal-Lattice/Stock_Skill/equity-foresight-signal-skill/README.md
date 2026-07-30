# 股势前瞻（Equity Foresight Signal）

Stable ID：`equity-foresight-signal`
Version：`0.0.0.1`
状态：`SOURCE_ONLY / SHADOW_ONLY / OUTCOME_NOT_PROVEN`

供现有股票系统直接调用的确定性预测节点。它接收宿主准备好的 point-in-time 证据，分别输出 5D、20D、60D 的正净收益概率、基准概率与 Lift、P10/P50/P90、经济 Edge、障碍触及时机、可靠性、数据质量和 `ABSTAIN`。

独立域名：`N/A`；专属部署节点：`N/A`；运行位置：既有远程 Linux/OVH 宿主进程按需嵌入。

它不是独立 Web、数据库、daemon、行情抓取器、券商连接器、组合系统或自动交易器；不依赖 ChatGPT、Codex、Claude、MCP、Agent Framework 或 LLM Token；不把工程测试解释为稳定 Alpha。部署画像固定为 `REMOTE_HOST_EMBEDDED_ONLY`：禁止安装或运行在 macOS，禁止 `launchd`、LaunchAgent/LaunchDaemon、本机常驻进程、本机持久缓存、日志、数据库或状态目录。显式调用完成后，本机持久文件、持久字节和常驻后台进程必须均为 0；函数执行瞬间不可避免的临时 CPU/RAM 不伪称为 0。

```bash
python3 -B -m equity_foresight_signal self-check
python3 -B -m equity_foresight_signal evaluate fixtures/request.json fixtures/bundle.json
python3 -B -m equity_foresight_signal train-direction fixtures/pit_dataset.json fixtures/training_config.json
python3 -B -m equity_foresight_signal audit-runtime
python3 -B tools/verify_macos_zero_footprint.py
python3 -B tools/run_release_oracles.py --output /tmp/efs-release-oracles.json
```

v0.0.0.1 只授权 `RESEARCH` 与 `SHADOW`。任何 `DECISION_SUPPORT` 请求必须 fail closed；真实多资产 PIT Outcome 进入 Future Roadmap，不阻塞工程正式验收，也不得被伪报为已证明。

上线后，宿主从 Host Status Payload 读取可哈希的五行业务基线矩阵；任务包同时提供对现有 `LinzeHomeHub/status` 采集器与 v3 四入口静态页的可逆补丁：保留“总览 / 运行 / 成本 / GitHub”四个一级入口，在既有“运行”页内嵌“业务基线治理”区块，并把无效、缺失或阻塞状态接入健康行动清单；全中文展示阶段、阶段环节、状态、上下游、耦合控制、阻塞原因和下一动作。复用既有 OVH cron 与 host-direct rsync，不新增一级入口、域名、数据库或 daemon；Skill 自身不传输、不持久化。
