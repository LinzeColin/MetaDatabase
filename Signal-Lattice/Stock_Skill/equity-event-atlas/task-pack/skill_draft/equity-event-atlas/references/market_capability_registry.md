# 全球市场能力登记

访问日期：2026-07-26。外部规则会变化，宿主每次运行仍需重新验证相关官方页面、披露和交易日历。

## 1. 两层能力

### 静态覆盖层级

- `DEEP`：内置该市场的主要披露路径、事件语义和时间规则。
- `STANDARD`：已建立较完整适配，但不是当前版本承诺范围。
- `GENERIC`：只保证统一本体与输出契约，不保证市场专属规则完整。

### 动态运行能力

- `FULL`：官方来源、交易日历和时点行情均已验证，且市场为深度覆盖。
- `SUPPORTED_WITH_HOST_DATA`：宿主已提供并验证三类数据，但市场仅有通用本体。
- `RESEARCH_ONLY`：可整理事实或事件，但不足以开放完整预测与主动动作。
- `BLOCKED`：官方来源或证券身份无法确认。

## 2. 深度覆盖

| 市场 | MIC | 监管与披露入口 | 采用结论 |
|---|---|---|---|
| 美国 Nasdaq | `XNAS` | SEC EDGAR 与发行人/交易所正式披露 | `DEEP` |
| 美国 NYSE | `XNYS` | SEC EDGAR 与发行人/交易所正式披露 | `DEEP` |
| 美国 NYSE American | `XASE` | SEC EDGAR 与发行人/交易所正式披露 | `DEEP` |
| 美国 NYSE Arca | `ARCX` | SEC EDGAR 与交易所/指数公司披露 | `DEEP` |
| 美国 Cboe BZX | `BATS` | SEC EDGAR 与交易所/指数公司披露 | `DEEP` |
| 澳大利亚 ASX | `XASX` | ASX announcements、ASX Listing Rules、ASIC | `DEEP` |

### 已核验官方入口

- SEC EDGAR APIs：`https://www.sec.gov/search-filings/edgar-application-programming-interfaces`
- ASX announcements：`https://www.asx.com.au/markets/trade-our-cash-market/announcements`
- ASX historical announcements：`https://www.asx.com.au/markets/trade-our-cash-market/historical-announcements`
- ASIC continuous disclosure：`https://asic.gov.au/regulatory-resources/markets/continuous-disclosure/`

这些 URL 是来源定位，不是静态内容快照。宿主需保存访问时间、实际文件/响应哈希和当时适用版本。

## 3. 通用全球覆盖

当前登记的通用 MIC 包括：

```text
XTSE XTSX XLON XHKG XSHG XSHE XTKS XKRX XSES XETR XPAR XAMS
```

已核验的示例官方披露门户：

- 加拿大 SEDAR+：`https://www.sedarplus.ca/`
- 英国 FCA National Storage Mechanism：`https://data.fca.org.uk/#/nsm/nationalstoragemechanism`

这些市场在 v0.0.0.1 仍为 `GENERIC`。调用方必须提供：

1. 证券身份与 MIC；
2. 该市场官方监管/交易所/发行人披露；
3. 正确交易日历、时区与公司行动调整；
4. 与 `as_of` 一致的行情快照；
5. 对当地披露延迟、停牌和证券类型的解释。

满足后最高升至 `SUPPORTED_WITH_HOST_DATA`，不得自动写为 `FULL`。

## 4. 未登记市场

- 不猜测监管制度。
- 不把搜索结果排名当作权威等级。
- 宿主确认官方来源前为 `BLOCKED`。
- 完成官方来源、日历、证券标识和最小 Fixture 后，可在后续版本登记。
