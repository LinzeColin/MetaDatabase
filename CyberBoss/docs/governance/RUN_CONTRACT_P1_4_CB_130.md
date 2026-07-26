# Run Contract — P1.4 / CB-130 Supervised Loopback Cloud Process Family

## 1. Goal

本 Run 只执行 Task DAG 节点 `P1.4 / CB-130`：

> Run the fixed local cloud bridge and Codex on loopback under one supervised
> process family.

在 CB-100、CB-110、CB-120 已通过的同一授权 OVH 主机上，把精确本地
implementation commit 的 CyberBoss bridge、loopback Codex Runtime 和无凭据
provider simulator 纳入 `cyberboss-cloud.service` 的同一 cgroup；提供可保护的
`/healthz`、`/readyz`、`/status/snapshot.json`，完成单 owner、100 次并发
start、100 次 kill/restart、四类 fault recovery 与 loopback/external scan。

本 Run 不切换 `current`，不 enable 业务 service，不激活真实微信/Codex
credential，不进入 `P1.5 / CB-140` 或 `PG-1`。

## 2. Frozen input and minimum scope

- 输入基线：
  `9e1c128aa3890f7c0ea0e69000fdb46e32a4bb00`；
- 依赖：
  `CB-100=passed`、`CB-110=passed`、`CB-120=passed`；
- 唯一权威：
  `04_TASK_DAG_EXECUTION_PACK.yaml` 的 `CB-130` 与
  `02_PRD_ACCEPTANCE_CONTRACT.md` 的
  `AC-011`、`AC-040`、`AC-044`、`AC-062`；
- 不创建新 repo；canonical code identity 仍为
  `LinzeColin/MetaDatabase/CyberBoss`；
- 完整 Corresponding Source、原许可证、provenance、修改记录和未解决冲突
  随 exact commit artifact 保留；合规表达固定为
  `AGPL-3.0-only AND GPL-3.0-only`，
  `upstream_clarification_received=false`；
- release 固定为 `/opt/cyberboss-cloud/releases/<implementation-commit>`，
  `current` 必须始终解析到
  `b2a603e415a2045b441f31e07cf74ac451ba6240`；
- Node/Codex toolchain 固定使用 CB-110 已安装的项目本地版本；
- workspace 继续使用 CB-120 已验证的唯一
  `/srv/cyberboss-workspaces/cyberboss`，本 Run 不推进其 Git head；
- systemd 主 unit 保持一个，`KillMode=control-group`；只用 `/run/systemd`
  transient drop-in 指向 candidate，验收后删除；
- Runtime 固定 `ws://127.0.0.1:8765`，status 固定
  `http://127.0.0.1:8780`，任何非 loopback 监听立即停止；
- 默认 staging provider 为既有 Weixin/Codex simulator。切换到真实 adapter
  只能通过 root-controlled config，代码路径不变；真实 adapter 保持
  `activation_pending`，不得把 simulator 结果称为真实激活；
- status token 仅存在 `/run/cyberboss-cb130/`，不进入 release、journal、
  evidence、Git 或命令输出；
- 目标地址只从受保护本地部署记录解析并匹配
  `target_id_sha256=7865f743d174`；只用 strict-known-host、key-only
  BatchMode，地址不得落库或输出。

## 3. Required implementation and Oracles

- supervisor 以非 detached child 方式拥有 Runtime、channel simulator 与
  bridge；任何 critical child 异常退出都先令 readiness 失效，再由 systemd
  probe-driven recovery 整个 cgroup；
- bridge journal 只输出 allowlisted lifecycle marker，不转储 account、
  token、消息、prompt/result、完整 child stderr 或 status token；
- simulator staging state 只写
  `/var/lib/cyberboss/cb130-staging`，synthetic account 与真实状态隔离；
- `/healthz` 只表示 supervisor 可服务；`/readyz` 只有三个组件全部 ready
  才返回 200；受保护 snapshot 只含 release、fixture claim、布尔组件状态与
  activation state，不含 PID、路径、identity、token、消息或 target；
- `AC-011`：`ss -lntp` 证明 8765/8780 只有
  `127.0.0.1`，operator-host scan 证明两端口不可从公网地址访问；
- `AC-040`：healthy/ready fixture 为 200/200；受控 unready fixture 为
  200/503；snapshot 无授权拒绝、有 ephemeral token 才允许；
- `AC-044`：100 个 concurrent `systemctl start` 结果、100 个 lock
  contender denial、100 次实际 cgroup kill/restart 均完成；每轮由
  ready predicate 和 invocation change 判断，active supervisor/bridge
  owner 始终各 1；
- `AC-062`：runtime、channel、bridge、whole-service fault 都必须观察到
  non-ready/unavailable，再恢复为 ready；不使用固定时间等待、LLM call 或
  虚假绿色状态；
