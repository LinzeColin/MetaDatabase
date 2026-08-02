# Social Archive Agent Contract

继承母仓库根目录规则；冲突按任务包 `CANONICAL_STATE.json` 的权威顺序解决。

## 唯一身份

- 产品：Social Archive
- 目录：`social-archive/`
- 版本：`v0.0.0.6`
- Python 包：`social_archive`
- 环境变量前缀：`SOCIAL_ARCHIVE_`
- 私有域名：`social-archive.linzezhang.com`

旧名只允许出现在 `.social-archive-migration/`、迁移测试/验证器和历史 Changelog 中；任何当前 UI、README、代码标识、运行目录或新证据出现旧名均失败。

## 运行边界

- OVH SQLite 只承担 Runtime Journal、Job、Outbox、幂等、游标和可重建 FTS。
- Private-Database 是长期结构化事实唯一权威源；R2 `primary-objects/` 是对象字节权威源；OCI 与 GitHub private Release 是异地/第三副本。
- 默认 L0/L1/L3，L2 手动；达到零费用硬门时暂停 L3，不影响 L0/L1。
- 第三方 GPL/AGPL 工具只能通过独立进程、容器、CLI、HTTP 或文件导入边界调用。
- 不持久化 Cookie、Token、密码、浏览器状态或签名材料；不绕过 CAPTCHA、访问控制、设备风控或加密签名。
- 不自动执行平台账号写操作；B站命令只允许 favorites、watch-later、history。
- 不完整扫描不得关闭关系；两次完整缺失或明确取消事件才允许关闭。
- 每个平台独立 Policy/Auth/Technical Gate、Circuit Breaker 和当前页兜底。
- 运行不依赖开发 Agent、聊天线程、人工保活、Mac 常驻任务或 launchd。

## 开发节奏

- Task：focused tests。
- Stage Gate：该 Stage 集成测试。
- Frozen Candidate：一次完整套件。
- Build Agent 不重新运行市场研究、Teleiosis、Persona 团队或更改验收边界。
