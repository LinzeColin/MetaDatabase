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

支持二维码、确认、`getupdates`、`sendmessage`、typing、入站注入、消息重放和 send/update 故障注入。开发 Agent 必须按 pin 后的上游接口再次核对字段。

## Codex App Server

```bash
node implementation-kit/simulators/codex-app-server-simulator.mjs
```

默认 endpoint：`ws://127.0.0.1:18765`。它只覆盖 MVP 用到的 initialize/model/thread/turn 方法，不代表 OpenAI 官方 App Server。

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
  implementation-kit/simulators/object-store-simulator.sh put snapshots/a.tar.zst ./a.tar.zst
```

采用 immutable key 语义，可用于 R2/OCI adapter contract tests。