- evidence 至少包含 redacted journal lifecycle excerpt、normalized process
  family、port/external scan、restart/singleton/fault matrix 和最终清理状态。

## 4. Allowed repository modifications

- `CyberBoss/app/package.json`
- `CyberBoss/app/scripts/cloud-supervisor.js`
- `CyberBoss/app/test/cloud-supervisor.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P1_4_CB_130.md`
- `CyberBoss/docs/product_design/v0.0.0.4/{MANIFEST.sha256,implementation-kit/**}`
  中 CB-130 直接相关 config、scripts、simulator、tests、README、report 与
  manifests；
- `CyberBoss/machine/facts/post-baseline-change-ledger.json`
- `CyberBoss/scripts/validate_cb130.py`
- `CyberBoss/tests/cloud-process-family.test.js`
- `CyberBoss/docs/evidence/CB-130/**`
- closure 时的
  `CyberBoss/machine/facts/task_state.json`、`CyberBoss/README.md`、
  `CyberBoss/HANDOFF.md`、`CyberBoss/CHANGELOG.md`。

其他路径不得修改，尤其是 `CyberBoss/vendor/**`、CB-000–CB-120/PG-0
历史 evidence、Task DAG、PRD、Roadmap、Acceptance、母仓其他项目。

## 5. Local validation

```bash
bash -n \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/health-check.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-cloud-process-family.sh
python3 -m py_compile \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py
node --test CyberBoss/app/test/cloud-supervisor.test.js
node --test CyberBoss/tests/cloud-process-family.test.js
cd CyberBoss/app && npm run check && npm test
python3 CyberBoss/scripts/validate_cb130.py --prepare
```

实现 commit 后，builder 只能从 clean exact worktree 产生 complete source
archive、artifact manifest 与 checksums，且证明 `remote_publication=none`。

## 6. Authorized target sequence

1. fresh read-only preflight 重验 target hash、key-only sudo、CB-120 candidate/
   workspace、service disabled/inactive、current、process/listener、staging
   collision 和 disk reserve；
2. installer `--check` 证明 persistent write/live command 均为 false；
3. 只将 exact artifact set 放入
   `/var/lib/cyberboss/incoming/cb130-<commit>`；
4. 两次 `--apply` 和一次 `--verify` 均绑定同一 commit；第二次必须幂等，
   三次都不得启动 service 或移动 `current`；
5. transient staging prepare 后，从 operator host 执行 8765/8780 external
   scan；
6. 执行 healthy/unready/snapshot、100 concurrent start、100 lock denial、
   100 kill/restart 和 runtime/channel/bridge/service fault matrix；
7. 无论成功失败都 stop/kill 整个 cgroup，删除 transient drop-in、token、
   incoming/transfer artifacts，daemon-reload；
8. 最终确认 service disabled/inactive、current/workspace 不变、process 与
   8765/8780 listener 为 0；真实 credential/provider/data operation 为 0。

## 7. Risks, rollback and stop conditions

- **Detached orphan / duplicate owner：** child spawn 明确
  `detached=false`，unit 保持 `KillMode=control-group` 和 flock。任何 child
  不在同一 cgroup、owner count 非 1 或 stop 后仍存活，立即停止。
- **False green：** readiness 源自组件事件和 live probe；critical child
  exit 先清 readiness。故障期间若仍返回 ready 200，立即失败并回滚。
- **Public App Server：** supervisor、simulator、status 与 env 均做
  loopback fail-closed；`ss` 或 operator scan 发现可公网访问即停止。
- **State/config contamination：** synthetic state 使用专用 staging root；
  token 和 drop-in 只在 `/run`。失败时删除该 transient root，不读取或删除
  真实 credential。
- **Release drift：** archive、manifest、release path、embedded commit 和
  tree 任一不一致即拒绝；existing release 只允许 exact immutable verify。
- **Rollback：** `systemctl stop` + `systemctl kill --kill-whom=all`，删除
  exact transient drop-in/runtime token，恢复 daemon state；`current` 从不
  参与切换，candidate 和 root-controlled staging env 可保留用于审计。
- **硬停止：** Runtime 必须非 loopback、duplicate owner 无法阻止、需要真实
  credential 才能完成 simulator-independent Acceptance、或 target 无法恢复
  到 disabled/inactive 且零 process/listener。

## 8. Completion rule

只有 `AC-011`、`AC-040`、`AC-044`、`AC-062` 的 exact-commit local 与授权
目标 evidence 全部通过、失败/纠正记录完整保留、final cleanup 通过后，才能把
`CB-130` 标为 `passed`。真实 Codex/WeChat 继续
`activation_pending` 不阻塞 simulator/dependency-independent completion；
不得因此声称真实激活。CB-140、PG-1 与后续任务保持 `not_started`，本 Run
不 push、不创建 PR/tag/release。
