# Run Contract — P3.3 / CB-320

## 1. 目标

在不改变 Owner 锁定产品版本 `v0.0.0.5`、设计基线 `v0.0.0.4` 或既有
Cloudflare/Tunnel/Access 控制面的前提下，完成一个本地可复跑的
`cyberboss.access-domain.v1` 薄层：从既有
`implementation-kit/config/identity-scope.policy.json` 派生唯一
`cyberboss.linzezhang.com` 的 route、Access policy、RS256 JWT/audience/origin
verifier 与 privacy-first analytics contract。它只生成原子本地 plan；真实
Access、DNS route、Analytics 和外部端口证据仍保持 `activation_pending`。

上游锚点为已关闭的 CB-310 closure
`183c2a7b624e5ae25c4ba27bb39651ebf207bfb4`。本 Run 只处理 P3.3 / CB-320；
下一原生节点为 CB-330。

## 2. TaskPack 与 Skill Router

- TaskPack：`v0.0.0.7`；ZIP SHA-256：
  `77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`
- Task boundary Router：`webapp-testing`，
  `NATIVE_IF_PRESENT_ELSE_EMBEDDED`，最多一个轻量 Skill body。
- `webapp-testing` body 在本机不可用，故只使用冻结
  `machine/skill_microplaybooks.json` 的 HTTP/DOM/unit-fixture fallback；
  网络获取为 `false`，实际 Skill body load 为 `0`。
- 不加载 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究；不使用
  真实时间等待。

## 3. 最小范围与复用边界

- 复用既有 `identity-scope.policy.json`、CB-020 的 scope/Access contract、
  CB-300 Timeline 与 CB-310 Status closure；不复制或修改冻结的
  `cloudflare_adapter.py`，也不创建第二个 Status、Analytics 或事实源。
- 只允许 `self_hosted`、默认 `deny`、Google/GitHub identity source、Owner slot
  与 non-identity status service-token slot；禁止 `bypass`、`everyone` 与
  `any_valid_service_token`。
- route 只能是受 Cloudflare Access 保护的
  `cyberboss.linzezhang.com`；origin 只能是既有 tunnel 至 `127.0.0.1:8780`。
  Codex Runtime 固定 `ws://127.0.0.1:8765`，不得 proxy 或公开。
- origin verifier 只接受本地提供的 RS256 public-key set，严格检查 signature、
  issuer、audience、`exp`/`nbf` 与 subject；不 fetch JWKS、不记录 JWT、身份或
  原始 header。
- `Cloudflare Web Analytics` 只允许聚合 `page_view` 及 Core Web Vitals 数值；
  URL 必须是固定 UI surface，禁止 query/fragment、prompt、result、私聊、Access
  identity、job/thread ID、cookie/token 与第二统计数据库。

## 4. 验收与验证

映射的 critical Oracle 为 `FA-AC-011`、`FA-AC-022`、`FA-AC-028`、
`FA-AC-032`：

1. anonymous/authorized matrix、错误 audience、坏 signature、direct-origin
   bypass、错误 host/port 和每个受保护 route 均 fail closed；8765 外部状态只能
   为 `unreachable`；
2. Cloudflare route、Access policy、Analytics 只作为本地 declarative plan，
   没有 receipt 时绝不声称 live route 或真实全局 Status；
3. 计划/CLI/evidence 不含真实 secret、完整私聊、稳定执行 ID 或绝对运行时路径；
4. plan 采用 fsync + atomic rename；before-rename crash 保留 last-good，
   after-rename 只留下完整 JSON；
5. 在 credential-name-scrubbed 临时环境执行本节点单测、CLI、既有 Access policy、
   `npm run check`、全 App tests、identity/config、DAG、traceability、no-wait
   和 TaskPack 验证。

## 5. 允许修改

实施阶段仅允许：

- `CyberBoss/app/src/services/access/canonical-access-domain.js`
- `CyberBoss/app/scripts/canonical-access-plan.js`
- `CyberBoss/app/test/canonical-access-domain.test.js`
- `CyberBoss/tests/canonical-access-plan.test.js`
- 本 Run Contract 与 `CyberBoss/scripts/validate_cb320.py`

封口阶段仅允许 `CHANGELOG.md`、`README.md`、`HANDOFF.md`、
`machine/facts/task_state.json` 与 `docs/evidence/CB-320/{summary,subject}.json`。

## 6. 风险、回滚与停止条件

- 真实 Cloudflare mutation 需要分离的 Access/DNS credential、精确 scope
  attestation、真实 route/status receipt 与 Owner 最终授权；缺一项即
  `activation_pending`，宽 account write 为 `hazard_blocked`。
- 回滚为撤销将来的 route/policy，但保留 loopback 服务；本 Run 不实际执行
  撤销或 provider mutation。
- 出现 Runtime 非 loopback、匿名详细 Status、JWT/audience bypass、第二
  Analytics database、真实 secret/PII、macOS `launchd`、任何控制面/运维模型
  调用或第二 Status/事实源，即停止并拒绝封口。
