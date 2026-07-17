# 37 — 隔离重测套件与 Run Contract（C/P/R/S 授权阻断项）

## 背景

独立验收 `EEI_acceptance_20260717T203634`（判定 FAIL）在生产面复测 31 项，其中
**4 项被判 BLOCKED**——不是因为产品缺陷，而是因为它们需要对生产做破坏性/高负载
操作，而验收只被授权在生产上做 1 VU / 1 RPS 只读探测：

| 验收 ID | 维度 | 需要什么 |
|---|---|---|
| C-001 | 并发 | barrier 并发写 + 终态断言 |
| P-003 | 性能/容量 | 平均负载→压测/尖峰/浸泡 + SLO 门槛 + 中止闸 |
| R-002 | 韧性/恢复 | 受控故障注入 + 验证恢复（无数据丢失） |
| S-003 | 安全 | 被动→受限主动安全测试（模糊/授权探测/注入） |

本套件把这 4 项从"无能力执行"变成"**套件就绪 + 隔离基线通过**"。所有可安全在
**隔离实例**（本地 wrangler + 本地 D1，或 owner 授权的类生产隔离克隆）上跑的部分
已跑通并留证；生产级规模仍需 Owner 授权（见下方 Run Contract）。

## 套件构成

`scripts/acceptance_retest/`：

| 脚本 | 验收 | 断言的不变量 |
|---|---|---|
| `concurrency_barrier.py` | C-001 | N 个并发 saved-view 更新同报 expected_version=1，**恰好 1 个成功、N-1 个 409、终态 version==2**（无丢失更新） |
| `load_capacity.py` | P-003 | 分级负载（1→4→8→16 并发）逐级测 p50/p95/p99/错误率，对 SLO 断言；含中止闸（错误率≥10% 停阶段保护目标） |
| `fault_injection.py` | R-002 | 请求级受控故障（未知 id/畸形体/畸形 JSON/超长词/缺参）**全部 fail-closed**（结构化错误、无栈泄漏、无 fixture 泄漏），且每次故障后有效请求立即恢复 |
| `passive_security_audit.py` | S-003 | 被动安全（安全头/TLS/CORS/指纹/错误体泄漏/PII）+ 记录主动扫描范围（授权隔离才跑） |

## SLO 门槛（P-003）

API 层（由 docs/28 的交互预算换算到网络往返）：

| 指标 | 门槛 |
|---|---|
| p95 延迟 | ≤ 800 ms |
| p99 延迟 | ≤ 1500 ms |
| 错误率 | < 1.0 % |
| 中止闸（停阶段） | 错误率 ≥ 10 % |

> 交互层门槛（hover<80ms、click<100ms、抽屉<120ms、参数预览 p95<250ms、
> 一层展开 p95<700ms、帧率≥55fps、LCP<2.5s）见 docs/28，由前端 e2e 与
> `validate_visual_coverage.py` 覆盖；本套件负责 API/容量层。

## 运行

```bash
# 隔离实例（本地 wrangler，默认 :8788；先 seed 本地 D1）
python3 scripts/acceptance_retest/concurrency_barrier.py --base http://127.0.0.1:8788 --fanout 16 --rounds 5
python3 scripts/acceptance_retest/load_capacity.py       --base http://127.0.0.1:8788 --stages 1,4,8,16 --per 30
python3 scripts/acceptance_retest/fault_injection.py     --base http://127.0.0.1:8788

# 被动安全（可安全对生产只读跑）
python3 scripts/acceptance_retest/passive_security_audit.py --base https://eei.linzezhang.com --host eei.linzezhang.com
```

每个脚本把结果 JSON 写到 `out/`；交付证据归档到
`_protected/EEI_runtime_evidence/acceptance_reverify/`。

## 基线结果（首轮）

| 验收 | 环境 | 结果 |
|---|---|---|
| C-001 | 本地 wrangler，fanout 16×5 轮 | **PASS**——每轮恰好 1 winner / 15 conflict / 终态 v2，零丢失更新 |
| P-003 | 本地 wrangler，1→16 并发 | **PASS**——各阶段 p95 全在 SLO 内、0% 错误（本地数值非生产代表，见下） |
| R-002 | 本地 wrangler，5 场景 | **PASS**（修复后）——首轮发现真实缺陷：超长搜索词触发 D1 `LIKE pattern too complex` 未捕获 500 泄漏 `SQLITE_ERROR`；已三层加固（截断+转义+捕获）+ 全局 fail-closed 边界 |
| S-003（被动） | 生产 eei.linzezhang.com | **PASS**——安全头 6/6、TLS 1.2+、无指纹、CORS 不反射带凭据任意源、错误体无栈泄漏、公开面无 PII |

> **本地负载数值不代表生产容量**：本地 miniflare D1 是嵌入式 SQLite，延迟极低
> 且 LIKE 复杂度上限（~50 字符）比生产 D1 更严。P-003 的生产级容量结论、R-002
> 的容器级 RTO/RPO、S-003 的主动扫描，都需下方 Run Contract 的授权隔离克隆。

## Run Contract（授权隔离重测所需面）

验收判定书要求的重测面。Owner 授权后按此执行生产级规模：

1. **类生产隔离克隆**——独立 Worker + 独立 D1（非生产 `eei-publication`），
   同构 schema，专用 `*.workers.dev` 或隔离子域，绝不指向生产自定义域。
2. **合成/已批准快照**——用 `smoke_seed.sql` 或 Owner 批准的合成发布面播种；
   绝不用真实 Owner 签核数据做破坏性测试。
3. **专用低权账号**——user-state 授权/IDOR 探测需一个专用低权限账号，
   与生产运营身份隔离。
4. **服务遥测**——隔离环境需暴露 Worker CPU/内存/子请求/D1 读写计数，
   供 P-003 容量结论与中止判断。
5. **工作负载门槛**——平均负载基线→压测→尖峰→浸泡的目标 RPS/时长/并发，
   由 Owner 与本套件 SLO 共同确定。
6. **中止 Owner + 清理命令**——每次跑指定一个可随时叫停的 Owner；跑完用
   `wrangler d1 execute <isolated-db> --file <reset.sql>` 复位隔离 D1。

授权后执行顺序（判定书指定）：barrier 并发 → 平均负载→压测/尖峰/浸泡 →
受控依赖失败 → 被动然后受限主动安全测试。

## 与验收的映射

本套件闭合验收 TEST_MATRIX 的 C-001/P-003/R-002/S-003 四个 BLOCKED 格。
其余 14 个 FAIL + X-003 由 PR #51-#55 的产品修复闭合，生产复测证据见
`_protected/EEI_runtime_evidence/acceptance_reverify/`。
