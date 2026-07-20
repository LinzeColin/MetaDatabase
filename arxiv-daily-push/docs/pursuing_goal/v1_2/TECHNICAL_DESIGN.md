# ADP v1.2 技术与运营设计

## 1. 基线与数据流

保留现有 Cloudflare Worker `adp-cloud`、D1 `adp-mirror`、R2 `adp-raw-artifacts`、三个 cron 和 `https://adp.linzezhang.com`。当前锁定 live build 为 `c2ccc1fd01ec`。S0 只落任务包与归档，不修改 Worker、cron、数据库、来源状态或线上配置。

来源数据继续进入现有 adapter/registry，经过解析、去重、内容门和用户中心同步后写入现有 item 结构。v1.2 不做破坏性 schema 迁移；确需字段时只允许增量、可逆并提供旧新版本兼容证据。

## 2. 来源获取契约

计划引入两个可测试结构：

```text
FetchPolicy {
  max_attempts,
  retry_statuses,
  delays_ms,
  timeout_ms,
  fallback
}

SourceFetchResult {
  items,
  attempt_count,
  terminal_status,
  reason_code,
  delays_ms,
  fallback_used
}
```

Google News 候选最多三次尝试，只重试 timeout、502、503、504，延迟为 1 秒和 3 秒。400、401、403、404 以及成功响应但解析为零项不重试。fetch 与 sleeper 必须可注入，使夹具测试不依赖真实网络或真实等待。最坏情况只新增两次外部子请求，并在 Cloudflare 50 次外部子请求上限内核算。

Bing RSS 保持活动来源；Google 只能在本地/CI 正负控与 Cloudflare edge canary 通过后切换。任何失败必须留下 attempt、终态、原因码和 fallback 证据，不得静默写零。

stats-gov 单独区分 `EDGE_TIMEOUT`、`HTTP_STATUS`、`PARSE_ZERO` 和 `SUCCESS`。诊断不能预写“不可达”；如果没有免费、边缘安全且可复跑的修复，则保留降级状态和证据，不用付费代理绕过。

Science Advances 使用 PubMed E-utilities：`ESearch` 以 `"Science Advances"[jour]` 和日期窗口取 PMID，再用 `EFetch` XML 批量取详情，按 PMID/DOI 去重后映射现有 item schema。无 API key，`tool=adp_cloud`，使用项目公共联系邮箱，速率不超过 1 请求/秒；空搜索、坏 XML、错误期刊、重复标识和远端错误均失败关闭。

## 3. 内容与前端契约

- 当没有可靠翻译/解释模型时，人话版输出明确的中文结构化回退，说明已知、未知和原文入口；不得猜测内容。
- 长英文只能放在清晰标识、默认折叠的原文区域，不能占据“人话版”。
- `<780px` 时全部六主题只有“今天／队列／雷达／系统”四个底部标签；桌面 sidebar/topbar/dock 保持原设计。
- 六主题结构、字体、形状和动效语言必须肉眼可辨；三个视频主题必须 muted、loop、真实播放。
- `prefers-reduced-motion` 停止 autoplay 和装饰运动，但功能与静态内容保持可用。
- 视觉门必须包含像素或等价可见 Oracle：非视觉 title 清洗应放行，主题、导航、视频和动效破坏负控必须阻断。

## 4. 双平面与版本身份

机器事实位于 `machine/facts/`，`文档/` 七文件只由 renderer 生成。`docs/HANDOFF.md` 是仓位、live、Owner 决策和当前开发线的唯一入口；本任务包是 v1.2 的活动开发合同。V7.2 `CURRENT.yaml` 继续服务旧本机运行时兼容测试，不得覆盖 v1.2 Cloudflare 开发线。

版本面必须显式区分：

- 当前 live/product：`0.41.0`；
- 任务包及目标产品：`1.2.0`；
- 候选：`1.2.0-rc.N`；
- Python：元数据与 CI 对齐真实最低版本 `>=3.12`；
- build：源码 commit/tree、Worker 自哈希、制品 digest 和部署 identity 可互相映射。

## 5. 观测、SLO 与免费档

保留现有三个 Worker cron。15 分钟只读端点探针由 GitHub Actions 执行，不占新 cron；缺探针记为 UNKNOWN。滚动月可用性目标为 99.5%，探针覆盖至少 95%，每日管线新鲜度不超过 36 小时，RTO 不超过 60 分钟，RPO 不超过 24 小时。

使用 Cloudflare Free 优先；不得自动购买或升级。若请求量、CPU、cron 或存储容量接近免费上限，停止扩张并生成包含测量值、预计成本、收益、回退方案和 Owner 决策位的升级提案。

## 6. 发布、回滚与稳定期

发布顺序固定为 fixture/local → CI replay → isolated D1/R2 → shadow → canary → production。生产前必须锁定上一版本、回滚命令、数据不变量、abort 阈值和 Owner/on-call。用户已预授权“所有阻断门 PASS 后自动部署”，但未运行、缺证据、UNKNOWN、BLOCKED、开放 P0/P1 或无法验证回滚一律不部署。

生产后立即核对 build identity、核心路由、数据新鲜度、来源健康、六主题和 console。任一阻断检查失败自动回滚并标记 `ROLLED_BACK`。只有完成 14 个连续健康日后才标记 `PRODUCTION_ACCEPTED`，不得用 waiver 跳过。

## 7. 安全与公开归档

历史 ZIP 上传前递归检查路径穿越、symlink、加密/重复成员及常见凭据形态。公开仓归档是 Owner 的显式决定；已知绝对本机路径和项目邮箱在披露记录中说明。发现真实凭据时停止提交并要求轮换/清史。归档不改变根 `LICENSE`，也不赋予任何额外许可。

## 8. 恢复与本地清理

合并后从 `origin/main` clean-room 读取归档，重算 SHA-256、执行 `unzip -t`、重新 ingest v1.2 并比较目录摘要。全部通过后才精确删除 Owner Downloads 中本批 ADP 文件；任一证明失败则删除零文件。删除后的恢复来源是 GitHub commit/object 和三份已验证归档，不是本机副本。
