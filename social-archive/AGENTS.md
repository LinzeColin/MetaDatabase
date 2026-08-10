# Social Archive Agent Contract

继承母仓库根目录规则；冲突按任务包 `CANONICAL_STATE.json` 的权威顺序解决。

## 唯一身份

- 产品：Social Archive
- 目录：`social-archive/`
- 版本：`v0.0.0.28`
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

## 写文档时的一条排版约定（**有一道门在管它**）

**直角引号 `「」` 在这个仓里专表一件事：界面上真有的那个词。**
（这句话本来写成「…那个词」，用直角引号强调——**当场违反了自己刚定的规矩**。
留着这条注记，因为这正是它最容易被用错的方式。）
发布门里的 `check_docs_match_the_ui.py` 会把 docs/ 里每一处 `「…」`
拿去界面代码里找；找不到就红。它存在的理由是：手工扫三次、三次都揪出
文档教用户点一个**不存在的按钮**，而照着旧文档操作的人只会以为是自己错了——
**没有任何东西会报错**，这比代码 bug 更难发现。

所以：

  · 引用界面上的按钮／标签 → 用 `「连接账号」`，而且它必须真的存在
  · **只是想强调** → 用 `**粗体**` 或破折号，**别用直角引号**

2026-08-05 这一天我自己因为混用它被拦了三次（「相同」「恢复顺序」
「一定没有」都不是界面词）。三次都是这道门对——而这条约定**当时哪儿都没写**，
只能靠被拦住才知道。现在写在这儿了。

## 发布门会因为「你不知道规矩」拦住你的那几条

发布门有 22 道。大部分是查缺陷的，**下面这几条不是——它们是对写东西的人
提的要求**。它们此前**一条都没写在文档里**：22 道门，规矩全在门自己肚子里，
每个人都得先被拦一次才知道。

| 你在做什么 | 规矩 | 拦你的那道门 |
|---|---|---|
| 写文档，引用界面上的词 | 直角引号只给**界面上真有的词**；强调用粗体 | `check_docs_match_the_ui.py` |
| 写文档，让人跑某个脚本 | 那个脚本得真的在；`dist/` 那种 gitignore 的产物要先给出造它的命令 | `check_docs_point_at_things_that_exist.py` |
| 写证据文件 | **必须有一段说清「这不能证明什么」**；自锁的 BLOCKED 不许被改写成 PASS | `check_evidence_declares_its_limits.py` |
| 代码里新加一个 error_code | 同时补上对应的中文文案，否则界面只会说「我们没能记录下原因」 | `check_every_failure_code_is_explainable.py` |
| 加一个平台 | 十几张平台表都要提到它；确实该是子集的，登记时**必须写下理由** | `check_every_platform_table_is_complete.py` |
| 改版本号 | 真源是 `pyproject.toml`，其余全部对它；CHANGELOG 要有这一版 | `check_the_stated_version_is_the_real_one.py` |

其余那些 `find_*` 是查「建好了没接上」的六种形态（未引用的符号、没人调的接口、
只写不读的存储键、只有一头的消息、没法设置的配置项、根本不存在的函数），
它们不要求你记住什么——**红了就是真有东西没接上**。

## 开发节奏

- Task：focused tests。
- Stage Gate：该 Stage 集成测试。
- Frozen Candidate：一次完整套件。
- Build Agent 不重新运行市场研究、Teleiosis、Persona 团队或更改验收边界。
