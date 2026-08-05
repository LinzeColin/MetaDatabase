# v0.0.0.7 交接 — 2026-08-03

接手前只需读三样：本文件、`09_ROADMAP/TASK_DAG.json`、`evidence/T00/CURRENT_TRUTH.json`。
其余结论都已落在证据文件里，**不要重新调研**。

> **`09_ROADMAP/TASK_DAG.json` 不在这个仓里。** 它属于单独交付的 v0.0.0.7 任务包
> （同理还有 `CONFLICT_ORDER.md`、`GOLDEN_TRANSACTION.md`、`10_ACCEPTANCE/`、
> `11_AGENT/`、`03_PREBUILT/`——本文件与 docs/ 里凡是这几个前缀的路径都是仓外的）。
>
> 手上没有任务包时，仓内关于 T00–T18 的记录只有两处，别去别处找：
>
>   · 下面那张 DAG 状态表（每个节点的状态与证据指向）
>   · `evidence/T00/CURRENT_TRUTH.json` 的 `task_classification.tasks`
>     （每个节点一行分类与一句观察，**没有 Acceptance 原文**）
>
> 仓里那份 `machine/task_dag.yaml` 是**封存的 v0.0.0.5 任务包**（SA-xxx，32 条），
> 不是这一版的 DAG。照它做会做错版本。

## 现在真正卡住进度的是什么（2026-08-05）

> **这一段原来写着「能由我推的都推完了」。写完那句话之后，同一天又找出十来个
> 真缺陷**，其中最贵的一个是：交接让 Owner 去点的那颗「连接账号」按钮
> **根本不存在**（设置页的平台表里没有 youtube）。
>
> 所以别把下面这段读成「只剩等人了」。**准确的说法是：我每次宣布推完，
> 再找一轮就还有。** 当天后来找到的还包括——YouTube 去重彻底失效
> （id 在查询串里，而取 id 的表按路径匹配）、库里会把 YouTube 标成
> 「Chrome书签/网页」、八条隐私说明写了但**没有任何界面显示**、
> 目的地覆盖 1/193 而下一步说「最近一次自动导入成功」。
>
> 这些都不是靠再想一遍想出来的，是**改用机器去数、去跑、去问真运行时**
> 才掉出来的。下一个人接手时该假设的是「还有」，不是「没了」。

**卡住进度的不是技术**：下面四件事只有 Owner 能定，我做不了。
但「他不定我就没事可做」是假的——见上面那段。

到今天为止已经闭环的：Owner 的第一步链路（下载 → 装上 → 自动认出 →
接上凭据 → 同步书签）每一环都在真 Chrome 里实测过；耐久性从
「制品三副本、索引一份」补成三份且全部走过完整解密链，并做了一次
552/552 的全量灾难恢复演练；备份 timer **已自主触发过一次**，
产物从 GitHub 那份副本真取回来核过。

剩下的是**四件只有 Owner 能定的事**，按要紧程度排：

1. **age 私钥要不要存第二份、存哪里。** 全机只有一份（按内容哈希全盘搜，
   命中 1 处）。它一丢，R2/OCI/GitHub 上那些副本**一份也解不开**。
   备份脚本一处都不提它——**那是对的**，私钥绝不能进它保护的那些仓。
   放哪里属于信任取舍，而按规矩我不经手也不传输任何密钥材料。
   `doctor.sh` 每次都会提醒这一条。
2. **索引快照的保留期。** 每次库变化留一份，脚本刻意不自动删
   （自动删历史备份是那种「出事才发现」的操作）。
3. **官方 X 接口收不收费。** 它被零费用门（Owner 的 L0 硬边界
   「0 新增必付费用」）主动关着，没有任何授权动作能打开——
   只有确认那个 API 权益绝不收费才行。确认了 x 才能回到「能同步」。
4. **要不要授权 platform canary。** 最小只读探针，默认不读凭据、不访问网络；
   开了才能定期确认平台那一侧还通着。现在它停在
   `OWNER_CANARY_NOT_AUTHORIZED`。

**Owner 可以做的有两件**（第一件是必须的，第二件是刚打开的一条新路）。

### 证据里还挂着 19 条未完成项——**17 条卡在同一个地方**

跑 `python3 scripts/list_open_items.py --verbose` 可以逐条看。2026-08-05 逐条读过一遍：

| 格子 | 条数 | 卡在什么上 |
|---|---:|---|
| T02 | 4 | 他的真实登录 / 两个浏览器 profile |
| T06 + T07 | 8 | **Oracle：需要一次真实平台会话**，也就是他去连一个平台 |
| T08 | 3 | 一个**已登录的** B 站收藏夹页 |
| T12 | 2 | reddit 令牌怎么存（T05 明确拒收 reddit，因为它走 OAuth 不是 Cookie）+ reddit 验收 |
| T18 | 2 | 磁盘（那条已解，见下面）+ **没有 CI 在生产那个 Python 上跑判据** |

**除了 T12 和 T18 新增那条，全部卡在 Owner 身上。** 另两条都不是缺陷、
也不需要他去点什么：

  · T12 那条是设计取舍——T05 是故意拒收 reddit 的，要接得先改那个决定。
  · T18 新增那条是工程约定：本机 venv 是 3.13.14，生产镜像是 python:3.12-slim，
    而这个仓**一条 CI 都没有**。08-05 手工用 3.12.13 跑过一次全量（全过），
    但没有任何东西会重跑它。要么加一条 3.12 的 CI，要么把本机 venv 换成 3.12——
    **两条都是改约定，得有人拍板**。

> 这张表本身返修过两次，两次都值得记着：
> 一次是清单把**已经做完的**也算进去（键名还叫 `still_open`，正文写着「已修」）；
> 一次是我想筛掉误报时**误伤了三条真待办**（写成一句话的「…仍然 NOT_RUN——需要 Owner 登录」
> 被「必须以 NOT_RUN 开头」的规则筛没了）。
> **清单每多报一条做完的，就离狼来了近一步；每漏掉一条真的，就白立在这儿。**

### 二、（可选，但这条最省事）在设置页点一次 YouTube 的「连接账号」

> **这一条在 2026-08-05 之前是做不到的，本文件此前写错了两次。**
>
> 原来写的是「在 YouTube 页点一次「连接」」。两处都错：按钮叫**「连接账号」**，
> 它在**扩展的设置页**（弹窗右上角「···」进去），**不在 YouTube 页面上**，
> 连接也不要求你正开着 YouTube。
>
> 而更要紧的是：`options.js` 的 `platformOrder` 里**根本没有 youtube**，
> 设置页压根不给它出卡片——**那个按钮当时不存在**。
> 也就是说这一条一直是一句做不到的指示。已修（三张表都补上），
> 并在真 Chrome 里核过：设置页 9 张卡，最后一张是 YouTube，按钮「连接账号」。
>
> 正确步骤：**点插件图标 → 右上角「···」打开设置 → 找到 YouTube 那张卡 → 点「连接账号」。**

