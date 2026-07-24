# 最新 Timeline 数据产品

## 1. 用户价值

用一张最新图展示 Moomoo 报表标称日期、Gmail 到达悉尼时间、延迟、周末/美国休市背景和邮件生命周期，使异常到达、月结单和处理状态一眼可见。

## 2. 唯一资产

- 固定 Release：`moomooau-live`；
- 固定加密 Asset：`timeline-latest.png.age`；
- 健康稳态固定资产恰好 1，任何时刻最多 1；
- Git 树、LFS、Actions Artifact、Cache、本地均不保存 Timeline 图片；
- 历史事实存在 Processed Timeline Events，不重复存历史图。

## 3. 时间口径

- 到达事实：Gmail `internalDate`，UTC 保存；
- 展示：IANA `Australia/Sydney`，自动 AEST/AEDT；
- 报表业务日期：`statement_label_date`，不因悉尼时区改写；
- `elapsed_hours`：精确小时；
- `calendar_lag_days`：悉尼日历日差；
- `us_market_session_lag`：美国市场日历会话差；
- Trash 进入时间无法从历史证明时为 `null`；
- 没有独立活动证据时未收到报表是 `NOT_OBSERVED`，不是 `MISSING`。

## 4. 视觉要求

- 横轴：悉尼当地日期；
- 圆点：报表标称日期；
- 方块：Gmail `internalDate` 换算后的悉尼到达日期；
- 连线：同一报表；
- 标注：日历日差和可选美国市场会话差；
- 月结单/财年汇总使用独立形状；
- 周末和美国市场休市可采用背景带；
- 图例和标题不出现账户号、金额、Ticker 或完整邮件主题；
- 渲染容器、字体、排序、DPI 和 Metadata 固定，保证语义可重现。

## 5. 串行替换与确定性修复

1. 从已提交 Processed 确定性计算 Snapshot Root，并确认固定 Asset 数量不超过 1；
2. 若加密私有发布状态记录同一 Snapshot Root，重取当前 Asset、校验密文摘要、解密并校验明文摘要；全部一致时不渲染、不上传；
3. 状态缺失、不一致或资产为零时，在 tmpfs 确定性生成 PNG 并先计算明文摘要；
4. 当前 Asset 解密后的明文摘要若与候选相同，只修复加密状态，不替换 Asset；
5. 明文确有变化时才 age 加密；每次密文使用新的安全随机数，因此不得比较密文字节判断业务变化；
6. 在同一临时 Job 解密候选并验证明文摘要，再重取和验证当前固定 Asset，随后删除旧固定 Asset；
7. 以同一固定名称上传候选并回读校验远端大小、密文摘要、可解密性和明文摘要；
8. 成功后用一个私有仓 Commit 写入加密发布状态，确认固定 Asset 数量为 1，并清理 tmpfs；
9. 删除后上传失败时发布 `TIMELINE_REPAIR_REQUIRED`，资产数量保持 0；下一次运行必须从同一已提交 Processed Snapshot 重建后才能发布更新事实。

协议不创建临时或备份 Release Asset，不写 Git/Artifact/Cache，因此不能声称平台提供原子替换。age 密文摘要只证明传输和远端恢复完整性；逻辑幂等只由 Snapshot Root 与已验证明文摘要裁定。
失败状态不影响 Raw 归档，但必须可判定、可重试且不得虚报健康。

## 6. Acceptance

- `AC-028`：健康稳态恰好 1、任何时刻最多 1、历史图片 0、零资产修复成功率 100%；
- `AC-029`：时区、DST、休市和报表日期正确；
- `AC-030`：无依据 Missing 误报 0。
