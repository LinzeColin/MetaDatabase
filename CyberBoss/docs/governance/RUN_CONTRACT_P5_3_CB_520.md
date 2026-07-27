# P5.3 / CB-520 Run Contract — 有限请求 Canary 与可逆回滚

## 目标

在 CB-510 已验证的不可变 Linux release 上，执行有限请求数 Canary、一次真实
`current → previous → current` 回滚闭环，以及不依赖真实时间的重启/状态复验。产品版本
固定为 `v0.0.0.5`，不以 WeChat channel pending 状态伪造 E2E 成功。

## 最小范围

- 既有 `/opt/cyberboss-cloud` 的 `current`、`previous`、不可变 release 与
  `cyberboss-cloud.service`；只使用 Linux systemd。
- 同机 loopback 的 `healthz`、`timeline`、受保护 Status snapshot，及已存在的
  Cloudflare Access challenge；不新增公开 origin 或常驻服务。
- 当前 release 的纯本地 input-policy/`/stop` handler 语义，用独立、无模型、无
  Provider 的短生命周期进程复验；真实 WeChat delivery 仍明确为 pending。
- `CyberBoss/scripts/`、`app/scripts/` 的可复跑 canary/封签代码、对应单测与
  `docs/evidence/CB-520/` 脱敏 Subject。

不修改冻结设计、产品版本、Private-Database 真源、Access policy 或 DNS；不 clone
Private-Database，不启动 simulator，不调用 Codex/Claude/LLM，不使用 launchd、固定
sleep、真实时间观察或第二模型。

## 有限请求集合与判定

1. loopback `healthz`、Timeline 和受保护 Status snapshot 的只读成功；
2. 匿名受保护 snapshot 的拒绝，以及公网 Access challenge 的拒绝；
3. 当前 release 对 oversize 输入的拒绝和 `/stop` control-handler 的无模型取消语义；
4. 一次受控 systemd restart 后的精确 release/status 复验；
5. 可逆 mutation：原子切至已验证 `previous`、复验，再原子恢复本 CB-510 `current`、
   复验；spool、canonical 状态和证据不得删除或清空。

任何错误 release、服务/状态不一致、丢失/重复副作用、非零模型计数或无法恢复
`current` 都是 P0：停止新操作，立即固定在可验证 `previous`，输出机器可读失败
receipt。只有所有已适用 predicate 有精确 Subject 绑定证据时才可关闭 CB-520；缺失
真实 WeChat credential 只保留该 adapter pending，不影响其他真实已验证 predicate。

## 验证与回滚

- 先运行本包 CB-520 Router；native `webapp-testing` 不可用时仅采用冻结 fallback，
  Skill body loads=0。
- 运行本地 deterministic canary tests、冻结 TaskPack validator、scope/secret 检查，
  并在目标 release 运行同一 bounded canary，不使用 sleep 或轮询等待。
- 证据仅写 `docs/evidence/CB-520/summary.json` 与 `subject.json`；真实业务/运行时
  数据仍通过无 clone 的 Private-Database 客户端管理。
- 成功路径必须恢复 CB-510 release 为 `current`；失败路径保持经验证的 `previous`，
  不删除 release、spool、备份或历史证据。