T06 那格的 Oracle 是「gallery-dl 取到 ≥1 条 Owner 私有条目」，卡在**没有任何
凭据在托管**（08-05 实测 platform_credential 表一行都没有）。可用的平台只有
Cookie 导出白名单里那三个：

  · x —— 压着零费用门，只有他能开
  · instagram —— 授权那步还没有他点得到的界面
  · **youtube —— 什么门都不压**，而他已经是 Google 用户（T02 就是 Google 登进去的）

而 youtube 此前**在服务端凭据表、Cookie 导出白名单、manifest 权限三处都支持，
唯独界面上没有入口**。08-05 由 Owner 裁定接上了。

**B 站那条不行**：国内平台的 Cookie 永远不出浏览器（INV-DOMESTIC-COOKIE-STAYS，
cookie-export 的 FORBIDDEN_PLATFORMS 在第一行就拒）。我一度说「开 B 站时顺手
连一下」——那是错的，已更正。

### 一、（必须）重装插件：重装插件——**而且现在必须重装**。
08-05 修掉了一个「观察器落地太晚、页面加载时打的那个请求一条都抓不到」的缺陷
（自报装好了、就绪了，抓到 0 条）。装旧包点诊断会白点一次。

**还有第二个理由，08-05 傍晚才上线的：** 旧包里，档案馆页面通过桥下发的
「档案馆地址」**不校验同源**——能对桥说话的页面可以改掉「打开档案馆」那颗
按钮的去向，把你送到别人那儿。新包只收同源的地址。

> 说清它有多严重，免得吓着也免得轻看：桥**只**跑在你自己档案馆的域和
> 本机 8765 端口上，且没开 `externally_connectable`——**任意网站打不到它**。
> 要利用得先在你档案馆那个源上执行脚本，或者在你本机占住 8765 端口。
> 是真缺陷、属于纵深防御那一层，**不是远程可利用**。
> 但你手上装的那份仍是旧的：**插件装在你本机，不会自己更新**。

具体做法：从下载页拿包，解压后把文件夹**放进「文稿」**——别留在「下载」，
那是 ERR_FILE_NOT_FOUND 的根因。然后打开 B 站收藏夹页，点一次插件的诊断。
诊断结果会自己存到他的服务器，**不需要他复制任何东西给任何人**。

> **这里不写包的 sha256。** 之前写过一个，而包当天被重打了十几次，
> 那个哈希立刻就陈了——**在最该可信的一段里放一个会陈的数字，是自找的**。
> 要核的时候现场量：部署脚本第 8 道门每次都从机器内部打一次下载路由，
> 比对 content-type 与 sha256，对不上就中止部署。

### 他按完那一下之后，接手的人做什么

1. 读报告：`/var/lib/social-archive/diagnostics/extension-diagnostics.jsonl`
   的最后一条 bilibili 记录。要看的是 **readable_urls**——那是「读得懂的那条
   响应的地址」，拦截前缀就从它身上取。只有 capture_count 而 readable_urls 是
   空的，说明拦到了但一条都读不懂（多半是没登录），让他登录后再按一次。
2. 固化，**在容器里跑**：

   ```
   sudo docker exec social-archive-core-api-1 python /app/scripts/freeze_intercept_prefix.py \
       --platform bilibili \
       --report /var/lib/social-archive/diagnostics/extension-diagnostics.jsonl
   ```

   先不加 `--apply`，看它推出什么前缀，确认无误再加。
   **在主机上跑会报 RUN_ME_INSIDE_THE_CONTAINER**——`.env` 里的密钥路径
   指的是容器里的挂载点，主机上没有那些文件。
3. **别把「写进去了」当成「能同步了」。** 固化只是把前缀写进平台目录；
   今天全仓只有诊断那条路读它，而诊断进门就把它覆盖掉。
   **让同步真的用上这个前缀是 T10**，那一格还没做。

### 要加一个新平台的话（这条路现在是可重复的）

**别去数有几张表。** 接 youtube 那天我数过三次，三次都少数了：
先说四张，补完发现设置页那三张没接（**于是那颗「连接账号」按钮根本不存在**），
补完再扫又冒出四张（popup ×2、sidepanel ×2、options 的 relationCopy），
顺着还揪出 PWA 的 platformMeta（库里会把 YouTube 标成「Chrome书签/网页」）
和 CONTENT_ID_PATTERNS（**YouTube 去重彻底失效**）。

**每一次都是宣布完成之后才发现的。** 所以现在不数了，让两样东西替你数：

  · 发布门第 22 道 `check_every_platform_table_is_complete.py`——全仓扫平台表
  · 下面这个演练——在真 Chrome 里问运行时，包括**真开一次设置页看那张卡在不在**

改完之后跑这个：

```
python3 scripts/build_extension_package.py          # dist/ 是 gitignore 的，得先造
unzip -q -o dist/social-archive-extension.zip -d /tmp/sa-wire
python3 scripts/extension_platform_wiring_drill.py --ext-dir /tmp/sa-wire \
    --platform <平台> --sample-url <该平台一个真实页面> \
    --expect-custody yes|forbidden|not-yet \
    --expect-connect-card        # 真开设置页，确认那张卡和「连接账号」按钮都在
```

第一行别省。`dist/` 在 `.gitignore` 里（第 41 行），克隆下来是没有那个 ZIP 的——
**这一段最初就漏了那一行**，写的人（我）机器上刚好有，于是看不出来。
演练要装的是**下发给 Owner 的那个包**，不是 `apps/browser-extension/` 目录，
所以这一步不能跳：包和源不一样的时候，正是最需要它红的时候。

`--expect-custody` 有**三种**状态，别只想成两种：`yes` = 白名单里有
（x / instagram / youtube）；`forbidden` = 禁止名单里有、白名单里没有
（国内四平台的硬边界）；`not-yet` = 两张表都没有（支持这个平台，但托管
还没做，比如 reddit）。**「还没做」不要拿禁止名单去表达**——那张表是给
「Cookie 永不出浏览器」留的，被当成待办清单用之后就说不清它在表达什么。

它**不证明**这个平台能真的同步——那要等取数通路（T09/T17）。
见 `T06/ADDING_A_PLATFORM_NOW_HAS_A_REPEATABLE_ACCEPTANCE_PATH.json`。

## 2026-08-05 的四个缺陷（都在 Owner 唯一要动手的那条路上）

写了一个回环演练把「拦截 → 读懂」整条链跑一遍，**第一版报 PASS 是假绿**：
它的假页面每 700ms 重发一次请求，观察器无论多晚装上都还能等到下一轮。
真收藏夹页不是这样的——那个请求是加载时打的，打完就没有了。
把假页面改成「加载时发一次」，当场就红了，然后一口气揪出四个：

1. **观察器落地太晚，加载时那个请求一条都抓不到。** 自报 installed/ready
   全为 true 而抓到 0 条。原因是「刷新 → 等 1500ms → executeScript」。
   改成注册 document_start 的内容脚本再刷新，另加一个暂存区补上「脚本已就位、
   前缀还没到」的那段缝。
2. **缓冲区满了丢最早的那条。** 而收藏列表那个请求永远在最早的几条里，
   后面涌进来的全是心跳埋点。改成丢新留早，并把丢掉的条数报出来。
