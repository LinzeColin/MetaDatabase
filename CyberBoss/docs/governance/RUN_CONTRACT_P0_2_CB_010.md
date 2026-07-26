# Run Contract — P0.2 / CB-010

## 1. Goal

只读测量现有 OVH 资源、端口、进程、文件系统和 Status 接入面，建立可重复的
capacity/profile/protect/recover 计算与压力 fixture，为后续部署提供不伤害既有
关键服务的边界。

## 2. Minimum scope

- 对 `status.linzezhang.com` 公共只读页面与 snapshot contract 做当前观测；
- 使用已授权 OVH SSH/sudo 入口运行一次只读 collector，输出三次即时 snapshot；
- 记录 memory/swap/load/disk/inode、listener ports、service/process/container
  摘要、reverse proxy 与 Status ingestion 线索，所有证据必须脱敏；
- 从同一组测量确定 `constrained`、`tiny` 或 `standard` profile，并计算
  MemoryHigh/MemoryMax、disk/workspace/log/snapshot cap 和 protect/recover
  predicate；
- 执行有硬上限、无等待的 memory/disk/queue pressure fixture，验证
  guard → protect → recover；
- 使现有 global Status adapter 与当前公共 `projects[]` row contract 一致，
  只构建 fixture，不修改线上平台。

## 3. Non-goals

- 不安装 package、创建用户/持久目录或修改 OVH 配置/持久文件；
- 不启动、停止、重启或 reload systemd、container、reverse proxy；
- 不运行真实 CyberBoss/Codex/微信任务，不写真实业务数据；
- 不修改 DNS、Cloudflare Access、线上 Status snapshot 或 collector；
- 不执行 `P0.3 / CB-020`；
- 不 push，不创建 PR/tag/release。

## 4. Inputs to inspect

- `04_TASK_DAG_EXECUTION_PACK.yaml` 的 `CB-010`
- `02_PRD_ACCEPTANCE_CONTRACT.md` 的 `AC-064`、`AC-067`
- `03_ARCHITECTURE_DATA_SECURITY.md` 的 Status 与 Capacity contract
- `06_OPERATIONS_STATUS_HANDOVER.md` 的 preflight/runbook
- `implementation-kit/scripts/preflight.sh`
- `implementation-kit/scripts/select-resource-profile.sh`
- `implementation-kit/status/`
- 现有 SSH config 中已明确授权的 host alias
- Owner 明确指示后，可从本机 `_protected` 既有 Alpha/OVH 部署记录解析唯一
  目标与认证文件位置；只可读取身份/模式/一致性元数据，不得复制、输出或提交
  地址、credential 或 private-key material
- `https://status.linzezhang.com/` 与
  `https://status.linzezhang.com/data/snapshot.json`

## 5. Allowed modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_P0_2_CB_010.md`
- `CyberBoss/docs/evidence/CB-010/**`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/scripts/validate_cb010.py`
- `CyberBoss/scripts/validate_cb000.py`（仅移除对“当前 Run 必须仍是 P0.1”
  的历史状态假设，继续验证 CB-000 固定来源事实）
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/preflight.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/select-resource-profile.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/resource_profile.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/resource-pressure-fixture.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/status-snapshot.example.json`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/status/**`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/**`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md`
- `CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md`
- 上述 implementation-kit 与外层 TaskPack 的 `MANIFEST.sha256`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

不得修改 `CyberBoss/app/`、`CyberBoss/vendor/`、仓库根文件或其他项目。

## 6. Validation

```bash
bash -n CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/preflight.sh
bash -n CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/select-resource-profile.sh
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_resource_profile.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/resource-pressure-fixture.py
node --test CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/status-adapter-contract.test.js
python3 CyberBoss/scripts/validate_cb010.py
python3 CyberBoss/scripts/validate_prestage0.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_task_dag.py \
  CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_traceability.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_no_wait.py \
  CyberBoss/docs/product_design/v0.0.0.4
git diff --check
```

## 7. Risks and rollback

- 错误识别主机可能泄露或影响非目标系统：只接受现有明确 SSH alias/Owner
  提供的目标，不根据 IP、DNS 或公共页面猜测。
- collector 可能暴露 IP、PID、argv、mount/device 或 secret path：仓库证据只保留
  聚合值、unit/executable basename、port number/bind scope 和允许路径类别。
- 压力测试可能挤压关键服务：fixture 默认只使用有硬上限的当前进程临时资源；
  真实 host pressure 只能在 cgroup/预算证明安全且 Owner 明确授权有界实机压力后
  执行；“只读准备”本身不视为该授权。
- 回滚为本 Run 本地 commit；本 Run 不改变 OVH 或线上 Status，因此没有远端回滚。

## 8. Stop conditions

- 没有可证明已授权的 OVH host identity/SSH 入口；
- 当前授权仅限只读，而下一步是会分配内存/临时磁盘的 induced-load；
- 只读证据需要输出 credential、完整 argv、IP、私人路径或业务数据；
- 单一 Codex Runtime 即使 constrained profile 也无法保留 host safety reserve；
- safe cleanup/partial checkout 仍无法满足最小磁盘边界；
- 8765/8780 或路径冲突没有可逆方案；
- 任何下一步需要修改既有服务、反代、容器或线上 Status。

## 9. Acceptance

`CB-010` 仅在以下全部成立时为 `passed`：

1. 同一已授权 OVH host 的三次即时 snapshot 与一份有界 induced-load/cgroup
   snapshot 均存在且已脱敏；
2. 真实 `free/df/ss/systemctl` 等价证据覆盖 memory/swap/load/disk/inode、
   port/process/service/container/reverse-proxy/status ingestion；
3. profile calculator 从真实测量生成安全预算，端口/路径与现状无不可逆冲突；
4. AC-064 的 guard/protect/recover、无 OOM、无真实时间等待由可执行 fixture
   和 host/cgroup evidence 共同证明；
5. AC-067 的 clean-shell `--check`、runbook 与实际脚本一致；
6. 当前公共 Status contract 已确认；fixture 与其字段/状态值一致，但不冒充
   已完成线上 CyberBoss row 接入；
7. CB-020 及后续 Task、PG-0–PG-5 均未推进。

没有授权 OVH 入口时，本 Run 可完成所有 repo-local 与公共只读工作，但
`CB-010` 必须保持 `activation_pending`，不得以 simulator/public Status
代替真实 host evidence。

## 10. Run result — 2026-07-26

- Owner 明确要求从本机既有部署记录自动解决目标发现；受保护 Alpha/OVH
  baseline、operate status 与 handover 对同一主资产一致。
- strict known-host、key-only BatchMode SSH 通过；地址、credential 与 key
  material 未进入日志或仓库。
- 同一 host 三次即时 snapshot 完成，选择 `constrained`、
  guard=`recover`、activation-safe=`true`；8765/8780 与四个 canonical
  path 无冲突。
- 现有 Status compose/collector/data/web、cron ingestion、mount 与 Traefik
  只读 whitelist probe 通过，未持久化 raw rows/config。
- baseline 安全门通过后，使用现有镜像、无 pull/network、只读 rootfs、
  非 root、128 MiB memory/swap、32 PID、0.25 CPU 的 ephemeral container
  执行 16 MiB/8 MiB/100 fixture；guard ladder 完整、OOM-kill delta=0，
  container 与远端临时目录已清理。
- `CB-010=passed`；未执行 CB-020、未作 persistent OVH/Status mutation、
  未 push/PR/tag/release。
