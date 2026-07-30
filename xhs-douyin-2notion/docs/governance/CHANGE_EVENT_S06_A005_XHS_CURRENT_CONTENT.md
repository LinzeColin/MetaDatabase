# Owner Change Event — CE-X2N-20260729-S06-A005-XHS-CURRENT-CONTENT

## Owner 决策

Owner 授权将本次 `TSK.x2n.assurance.005` 直接 MVP 中的“小红书点赞 20 条”替换为
“小红书当前内容 20 条”。本事件只变更该任务的真实 Owner MVP 基线，不删除或缩小产品长期的
小红书点赞能力目标。

## 受影响的有界范围

本次基线仍严格为四个范围、每个范围 20 条、合计精确 80 个关系：

| 范围 | 关系 | 执行方式 |
|---|---|---|
| 小红书收藏 | `saved` | 一个显式可见列表操作，禁止自动滚动/翻页 |
| 小红书当前内容 (`xiaohongshu_current_content`) | `saved_current` | 20 次逐条、显式打开的详情页捕获；每次均由 Owner 手势触发 |
| 抖音收藏 | `saved` | Owner-private 可见 DOM Sidecar 的单次有界操作 |
| 抖音喜欢 | `liked` | Owner-private 可见 DOM Sidecar 的单次有界操作 |

小红书当前内容不得伪装成 `liked`，不得从列表、页脚卡片、后台队列、自动导航、自动滚动、
自动翻页或重试中派生。通用小红书点赞 Adapter 仍保留为 CI 合成能力；它不构成本次 A005
真实范围，也不得被用来声称本次真实点赞支持。

## 证据与隐私边界

- 每一条当前内容在首次 Canonical 写入前，必须与 Owner-private 的 20 项 SHA-256 Manifest 精确匹配；
  不匹配即零写入。
- 在 arm 前，详情页专用按钮只可把已验证稳定 ID 的 SHA-256 加入私有预备集合；它不创建 Canonical
  Job/Content/Relation/Observation，也不保存 URL、标题、DOM 或媒体。四个范围都精确 20 条后才原子冻结
  release input；Owner 不需要手工复制 ID、计算 Hash 或编辑模板。
- Release state 只记录 SHA-256 内容标识与不透明 Native Job ID；聚合验证只输出数量和摘要。
- 不保存或输出原始内容 ID、详情页 URL、平台 CDN URL、凭据、Cookie、Profile 数据或原始媒体。
- 当前范围完成后，才导出确定性的单一范围 receipt；任何重复、缺项或身份漂移均 Fail Closed。

## 验收与回滚

本变更由当前内容 Contract 字段、Native Host 写前 Manifest Gate、20 次显式捕获测试和
Canonical 聚合快照共同验证。尚未发生真实发布、部署或 Runtime 数据迁移；因此本事件的回滚
仅能由新的 Owner Change Event 替换未来 A005 范围，不能修改既有真实数据或历史证据。