3. **缓冲区从头到尾没人清过。** 「点完没反应就再点一次」是最常见的动作，
   而第二次会把第一次的数进去；换个平台再按更糟。改成每次诊断先清干净。
4. **解析会把最多 200 份响应体一条一个往返传上去。** 几分钟卡死，
   而他不知道是没坏还是坏了。改成按地址去重 + 封顶 30 条，**没读的条数照实说**。

修好的包已经上线，下载页实测下发的就是它。另外把状态页那盏
**永远红着的灯**修了：overall 恒为 degraded 且不可能变绿（9 个连接器 8 个是
能力声明写着「还不能」的），现在只对本该工作的判健康，并新增
not_yet_supported 如实报出还没做的条数。生产实测 overall=healthy、
not_yet_supported=8。

## 每次提交都会看到的那条 git 警告：**别照它说的做**

提交时 git 会反复印这两句：

    warning: The last gc run reported the following...
    warning: There are too many unreachable loose objects; run 'git prune' to remove them.

**它让你跑的正是那条销毁过 2467 个提交、且不可恢复的命令。** 本机铁律 3
明文禁止给 gc 加那个「立刻清掉不可达对象」的参数，而 `git prune` 是同一件事
的另一个写法。

量过了，不值得为它冒任何险：

  · 松散对象约 730 MiB / 11835 个，`.git` 合计 1.1G
  · 本机可用 **622 GiB** —— 那 730 MiB 是可用空间的 **0.1%**

**这一段本来写着「连 gc.log 也不删」，而 2026-08-05 我跑了一次 `git gc`
（不带任何 prune 参数）。** 记下来免得下一个人以为文档和现实哪个错了：

  · 铁律禁的是**给 gc 加「立刻清掉不可达对象」那个参数**，以及等价的
    `git prune`。**不带参数的 `git gc` 正是铁律指定的清理方式**，
    它用默认的两周宽限期，今天产生的对象一个都不会动。
  · 实测收成极小：12394 → 11835 个松散对象，747 MiB → 744 MiB，
    `.git` 还是 1.1G。**这正是宽限期在起作用**，不是它没跑。
  · 它顺带删掉了 gc.log，于是自动 gc 恢复；下次提交那条警告又会回来。
    **那是对的**：自动 gc 用的也是同一个两周宽限期。

所以结论不变，只是理由更清楚了：**这条警告是噪音**。那 730 MiB 会在两周
宽限期到期后被普通 gc 自动收走，不需要任何人做任何事。要动手时唯一安全的
写法是不带参数的 `git gc`（或更保守的 `git gc --no-prune`，一个对象都不删）。

**永远不要跑 `git prune`，也永远不要给 gc 加那个立刻清理的参数**——
它销毁过 2467 个提交，没有后悔药。

## 工作位置

```
worktree  ~/Documents/Codex/GithubProject/_scratch/metadatabase-social-archive-v0007
分支      claude/social-archive-v0007  ← origin/main @ 49bbe45c
sparse    .github + social-archive
台账      ~/.claude/goal/sessions/<session_id>.sa-ledger.json
```

主树 `GithubProject/MetaDatabase` 停在 main、0 脏文件，没被污染（铁律 2）。

## DAG 状态（2026-08-04 二次更新）

