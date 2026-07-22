# Versioned Contracts

`TSK.x2n.foundation.002` 冻结的当前版本为 `1.0`：Pydantic model/常量是生成真源，
`schemas/v1/`、`registry/*.v1.json` 与 `types/contracts.ts` 是确定性生成物。所有
model 默认 `extra=forbid` 且只接受精确版本；未知字段、未知版本和未知 Native action
不得静默降级。

`payload_hash` 固定为 UTF-8、对象 key 排序、compact JSON、safe-integer-only 的
SHA-256；生成的 TypeScript 同时导出 `canonicalPayloadJson` 与
`computePayloadHash`，避免 Extension 与 Python 使用不同规范化算法。

本包只有 Contract 与纯验证逻辑，没有 Host、Job、SQLite、浏览器、平台、Sink 或网络
实现。Native `page_url` 只允许六平台规范页面 host/path；媒体只能用不透明
`ephemeral_media_ref_id` 表示。媒体 URL、Cookie/Header/Token、Shell、任意本地路径
和任意代理 URL 没有可持久化字段。

```bash
PYTHONPATH=packages/contracts/src uv run --frozen --package x2n-contracts \
  python -m x2n_contracts.generate --check
npm run check:contracts:types
```

`ACC.x2n.ext.003`、`ACC.x2n.data.001`、`ACC.x2n.data.003` 在本 Task 只声明并验证
Contract 范围；真实 Native Host/Job Ledger、SQLite FK/Integrity/Migration 和
Markdown/Notion Canary 仍为 `DOWNSTREAM_NOT_RUN`。
