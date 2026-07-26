# Provider Simulators

这些 simulator 用于在真实微信扫码、Codex device auth、Private-Database/R2/OCI
凭据尚未注入时完成非激活层开发和确定性故障验证。它们不得被报告为真实 provider 已通过。

## WeChat iLink

```bash
node implementation-kit/simulators/weixin-ilink-simulator.mjs
curl -fsS -X POST http://127.0.0.1:19080/admin/inject \
  -H 'content-type: application/json' \
  -d '{"text":"ping","count":1}'
```

支持二维码/login state、`getupdates`、`sendmessage`、typing、empty batch、
入站注入、候选 cursor、反序 batch、重复 update、stable source/context ID、
provider receipt 与 duplicate ack。`/admin/fault` 可为 get/send 分别排队
`401|403|429|500|503|timeout|connection_reset`；send 另支持
`unknown_outcome`（provider 已记录但 client 未收到 ack）。所有 timeout 都是
立即返回的 deterministic fixture，不执行真实等待。

`GET /admin/fixture` 是明确标注 `SIMULATOR FIXTURE — NOT REAL WECHAT` 的本地
截图页，不含真实账号、token、QR payload 或私聊。开发 Agent 必须按固定上游
接口再次核对字段，不得把 simulator 证据报告为真实微信通过。

## Codex App Server

```bash
node implementation-kit/simulators/codex-app-server-simulator.mjs
```

默认 endpoint：`ws://127.0.0.1:18765`。Simulator 从 `CyberBoss/app` 已锁定
的 `ws` dependency 加载，不要求在 implementation-kit 内复制依赖。它覆盖：

- initialize → initialized gate、重复/未初始化拒绝；
- model/thread start/resume/list/compact；
- turn start、progress delta、approval server request/response、completion；
- retryable/terminal error、interrupt、bounded queue overload
  `-32001 / Server overloaded; retry later.`；
- process crash/reconnect、false-success、late/duplicate event；
- `simulator/state` 中的 artifact count/SHA-256 completion Oracle。

测试可用 simulator-only `simulator/setScenario` 选择
`success|approval|retryable_error|terminal_error|overload|cancel_hold|
false_success|late_duplicate|process_crash`。这些控制方法不属于 OpenAI
协议，不得由 production adapter 调用。Simulator 的 on-wire JSON-RPC header
按当前 App Server 文档省略，且两份 simulator 都拒绝非 loopback bind。

完整验证：

```bash
node --test implementation-kit/tests/simulator-contract.test.mjs
```

它是 CyberBoss MVP contract fixture，不代表 OpenAI 官方 App Server 或真实
Codex auth 已激活。

## Private-MetaDatabase canonical

```bash
root="$(mktemp -d)"
implementation-kit/simulators/private-db-simulator.sh "$root" init
implementation-kit/simulators/private-db-simulator.sh "$root" \
  ingest Private-MetaDatabase ./event.json --domain CyberBoss
```

第一个 `root` 参数只用于隔离 simulator 状态；其后的命令行与当前治理真源
`private_db_client.py` 的 `ingest/get/list/verify` 子集一致。它提供
content-addressed 假实现，以及
`CB_SIM_PRIVATE_DB_FAULT=403|409|429|outage` 的确定性故障注入。它不 clone、
fetch、push 或模拟 Git remote；真实 canonical 数据仍只能通过
`private_db_client.py` 写入 `Private-MetaDatabase`。

## Object store

```bash
SIM_OBJECT_STORE_ROOT=/tmp/cyberboss-r2-sim \
  implementation-kit/simulators/object-store-simulator.sh \
  put ovh-singapore-vps-1/snapshots/a.tar.zst ./a.tar.zst
```

采用 immutable key 语义。Simulator 锁定 `provider=r2`、
bucket=`cyberboss-cold` 和 `ovh-singapore-vps-1/` 前缀；测试可以通过
`SIM_OBJECT_STORE_REQUEST_BUCKET` 证明越界 bucket 被拒绝。OCI 使用独立的
`oci_object_adapter.py --backend mock`，避免把两家 provider 的身份混在一起。

Private-DB simulator 同样只接受 `Private-MetaDatabase` 与
`domain=CyberBoss`。所有 simulator 结果只证明本地 contract，不证明真实账号
或云服务已经激活。