| 任务 | 状态 | 说明 |
|---|---|---|
| T00 | **done** | `evidence/T00/CURRENT_TRUTH.json`；另见 `C-T00-01_STILL_BROKEN_IN_PRODUCTION.json` |
| T01 | **done** | `evidence/T01/MIGRATION_COUNTS.json`；`tenancy_audit` 已挂到 `/v1/status` |
| T02 | **done** | 生产实测闭环：Owner 用 Google 真登进去了（oauth_identity 06:23:50Z），三态实测 无Cookie→401 / 伪造→401 / 真会话→200。见 `T02/OWNER_IS_ACTUALLY_LOGGED_IN.json`。**GitHub 那条路仍未被任何真实登录验证过** |
| T03 | **done** | `evidence/T03/REMOVAL_AND_ZERO_TYPING.json` |
| T04 | **done** | 真实浏览器跑通：62 条书签 `queued→completed`，界面表格 62/62 逐条对上；另补 `DELETE /v1/accounts/{id}`（连得上断不开，见 `T04/CONNECT_HAD_NO_INVERSE.json`） |
| T05 | **done（2026-08-05 补了一次真查）** | 凭据托管；HTTP 层往返判据见 `test_credential_http_roundtrip.py`；隐私声明曾与实现相反，见 `T05/PRIVACY_CLAIM_WAS_FALSE.json`。**「值不进日志」这条此前从没真查过**——不是没查，是**验它的工具认不出该找什么**：两道密钥扫描门都认不出 Notion / Obsidian / R2 私密访问密钥，以及 **age 私钥**（占位符过滤按前缀跳过 A 开头的值，而 age 私钥永远以 AGE- 开头）。当天把扫描器补齐后第一次真查：生产运行数据 2119 个文件 + 五个单元近 14 天共 3536 行日志，**0 处命中**。见 `T05/SECRET_VALUES_NEVER_REACHED_THE_LOGS.json` |
| T06 | **partial** | 托管往返实测通过（合成会话）；「一键撤销」已接上。**Oracle 仍未跑，而且是真的跑不了**：08-05 实测 platform_credential 表一行都没有，没有任何凭据在托管。但原来那句「**需 Owner 的 X 登录**」框窄了——Oracle 原文是「gallery-dl 取到 Owner 私有条目」，**没说哪个平台**，任何一个他连上的平台都算；而 X 还额外压着零费用门。他本来就要为 T08 打开 B 站收藏夹页，同一次点一下「连接」这格就有机会一起动。回执里两处已陈：凭据专用 age 密钥**已建好且容器读得到**，downstream 那张表里 T07/T15/T16/T18 早已 done。见 `T06/BLOCKED_RECEIPT.json` 的 rechecked 段 |
| T07 | **done** | Owner 已裁定「cookie 可以进 ovh」；Cookie 已接进 sidecar（tmpfs、0600、finally 里删、值不进日志）。见 `T07/COOKIES_MAY_ENTER_THE_SIDECAR.json` |
| T08 | **partial** | 整条链在真 Chrome 里跑通（回环，不碰任何平台）：注入 → 两个世界通消息 →抓到相对与绝对地址 → **生产解析器读出条目**；连按两次不串味；反例 0 条。08-05 由此揪出并修掉四个缺陷（见下）。真实收藏页仍未验 |
| T09 | **工具就位（2026-08-05）** | 「抓到即固化」原来两头都断：**没人读那份诊断报告**，而且报告里只有 readable_count 这个数字、不说是哪条读得懂。两处都接上了（readable_urls 三段接通 + scripts/freeze_intercept_prefix.py）。拿生产上真报告跑过：**REFUSED / NOTHING_READABLE**——它拒绝从 urls 里挑一个看着像的，那正是它存在的理由。**只差 Owner 按那一下。**
**但固化不等于能同步**：实测（08-05）全仓只有 installNetObserverForTab 读那张前缀表，唯一调用方是诊断按钮，而诊断那条路进门就把读到的前缀**整个覆盖掉**（改用当前页域名推的）；没有任何地方以 diagnostic=false 调它。**让同步真的用上这个前缀是 T10/T11**，那一格还没做。见 `T09/` 下 2 份证据 |
| T10 | pending | 原来只写「依赖 T08 的真实数据（拦截路要 Owner 那次诊断）」。**那句话会把下一个人支到干等**——2026-08-05 逐行核过，T10 缺的是**两处结构**，两处都不需要 Owner 先按那一下：**(1) 没有非诊断的安装路。** 全仓只有一个发送方发 `SA_INSTALL_NET_OBSERVER`（`popup.js:260`），而且写死 `diagnostic: true`；诊断分支进门就把查表得到的前缀**整个覆盖掉**（改用当前页域名推）。也就是说**冻结的前缀表今天是够不着的**——bilibili 那条 `api.bilibili.com/x/v3/fav/resource/list` 早就在表里，却没有任何代码路径会用到它。**观察器在正常浏览时根本不装**（`registerContentScripts` 在 `installNetObserverForTab` 里面，188–323 行；`tabs.onUpdated` 只注 FAB）。**(2) 读懂了不入库。** `/v1/extension/captures/parse` 只把响应读成条目并返回，**不落库**；后台只把 items 数了个数就丢掉。**真正依赖 Owner 那一按的只有一件事**：xiaohongshu / douyin 的前缀还是 null，要靠诊断去发现。bilibili 不需要。（08-05 已先把话说准：那一按现在会明说「这 N 条还没有进你的档案馆」，见 `T08/THE_BUFFER_DROPS_THE_RIGHT_END.json`。） |
| T11 | **投递这一侧大幅前进（2026-08-05）** | 打生产量出来：他连的 GitHub 与 Obsidian **各只收到 1 / 193 条**——不是坏了，投递只在新内容进来时发生，他后来才连上。Owner 裁定「只补 GitHub」，已执行完：**193 / 193，零失败**，写进 LinzeColin/Private-Database，并**把文件从 GitHub 取回来读过**（YAML frontmatter + 标题 + 原始链接，469 字节，不是空文件）。补投不再需要开发者登服务器：卡片上有按钮，接口三条边界（不存在 404 / 没授权 409 / 已齐 0 条）生产实测过。**Obsidian 的 192 条按他的选择没动**——但界面此前把这件事说成了「最近一次自动导入成功」。已改：覆盖不满时那句话会说清差多少、为什么差（投递只在新内容进来时发生）、以及**点哪颗按钮**（档案馆卡片上那颗「把没送过去的 N 条补上」）。见 `T11/` 下 2 份证据 |
| T12 | **done** | gallery-dl 退出码契约取自安装源；`evidence/T12/EXIT_CODE_CONTRACT.json` |
| T13 | **partial（2026-08-05）** | 原来写着「依赖 T10 证明拦截路」——**那是错的**。全仓搜到任务包原话（引自 T02 那份 BLOCKED 回执）：**「沉默不算 BLOCKED」**，讲的是阻塞状态要附真实回执，与拦截路无关，**从来不依赖 Owner 那次诊断**。顺着它修了一处：xiaohongshu/douyin/快手 报的是 HEALTH_PROBE_FAILED / WORKER_PROBE_OR_CALL_FAILED，而那三个探针连的 worker 早在 T03 就被证伪删除——**失败码指着一个故意移除的组件**。已改为报真实原因并把探针码留作 detail 线索，生产实测通过。**Acceptance 原文仍不在仓内**，只按那一句能验的验了。**2026-08-05 又把九个被挡住的连接器逐个看了一遍**：每一个都带真实失败码 + 人话说明 + 下一步，沉默的一个都没有。但抓到一处自相矛盾——youtube 的说明写着「现在可以：连接 YouTube」，紧跟的下一步却说「本版本没有能打开这条路的设置项」，**否掉的正是交接里唯一让 Owner 做的那件事**。成因是同一天接完插件那四张表没回头改服务端这张（第五张表）。已修并落判据。见 `T13/` 下 2 份证据 |
| T14 | **done（2026-08-04 大幅返工）** | 失败文案；两道门已接进发布门。本轮实测推翻了三处「界面说得到、后端做不到」：**插件每分钟抢用户标签页**（藏了按钮而队列照跑；x 也在抢，实测一次抢 2 下）、**SYNCABLE_NOW 四个平台三个是假的**（x 被零费用门关着、reddit/instagram 没有 Owner 能点的授权入口）、**一个太长的抖音标题让 79 条内容一个多月没导出**（safe_slug 按字符截而文件系统按字节算，且单条失败拖垮了整个目的地）。另修：失败任务被永久钉死（接口回 202 而什么都不跑）、34 条内容没有原文件时只给一段截断的英文工具输出。并第一次把生产 payload 灌进真实渲染代码读出 Owner 会看到的那八行字。见 `T14/` 下 12 份证据 |
| T15 | **done** | MV3 worker 之死的恢复；`evidence/T15/WORKER_DEATH_RECOVERY.json` |
| T16 | **done（2026-08-05 大幅加固）** | 制品 **552/552 三副本齐全**（R2+OCI+GitHub），开工前只有 19 个有任何副本。**索引（运行库 sqlite3）此前只有一份**——552 个加密块没有任何东西说得出是什么；现已三副本（每 ~15 分钟跟着制品走、只在库变了时才传；每天补 GitHub 那份）。**取回演练全部走过完整解密链**：制品四个备份包 ×三仓 12 次全 PASS + 一次真写回；索引 R2/OCI/GitHub 各一次，五张表与生产库逐个相同。**全量灾难恢复演练：只用远端副本，552/552 取回且哈希核对通过。**途中修掉三个各自足以致命的缺陷（恢复脚本拿错令牌、内容寻址重复路径被当成损坏、`--target /tmp` 被 PrivateTmp 吞掉而报成功）。**唯一剩下的单点是 age 私钥：全机一份，只有 Owner 能决定第二份放哪。** **2026-08-05 又重量了一遍**（不照抄结论）：552/552 三仓全 verified、零副本为 0、三个 timer 全 enabled/active；备份单元手工触发一次仍 Result=success 且三份远端全 verified。~~**唯一没证明的收窄成一句**：备份 timer 从没由它自己触发过（LAST 是 `-`）~~ → **2026-08-05 04:11 已验：它自己跑了。** LAST = `2026-08-05 03:35:02 UTC`，Result=success，NRestarts=0。而且没停在「日志说 PASS」上——那一次产出的快照**从 GitHub 那份副本真取了回来**，age 解密、gzip 解压、sqlite 打开，4,808,704 字节，五张表（content 193 / user_relation 194 / artifact 552 / object_replica 1656 / destination_receipt 391）与同一时刻的生产库逐个相同。见 `T16/THE_TIMER_FINALLY_FIRED_BY_ITSELF_AND_ITS_OUTPUT_COMES_BACK.json`。**下一个没证明的**：它只自主跑过一次，NEXT 那一栏要到 2026-08-06 03:21 才验第二次。**并且照运维手册那一行真跑了一次恢复**——原来跑不起来（`.env` 指的是容器里的 /run/secrets/…），已修并跑通 status=READY。**private-database 那条链原来只有写、没有读**（scripts/ 下只有 sync_private_database.py）——已补 restore_private_database_drill.py，拿 timer 那次的产物从 r2 与 oci 各取回一次，100 条 fact 逐条核 sha256 一条不差。见 `T16/` 下 14 份证据 |
| T17 | **partial（2026-08-05）** | 原来写着「按定义需要一次真实平台取数」，而同一行又写着 **Acceptance 原文不在仓内**——那个「按定义」引用的是一份谁也读不到的定义，于是先把能量的量了：一条真实 douyin 内容逐站追通（观测 → 2 个制品 → 三仓各 verified → 明文哈希对上且三仓密文哈希一致 → markdown 投递 done → **从 R2 真取回来解密核哈希 PASS**）。**仍缺取得那一站**，那要等 Owner 那次诊断。途中修掉一个真缺陷：主机上根本跑不起来恢复（.env 指的是容器里的 /run/secrets/…）。见 `T17/` 下 1 份证据与 scripts/golden_transaction_trace.py |
| T18 | **已部署（最近一次 2026-08-05T05:1Z）** | 生产跑 0.0.0.7；**C-T00-01 根因修复实测生效**（cli-tools uid/gid 正确、密钥可读、业务路由 401→200）；卡在 scanning 的那条 run 已自行落到终态。见 `T18/DEPLOYED_AND_VERIFIED.json`。**回滚演练已做**（29 秒，三条路由全 200，内容 193 条未动，会话没被踢；见 `T18/ROLLBACK_DRILL_ON_PRODUCTION.json`）。但那次回滚目标只差一个提交，**跨版本/带迁移的回滚仍未验过**，且已无可用的跨版本回滚镜像。**2026-08-05 又部署了一次**（修 youtube 那句自相矛盾的「下一步」）：八道门全过，密钥前后逐字节一致，/v1/accounts 200，下载页下发的就是刚部署的包；部署后用新建的 check_production_matches_the_repo.py 复核，**生产与仓 110/110 逐文件一致、四类差异全空**。见 `T18/PRODUCTION_AND_THE_REPO_NOW_AGREE_FILE_FOR_FILE.json`。**2026-08-05 晚些时候部署被磁盘门挡住**（可用 3.2G < 门槛 5G）：清完所有属于我们的可回收空间后仍差 0.3G——整机 34G 里我们只占 2.4G，大头是 containerd 共享层 12G、/srv/linze 6.8G、/tmp/pytest-of-ubuntu 2.2G，**都不是我们的**。两个可再生的候选（Trivy 缓存 2.5G、pytest 临时目录 2.2G）任一个都够过门，但属于别的项目，**等 Owner 裁定**。腾空间时删掉了回滚镜像，所以**现在这台机器没有回滚点**，下次部署成功即恢复；运维手册已补回滚一节（第一句是「先确认回滚点还在」）。见 `T18/THE_DISK_IS_FULL_AND_ALMOST_NONE_OF_IT_IS_OURS.json` |

## 接手第一件事：~~生产上数据只有一份~~ —— **已解决（2026-08-04）**

> **再更新（2026-08-05）。** 下面那组 549 的数字是 08-04 那天的快照，
> 保留原样作为记录。现在的实际状态：
>
>     制品                  552，**R2 / OCI / GitHub 三副本全部 verified**
>     索引（运行库 sqlite3） **08-04 之前全世界只有一份**——552 个加密块
>                           没有任何东西说得出是什么。现已三副本：
>                           每 ~15 分钟跟着制品走（只在库变了时才传），
>                           每天补 GitHub 那一份
>     取回演练              制品四个备份包 ×三仓 12 次全 PASS + 一次真写回；
>                           索引 R2/OCI/GitHub 各走过一次完整解密链
>     全量灾难恢复演练      只用远端副本，**552/552 取回且哈希核对通过**
>
> 下面那句「GitHub Release 2 ← 唯一还缺的一份」**已经不成立**。
>
> **唯一剩下的单点是 age 私钥：全机一份，只有 Owner 能决定第二份放哪。**
> 它一丢，三份副本一份也解不开。详见 `T16/THREE_COPIES_ONE_KEY.json`。


> **已经不是这样了。** 三个定时器已启用，实测复制跑通：
>
>     制品总数              549
>     R2 已校验             549
>     OCI 已校验            549
>     **两份副本齐全**      549   ← 开工前是 19
>     GitHub Release         2    ← 唯一还缺的一份，卡在一个不存在的仓库
>
> 过程中修掉一个真缺陷：加密缓存里有 33 个 root 属主的分片目录，把以
> socialarchive 身份运行的定时任务永久锁在外面（失败点在**写加密缓存**，
> 不是读源文件，所以症状看着像「读不了」）。详见
> `evidence/T16/DURABILITY_IS_REAL_NOW.json`。
>
> 下面这段是**修复前**的记录，保留作为对照。

    制品总数              549
    有 ≥1 个异地副本       19
    **一个副本都没有**    530
    三副本齐全             2

    social-archive-backup.timer                  disabled / 从未运行
    social-archive-replication.timer             disabled / 从未运行
    social-archive-private-database-sync.timer   disabled / 从未运行

journalctl 90 天内三个 unit 全是 "No entries"。`/var/backups` 里只有
v0.0.0.6 取证阶段的手工产物，**没有任何定时备份**。

不是配置缺失（六项必需配置在 `/etc/social-archive/social-archive.env` 里全在，
四个脚本也都验过：缺配置时退出 3 并打印明确中文原因，不会静默成功）。
**唯一的原因是这三个 timer 从来没有被启用过。**

`prepare_systemd_host.sh` 按设计不启用任何 unit（装好 → 验收 → Owner 显式启用），
那个取舍是对的；缺的是交接**没说要启用哪几个**。已补：脚本末尾逐条列出，
并新增 `scripts/check_durability_units.sh` 在宿主机上复核。

    systemctl enable --now social-archive-backup.timer \
                           social-archive-replication.timer \
                           social-archive-private-database-sync.timer
    bash /opt/social-archive/scripts/check_durability_units.sh

启用后 15 分钟内第一次触发，`journalctl -u social-archive-replication -f`
能看到**唯一还没验过的那一环**：云端凭据是否真的有效。

详见 `evidence/T18/DURABILITY_UNITS_NEVER_ENABLED.json`。

## ~~唯一需要 Owner 裁定的设计问题~~ —— 已裁定并实测（2026-08-04）

**平台会话（Cookie）能不能进那个 24 小时联网的 cli-tools 容器？**

`capture_url` 有两条分支：配了 `cli_worker_url` 走 HTTP sidecar，否则跑本机
二进制。v0.0.0.7 把凭据接到了**本机分支**，而生产走的是 **sidecar 分支**——
所以那次修复在生产上暂时不生效。

> **这一条已经不再悬着（2026-08-04）。** Owner 裁定：「cookie 可以进 ovh」。
> 走的是第二条路——sidecar 的 `/v1/capture-url` 接收 `cookies_txt`。
>
> **生产实测已通过**：`used_cookies: true`，gallery-dl 真的带着 `--cookies <path>`
> 被启动（exit 64 = URL 不支持，说明是在 argv 组装完之后才退出的），
> 哨兵值既不在返回体也不在容器日志里（grep 计数 0），/tmp 下无残留。
> /tmp 实测是 `tmpfs (rw,nosuid,nodev,noexec,size=512m)` 且 ReadonlyRootfs=true，
> 也就是**登录状态从不落盘**。见 `evidence/T07/SIDECAR_COOKIE_CHANNEL_VERIFIED_IN_PRODUCTION.json`。
>
> 备份用的 age 私钥仍然**不进**这个容器——那是另一个答案，没有被这次裁定带走。

下面是当时的两条候选路径，留作记录：

- **不进容器**：改走共享卷传临时文件，或放弃进程隔离让 Core 自己跑工具
- **可以进**：改 sidecar 的 `/v1/capture-url` 接口，让它接收 cookies ← **已采用**

见 `evidence/T06/CREDENTIALS_WERE_NEVER_USED.json`。

## 本轮反复撞到的一个形态：建好了没接上

十次以上，每次都是模块写完、判据写好、全绿，然后才发现没有人在调它：

    failure_copy 词典 / unexplained_zero_runs 审计 / 扩展的 lastResult /
    CredentialStore.materialize / tenancy_audit / /v1/storage/status /
    SA_REVOKE_PLATFORM_SESSION / GET /v1/credentials /
    POST …/receipts/{id}/retry / 六个设不上的配置项

**判据只证明「这个函数写得对」，不证明「有人在调它」。**
到 2026-08-04 已落成**六种形态、六道门**，全部挂在发布门里：

| 门 | 看的是哪一种没接上 |
|---|---|
| `find_unwired_code.py` | Python 里零引用的公开符号 |
| `find_endpoints_no_client_calls.py` | 服务端开着、没客户端请求的接口（**按方法判**，不只按路径） |
| `find_write_only_storage_keys.py` | chrome.storage 写了没人读的键 |
| `find_messages_with_only_one_end.py` | 扩展消息只有一头（有人听没人发／有人发没人听） |
| `find_settings_with_no_way_to_set_them.py` | 代码读它、而任何部署面都设不上的配置项 |
| `find_calls_to_functions_that_do_not_exist.py` | 调用了一个**根本不存在**的函数 |

**新写一道门，第一件事是核它的射程。** 已经写错过五次：
两次漏 `scripts/`（systemd 直接跑它，那也是生产）、一次多算了 `scripts/`、
一次把「验收脚本里有调用」当成「产品里有人调」、一次把
`platform_canary.py` 里的一句 `getenv` 当成「有地方能设这个变量」。
**读的人不是设的人，测试桩不是用户。**

另外两条同样代价高的教训：

- **绿灯本身不是证据。** 新判据写完先做反证——把修复摘掉，看它变不变红。
  本轮有一条判据断言 `'data-revoke-platform' in options`，把整段按钮 HTML
  删掉之后照样全绿，因为 `querySelectorAll("[data-revoke-platform]")`
  那一行里也有这个字符串：**判据被自己要找的选择器满足了。**
- **「在小样本上噪声低」不等于「判据对」。** 第六道门在六个文件上试跑几乎零噪声，
  扩到全 `apps/` 立刻炸出 23 条误报（class 写法 + `require` 解构没认）。

## 这一轮补上的四处「说了但没做」

按发现顺序，都是用户看得见的：

1. **「随时可以一键撤销」是假的。** 服务端 DELETE 路由在、扩展处理体在，
   而没有任何界面发得出那条消息。已接上（设置页每张卡片一颗按钮）。
2. **安装页的隐私声明与产品相反。** 「插件不会把密码、Cookie 或浏览器登录状态
   交给服务器」——对国内四源是真的，**对 X/Instagram/YouTube 是反的**
   （T05/T06 的整套设计就是加密上传）。同一句话的机器版
   （`/v1/extension/bootstrap` 的 `cookie_custody: False`）**由一条判据逐字钉着**。
   已改成如实说明，并把三个写死的断言改成测量。
3. **连得上、断不开。** 连接账号一次点击，此前没有任何反向动作，
   而连上之后每 6 小时自己跑一次。已补 `DELETE /v1/accounts/{id}`——
   **只断连接，一条内容都不删**。
4. **六个配置项代码读它、任何部署面都设不上。** X/Reddit/Instagram 账号扫描
   的身份与 token 全在这个状态：Owner 把该做的全做对了也一条都取不到，
   而没有任何东西告诉他还差什么。身份改成取自已连接的账号，token 补进
   compose secrets 与 `.env.example`。

## 三条必须知道的事实

### 1. 第一处断点不在任务包说的地方

任务包 `WHY_IT_WAS_ALWAYS_ZERO.md` 说六个缺陷「全都长在自研 DOM 抓取器这一层」。
生产实测**不是**：

- `cli-tools` sidecar 读不到自己的 `/run/secrets/cli_worker_token`（Permission denied）。
  密钥属主 `10001:10001` 模式 `0640`，而 compose 给该服务 `group_add` 的是 **GID 980**
  (`socialarchive`)，密钥要的是 **GID 10001** (`socialarchive-secrets`)。加错了组。
  于是 `/health` 正常 200，业务路由一律 401。
- 该错误停在 job 层：job 终态 `failed` / `attempt=4` / `CLI Sidecar 调用失败：HTTP 401`，
  而同一时刻 `sync_run` 仍是 `scanning`、`last_error_code` 为空。界面因此永远「同步中」。

已按 `CONFLICT_ORDER.md` 记为 **C-T00-01**。v0.0.0.7 把 B 站改走浏览器拦截路后
该 sidecar 路径预计被取代，但**若新设计任何环节复用同一 secret 编排，
必须在 T10 前显式核对 GID**。

### 2. origin/main 的测试套件本身不是绿的

干净基线（origin/main）：**288 passed / 11 failed**。
分属 T03/T04 等后续任务射程。清单在 `evidence/T01/MIGRATION_COUNTS.json`
的 `pre_existing_failures`。

HANDOFF.md 记的「235 passed」已过时。
**不要拿「全绿」当可用判据**——`GOLDEN_TRANSACTION.md` 本来就把它列在
「不能拿来当 PASS 的证据」里。

**当前分支：550 passed / 0 failed**（2026-08-04）。

那 11 条（后期收敛为 7 条）已**全部结清**，逐条查清成因：2 条字段改名、
3 条 v0.0.0.6 换界面留下的陈旧标记、1 条**直指生产事故根因**（cli 镜像缺
`useradd --gid socialarchive`，正是 C-T00-01）、1 条钉 UI 文案而非不变量。
详见 `evidence/BASELINE_FAILURES.json`。

**教训：不要把「基线失败」当背景噪音。** 那个标签把「我还没弄懂」
包装成「与我无关」，而其中一条一直在指名道姓地说出生产事故的根因。

### 3. 生产环境访问

```
ssh linze-ovh                                    # OVH VPS，密钥在 _protected/
服务目录  /opt/social-archive
运行库    /var/lib/social-archive/runtime/social-archive.sqlite3
Core API  http://127.0.0.1:18765                 # 注意不是 8765
```

**8765 端口被另一个 websocket 服务占着**，直连会得到
`400 Connection header did not include 'upgrade'`——那不是 Social Archive 的故障。
compose 暴露的是 `8765/tcp -> 127.0.0.1:18765`。

## T01 的设计取舍（改之前先读）

租户锚定在 **`source_account` / `user_relation` / `platform_collection` / `sync_run`**
四张关系表。**`content` 与 `artifact` 有意不带 `user_id`**：

> content 是内容寻址、全局去重的（`UNIQUE(platform, external_content_id)`）。
> 两个用户收藏同一条帖子时它只有一行，`user_id` 只能记下「谁先到」——
> 那是一个看着像隔离、实际谁都拦不住的列。真正的所有权边是 `user_relation`。

`tests/focused/test_tenancy.py::test_content_and_artifact_stay_shared` 把这个决定钉住了。
将来有人「顺手」给 content 加 `user_id` 会在那里失败。

隔离入口是 `RuntimeStore.for_user(user_id) -> TenantScope`。
**API 层不得直接用裸 store**（裸 store 留给 worker 与运维路径，它们要跨用户看作业队列）。

迁移**尚未上生产**：旧镜像的 INSERT 不带 `user_id`，只推 Schema 会立刻造出
T01 Acceptance 禁止的孤儿行。迁移随新镜像由 `initialize()` 一起上线，归 T18。
T18 部署前必须先 `sqlite3 .backup` 取快照并交给 `scripts/rollback_0007.sh`。

> **注意：这份交接原来写的是「已实证可用」，那句话当时没有依据。**
> 2026-08-04 第一次真跑演练，当场炸出一个数据丢失缺陷：撤销回滚与前一次
> 回滚发生在同一秒时，备份文件名（只精确到秒）会**覆盖它正要恢复的那份
> 快照**，脚本照样打印「✓ 回滚完成」而 users/session/platform_credential
> 整批消失。已修并加判据，见 `evidence/T18/ROLLBACK_DRILL.json`。
> 另：**只回滚数据库不够**——v0.0.0.7 的代码一启动就会把迁移静默重做一遍。
> 正确顺序是「先停服务 → 回滚代码 → 回滚数据库 → 再启动」。

## T02 卡在哪

制品与测试已闭环（`src/social_archive/auth.py`、session 表、23 个测试）。
Acceptance「Owner 在真实浏览器用两个 provider 各登录成功一次」**未达成**。

已完成的外部准备：

- **GitHub**：OAuth App 已建。App `3769969`，Client ID `Ov23lifw8qvwMxrAOtH6`。
  **client secret 尚未转运到生产机**（只显示一次，可能需要重新生成）。
- **Google**：项目 `social-archive-504412` 已建，同意屏幕配到第 4 步
  （App name `Social Archive`、External、支持邮箱已填），
  差最后勾选 "I agree to the Google API services user data policy" 再点 Create。
  **这一步是 Owner Gate**（`owner_gates.legal_or_brand_change=false`），不得代勾。

凭据就位后要设的环境变量：

```
SOCIAL_ARCHIVE_GITHUB_CLIENT_ID
SOCIAL_ARCHIVE_GITHUB_CLIENT_SECRET_FILE
SOCIAL_ARCHIVE_GOOGLE_CLIENT_ID
SOCIAL_ARCHIVE_GOOGLE_CLIENT_SECRET_FILE
```

回调地址（差一个字符就 `redirect_uri_mismatch`，结尾没有斜杠）：

```
https://social-archive.linzezhang.com/v1/auth/github/callback
https://social-archive.linzezhang.com/v1/auth/google/callback
```

## 两次判据自身出错的记录

写在这里是因为它们会再犯。

1. **铁律 hook 装上了但一次都没生效**。本机 `/usr/bin/python3` 是 3.9.6，
   跑不了 `str | None`（PEP 604 要 3.10+），hook 在 import 阶段 TypeError
   然后按兜底逻辑**静默放行**。加 `from __future__ import annotations` 修好。
   → 装了门就要实测它真的拦得住，不能只看它「装上了」。

2. **「路由没挂上」是误判**。用 `app.routes` 里有没有那几条路径当判据，
   得出「auth 路由没注册」的结论——但 FastAPI 0.141 会把带 prefix 的 router
   挂成 `Mount`，路由藏在 Mount 内部，`app.routes` 根本看不到，而实际请求一直是通的。
   差点据此去改本来没问题的代码。判据已改成打在端点响应上。
   → 判据要打在可观察行为上，不是内部结构。

## T03 进度与剩余（引用面已实测，不必重新摸）

Acceptance：「全仓 grep 不到 DOM 抓取与配对码实现；扩展可用且全程无需用户输入任何字符」。
Oracle 含「撤销令牌后扩展上行得 401 且界面显示中文提示」。

### 已完成 1/3 — 三个被证伪的 HTTP worker

已删 `compose.workers.yaml`（整个文件只有那三个 worker）+ `scripts/start_workers.sh`
+ `scripts/stop_workers.sh`。原先 6 个「断言 worker 存在」的测试**反转**成了
`tests/focused/test_superseded_paths_stay_removed.py`（守卫打在内容形态
`main.py` + `- api` 上，不只看文件名；两向都实测过）。

混在其他文件里的 3 个过时测试是**逐函数剥离**的，没整文件删——
`test_openapi_probe_connector.py` 与 `test_xhs_connector.py` 里仍有有效覆盖。

### 剩余 2/3

**(a) DOM 抓取器** `apps/browser-extension/content/account-mirror-core.js`（340 行，
末尾挂 `globalThis.SAMirrorCore`）。

> ### ⚠️ 这个文件**不能整体删除**——里面有一半是 T04 的地基
>
> 名字叫「账号镜像核心」，但 17 个导出干净地分成两半，实测确认：
>
> | 抓取器（T03 要删） | 通用工具（**必须留**） |
> |---|---|
> | `PLATFORM_SPECS`（DOM 选择器表，74 行） | `flattenBookmarksTree` ← **T04 脊柱的 Chrome 书签靠它** |
> | `extractCandidates`（主扫描器） | `chunk`（background.js:419,561） |
> | `ensureRelationScope`（产出 `RELATION_TAB_NOT_FOUND` 的就是它） | `canonicalUrl`（background.js:630,632） |
> | `relationTabIsActive`（选中态判定，缺陷 #4） | `preferExistingPlatformTab`（background.js:385） |
> | `detectLoggedIn` / `discoverCollectionScopes` / `collectionFromElement` | `externalId` / `relationFromUrl` / `cleanText` / `safeIso` |
> | `isAtBottom` / `explicitEnd` / `totalHint` / `completionProof` | |
> | 三个 DOM 文本正则 `END_TEXT` / `LOGIN_TEXT` / `TOTAL_TEXT` | |
>
> **整文件删会把 Chrome 书签一起删掉，而那正是 T04 走通脊柱的第一个来源。**
> 正确做法是剥出抓取器那半、保留工具半，并把文件改名（`mirror` 这个词
> 在剥完之后已经名不副实，留着会诱导下一个人再删一次）。
>
> 本会话实际试过一次：剥完 340 → 122 行、`node --check` 通过，但
> `background.js` 还有 **10 个调用点**（352/374/490/515/534/548/677/735/766）
> 指着被掏空的符号，且 4 个测试文件共约 16 个测试断言抓取器存在
> （`test_scan_platform_isolation` 5 个、`test_extension_account_mirror_core` 7 个、
> `test_v006_account_mirror_contract` 4 个、`test_extension_e2n_contract` 5 个）。
> 因余量不足以一次做完而**已回退**——半掏空的编排层比没开始更难接手。
>
> `content/account-mirror.js`（188 行）是抓取器的 content-script 一侧，同批删。
>
> ### ⚠️ 再深一层：`PLATFORM_SPECS` 自己也是混的
>
> 第二次尝试才发现的。它不只是 DOM 选择器表，每个平台条目里还有：
>
> | 字段 | 是什么 | T08 拦截路还要不要 |
> |---|---|---|
> | 各种 `selector` / `tab` / `item` | DOM 选择器 | 不要，删 |
> | `label` | 平台中文名（界面文案用） | **要** |
> | `home` | 平台首页 URL | **要**（拦截也得先导航过去） |
> | `relationUrls` | 每种关系对应的页面 URL | **要**（"B站收藏夹在哪个 URL"） |
> | `relations` | 该平台支持哪些关系类型 | **要**（`runBrowserAccountSync` 用它发起同步） |
>
> 也就是说 T03(a) 不是"删掉一个抓取器"，而是**把一个文件拆成三份**：
> DOM 选择器（删）／平台元数据（留，T08 要用）／通用工具（留，T04 要用）。
> 照字面理解去删，T08 得把 `relationUrls` 重新造一遍。
>
> **建议：把这件事当成 T03 与 T08 之间的一次共享重构来排期，而不是 T03 内部的
> 一次删除。** 具体做法建议先新建 `content/platform-catalog.js`（元数据）与
> `content/extension-utils.js`（工具），把 `background.js` 的引用切过去，
> 确认测试仍绿；再删 `account-mirror-core.js` 与 `account-mirror.js`。
> 分两个提交，中间那步是可回滚的安全点。

引用面**已实测**共 6 处：

| 文件 | 处理 |
|---|---|
| `apps/browser-extension/background.js` | **最难的一块**——它驱动整条扫描编排。删抓取器等于要重写编排层，而替代品（MAIN-world 拦截）属于 T08。建议 T03 只拆到"不再调用 DOM 扫描"，拦截实现留给 T08 |
| `apps/browser-extension/manifest.json` | 从 `content_scripts` 摘掉 |
| `tests/focused/test_extension_account_mirror_core.py` | 整体过时，反转为守卫 |
| `tests/focused/test_v006_account_mirror_contract.py` | 整体过时，反转为守卫 |
| `tests/focused/test_scan_platform_isolation.py` | 需逐函数看，可能有仍有效的覆盖 |
| `tests/focused/test_extension_e2n_contract.py` | 同上 |

**(b) 配对码链路** — 未做。**动手前务必先读下面这个区分，否则会删错东西。**

> ### ⚠️ 「配对码」和「共享 API 令牌」是两个东西，只删前者
>
> 它们在代码里挨得很近、名字也像，但机制不同：
>
> | | 配对码 | 共享 API 令牌 |
> |---|---|---|
> | secret 文件 | `social_archive_pairing_code` | `social_archive_api_token` |
> | Settings 字段 | `pairing_code_file` | `api_token_file` |
> | 语义 | **一次性**、十分钟过期、要用户**手抄** | 长期共享 bearer |
> | T03 要删的 | **就是它** | **不是它** |
>
> T03 的原文是「删除配对码签发/输入/校验全链路」。被 `CONFLICT_ORDER` 废止的
> 理由也只针对配对码：「十分钟有效期与手抄验证码本身就是技术门槛」。
> `api_token_file` 没有这个问题，删它会顺手把 `require_token` 的兜底一起拆了。
>
> 注意 `settings.pairing_required` 这个名字有误导性——它实际是**总鉴权开关**
> （`require_token` 第一行 `if not settings.pairing_required: return` 直接早退，
> 什么都不校验），不是「是否启用配对码」。删配对码时**不要连它一起删**，
> 建议改名为 `auth_required` 并单独一次提交，免得混进删除的 diff 里看不清。

`api.py` 里属于配对码、可以删的（约 250 行）：

- 常量 `PAIRING_PATHS` / `PAIRING_BODY_LIMIT_BYTES` / `PAIRING_RATE_LIMIT_PER_MINUTE` / `PAIRING_STATE_FILENAME`
- `PairingRateLimiter` 类与 `pairing_rate_limiter` / `pairing_state_lock`
- 中间件 `pairing_body_limit`
- `_read_pairing_record` / `_pairing_state_path` / `_read_pairing_state` / `_write_pairing_state`
  / `_pairing_record_is_live` / `_pairing_attempts_remaining` / `_pairing_client_key`
  / `_normalize_pairing_code` / `_exchange_pairing_code`
- `require_pairing_edge`、`PairingRequest` 模型
- 三条路由 `/v1/pairing/status`、`/v1/pairing/exchange`、`/v1/pair`
- `config.py` 的 `pairing_code_file`

测试侧 11 个文件引用 pairing，逐个看——有些只是用它做鉴权夹具，改用扩展令牌即可，
不必整文件删。

**(c) 扩展长期可撤销令牌 — 已完成。** 三层都通了：

- 存储：`RuntimeStore.issue_extension_token / resolve_extension_token / revoke_extension_tokens`
  （只存 sha256；签发时自动撤销该用户旧令牌）
- 端点：`POST/DELETE /v1/auth/extension-token`（要会话，用户不接触令牌文本）
- 鉴权：`require_token` 已先认扩展令牌

Oracle「撤销令牌后扩展上行得 401」已在 HTTP 层被
`test_extension_token_authenticates_protected_api` 证明。

> 那条测试里埋了一个坑的记录，改它之前先读：`pairing_required` 默认为 False 时
> `require_token` **直接早退不做任何鉴权**，那时「带令牌得 200」是假阳性。
> 所以判据第一段必须先断言「不带凭据被拒」，否则后面的 200 说明不了任何事。

> 顺序建议：先做 (b) 和 (c)——它们互补（撤掉配对码的同时补上令牌，扩展始终可用），
> 且不依赖 T08。(a) 里 `background.js` 那部分最好与 T08 一起做，否则会出现一个
> "抓取器删了、拦截还没有"的空窗期，扩展在那段时间是装得起来但什么都做不了的。