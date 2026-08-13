# Social Archive 交接

> **交给下一个人（或下一个 AI）时，把下面这段整块粘过去就够了。**

```
你要接手的是 LinzeColin/MetaDatabase 里的 social-archive：一个跑在生产上的
个人多平台收藏归档系统（B站/抖音/小红书/Reddit/Instagram/Chrome 书签）。

先读 social-archive/HANDOFF.md，从开头一直读到「六、两条绝对不要碰的」为止
（那一节之后全是历史记录，别照着做）。它会告诉你：现在跑到哪一版、
什么东西没人管也会继续跑、怎么一眼看出它还活着、只有 Owner 本人能做的那一件、
坏了去哪儿查、以及哪两样绝对不要碰。

三条不能破的约束（破了会花钱或泄露登录态）：
1. 云端账单必须恒为 $0.00：禁止 R2 的 InfrequentAccess 存储类，禁止用"整包下载"
   去判断存在（判存在用 HeadObject）。新增周期任务先算月操作量。
2. 国内平台的 Cookie 不出 Owner 的浏览器。服务器上一个都不许有——
   部署第 0.9 步就是专门查这件事的硬闸。
3. 开发一律在 git worktree 里做，主工作树永远停 main、永远干净。

改代码之后必须跑 `bash scripts/deploy_to_production.sh`（在开发机上）：
它自己带一整套真 Chrome 演练 + 发布门 + 部署后从公开域名回读（数目会变，别记死）。
不要用 systemctl restart 代替它——那不会重建镜像，代码改动一个字都不会生效。

判活的一条命令：
curl -s https://social-archive-api.linzezhang.com/health
看 version / worker.alive / backup.stale / replication.stale（后两个要是 false）。
```


**这一节是当前状态（2026-08-13）。下面每个数字都是当天从生产上量出来的，不是记忆。**

## 一、它现在是什么

| | |
|---|---|
| 公开地址 | `https://social-archive.linzezhang.com`（资料库）／ `…-api.…`（接口） |
| 跑着的版本 | **0.0.0.89**（从本机打公开域名读回来的，不是打回环） |
| 生产机 | 见 `deploy/PRODUCTION_HOST`——**唯一真源，别把机器名抄进命令** |
| 你的库 | 内容 **193** 条、关系 **194** 条、制品 **552** 个 |
| 三份副本 | **552 / 552 全部三份已验证，pending 0** |

**「三份副本」不是登记表上的一个数字。** 最后一次部署（2026-08-13）真的做了这件事：

```
runtime-db：3/3 份真取回来了（r2 193 条、oci 193 条、github 193 条）
private-database：1/1 份真取回来了（哈希逐条对）
disaster-recovery：索引里 552 个制品抽了 25 个——**不是全量**
                   （起点每次部署挪一格，所以别记这里的窗口号；
                    当次的窗口写在那次部署日志的 8.69 步）
三份都是真取回来的（下载 → 解密 → 打开 → 判），不是读登记表
```

> **明晚之后这套验证不会再自动跑**（它挂在部署里，而不改代码就不会有部署）。
> 这件事的影响比看上去小：**每一次备份在写进去的时候就当场验过**
> （上传完立刻回读，`verified_remote_copies: 2` 才算数），而恢复那段代码
> 之后也不会再变。**真正会悄悄烂掉的面很小。**
>
> 要自己重跑一次：`docs/06_运维手册.md` 的 **恢复顺序** 一节。

## 一之二、「聚合真的发生」这件事，证到哪一步了

**已经证到的**（每次部署第 8.55 步真跑一次，2026-08-13 最后一次的结果）：

```
从 B 站公开收藏夹「B站 × WAIC AI会客厅」真读到 5 条，
全部进了档案馆并按标题读回来了（不带登录态、他的库没动）
```

这一条为什么算数：打的是**真 B 站**（真网络，公开收藏夹）；取数用的是**插件里
那一份** `bilibili-reader.js`，不是另抄一遍；入库走 `/v1/captures/batch`，
和插件平时送条目**同一条路**；最后**从库里按标题读回来**。
跑在一次性容器的 tmpfs 上，**跑前跑后各数一次你的库，条数变了就红**。
全程零费用、不粘 Cookie、不用令牌。

**而用你自己的账号，这件事也已经真的发生过。**（2026-08-13 部署第 8.7／8.87 步
从生产库里量的，不是演练）

```
真的进过东西的平台   bilibili、douyin
现在档案馆里          去重后 186 条是自动同步搬进来的
最近一次成功的自动同步
  bilibili            2026-08-04T08:06:08Z
  douyin              2026-08-04T08:06:50Z
  xiaohongshu         2026-08-06T10:28:10Z（进 0 条）

你库里 194 条收藏，187 条能追到带它进来的那一次跑，
7 条压根没记跑，0 条指向已经消失的跑。
```

> **两个口径别搞混**：186 是**去重后真在库里**的条数；另有一个数 260，
> 那是各次同步自报的导入数**相加**，同一条重复导入会重复计数——它回答的是
> 搬过几次，不是搬进来几件。
> **而且 186 本身可能不全**：导入它们的那 4 次同步**4 次都没跑完**。

服务器上的 `core-worker` 自己跑的，不经过任何人的电脑。
**为什么现在不再有新东西进来**：三个账号 8/04 之后陆续断开，现在全是
`disconnected`、自动同步都是关的。**断开不删东西**——已存的一条不少。

**还没证到的那一层，是在今天这版代码上再跑成一次。**
抖音那条取数路 2026-08-06 换过，换过之后还没有真跑过一次
（抖音那 85 条缺作者也因此只能靠重新同步来补）。
这一层只能由你按那一下来完成（见第四节）：它要**真实的用户手势**，
而国内平台的登录态按设计不出你的浏览器——**这一层我拿不到，也不该拿**。

## 二、没有人照看也会继续跑的部分（当天逐条验过）

- 三个容器 `restart: unless-stopped`，且 `docker` 开机自启 → **重启后自己回来**
- **四个** systemd 定时器 `enabled`（备份、对象复制、状态投影、私有库同步）→ **重启后自己回来**
  > 这一行原来写的是「三个」，漏掉的正是**备份**——而 8/12～13 死掉的就是它。
  > 并且 `enabled` 只说明定时器装着，**不说明它叫起来的活儿干成了**：
  > 那两天它一直是 `enabled`/`active`，服务却每次都失败。要看干成没有，
  > 用上面第三节那两个办法（`/health` 的 `backup.stale`，或宿主机上的
  > `check_durability_units.sh` 第四列）。
- 自动同步跑在服务器的 `core-worker` 里，**不经过任何人的电脑**
- 磁盘还很宽裕（**当前值现读**：`curl -s …/health` 的 `disk.used_percent` / `disk.free_gb`；
  大头是 docker 镜像，归档数据本身很小）
  > 这里原来写死「31% / 67G」。六次部署之后就变成 35% / 62.25G——
  > **手抄的易变数字必然漂**，所以改成指给你去哪儿现读。

**也就是说：不改代码的话，这套东西不需要任何人（也不需要任何 agent）。**

## 三、怎么一眼看出它还好着

打开资料库那一页就够了。**坏了它会自己说话**，不用去翻日志：

**一类：跑过，这次没跑成**（等一等可能自己追上）

- 后台没在跑 → 顶部徽章变成「后台没在跑 · 新的同步会排队等着」
- **没做出新备份** → 徽章说「已经 N 小时没有做出新的备份了——之前存下的内容
  一条都没少，但这段时间里新进来的东西还没有进过备份。」
- **备份做出来了、没复制到别处** → 徽章说「备份已经 N 小时没有跑过了——
  已存下的内容一条都没少，停下来的是『再存一份到别处』这件事。」

**另一类：一次都没跑成过**（**不会自己追上**，要去看是哪个定时器没起来）

- **一次都没备份过** → 徽章说「还没有做出过任何一次备份。」
- **一次都没复制到别处过** → 徽章说「还没有把任何一份内容复制到别处——
  你存下的东西都在，但目前它们只存在这一台机器上。」
- **复制的状态记录坏了** → 徽章说「复制这一步的状态记录坏掉了——
  你存下的东西都在，但现在没办法确认它们到底有没有第二份。」

后一类在**新装一台机器**、或那个状态文件被删掉时出现。处置是同一条命令
（在生产机上）：`cd /opt/social-archive && bash scripts/check_durability_units.sh`

> **这两类分开写，是因为混在一起会让人等错东西。** 两条链会单独死：
> v0.0.0.71 加了备份那条的信号，**而那一版界面只读复制那条**——建好了没接上；
> v0.0.0.72 接上了，并立了「`/health` 回的每一格都得有人读」这道判据。
> **v0.0.0.79 才发现同一个病还压着「一次都没跑成过」那一支**：
> 备份那条会说话，复制那条连 `message_zh` 这个键都不下发，徽章全哑。
> 根因是「文件不在」（知道）和「读不动」（不知道）被写进了同一个 `except`，
> 而「不知道」按设计不说话。

要自己确认，打一条命令：

```bash
curl -s https://social-archive-api.linzezhang.com/health
```

看四样：`version`、`worker.alive`、**`backup.stale`**、`replication.stale`
（后两个都要是 `false`）。

> **为什么备份要占两格。** 它是两条会**单独死**的链：`backup` 做出加密快照，
> `replication` 把快照复制到别处。两次事故各死了一条：
>
> - **2026-08-11**，复制服务连着失败 **108 次、28 小时**；
> - **2026-08-12～13**，备份服务连着两天没做出快照（生产上 8/11 之后隔了两天
>   才有下一份）。
>
> 两次同一个根因：有人把 `/opt/social-archive` 改回 700，而这两个服务都以
> `socialarchive` 用户跑、共用这个工作目录，连进都进不去。
>
> **而两次的绿灯都还是绿的**：`/v1/status` 的 `replicas` 一直是 `verified`——
> 那是库里记着的**历史回执**，不是"现在还在跑"。第二次更难看：当时只接了
> `replication` 一格，它活着，就把死掉的 `backup` 整个挡住了。
>
> 现在两格分开报，各自读**真产物**：`replication` 读复制脚本每次跑完重写的那个
> 文件的时间戳；`backup` 读最近一份带 `manifest.json` 的快照目录名。
> **回执是历史，产物才是活性。**

> **宿主机上还能再核一层**（要 ssh 上去）：
>
> ```bash
> bash /opt/social-archive/scripts/check_durability_units.sh
> ```
>
> 它现在有第四列「上次跑的结果」。**只看前两列会被骗**：`enabled`/`active` 说的是
> 定时器本身还在不在，跟它叫起来的服务跑成没跑成毫无关系——上面那两次事故里，
> 这张表全程都是绿的。红了它会直接告诉你是哪个服务、下一步敲哪三条命令。
>
> **第四列有三种值，`?` 那种最容易被当成没问题：**
>
> | 印出来的 | 意思 |
> |---|---|
> | `✓ 上次成功 <时刻>` | 定时器叫起来的那次真的跑成了 |
> | `✗ 上次失败 …` | 跑了没成，下面会告诉你查哪个服务 |
> | `? 上次成功的是**手工**那次 …` | **成功的那次是人手动跑的；定时那次成没成，这几个字段答不了** |
>
> 最后那种是 2026-08-14 加的，起因是它真的骗过一次：8/13 定时那次 03:33
> 以 `200/CHDIR` 失败，我 08:51 手工补跑成功，而 systemd 只保留「最近一次运行」的
> 结果、**不分是谁叫起来的**——于是表上印 `✓ 上次成功 08:51`，把失败的那次
> 自动运行整个盖住。**手工能跑通，和没人管也会跑，是两件事**——后者才是这套东西的意义。
> 看见 `?` 就照它给出的 `journalctl` 命令去看定时那一刻；
> 下一次自动触发跑完之后，它会自己变回 `✓`。

## 四、只有你能做的那一件

**重新连接那三个账号**（现在 bilibili / douyin / xiaohongshu **全部是 disconnected**）。

资料库 → 每一行点**「连接账号」** → Chrome 弹的授权框选**「允许」**。

只能你做，因为最后那一下要**真实的用户手势**（`chrome.permissions.request` 的硬限制），
无头浏览器点不了；而国内平台的 Cookie 按设计不出你的浏览器。

**断开不删东西**——已经存下的 193 条一条不少，只是不再自动跑。

## 五、坏了怎么办

`docs/06_运维手册.md`。回滚、体检、备份、恢复都在那儿，命令都从
`deploy/PRODUCTION_HOST` 取机器名（2026-08-13 修的：那一节原来写死了一台
**已经连不上**的机器，半夜照着敲会挂在超时上）。

## 六、两条绝对不要碰的

1. **不要用 `InfrequentAccess` 存储类**（建桶／写对象／生命周期转换都不行）。
   R2 免费额度只覆盖 Standard；实账单量过：**51 次 IA 操作 = $9.00**，
   同周期 301 万次 Standard = $0.00。
2. **不要 `git prune` / `git gc --prune=now`**。不可达对象一删没有后悔药；
   这个仓的一个工作树半路整棵消失过，提交全活正是因为没人 prune 过。

---

> **下面是 v0.0.0.6（2026-08-03）的历史记录**，留着是因为里面有 SA-205 那条线、
> 当时的 Canary 约束和那个 ZIP 的哈希，删了就查不到了。
> **别照着它判断今天的状态。** 更早的一份 build-agent 视角交接在
> [`evidence/HANDOFF_v0007.md`](evidence/HANDOFF_v0007.md)（v0.0.0.7 / 8-03，
> 面向任务包，同样不是今天的状态）。
## v0.0.0.6 production cutover and real provider receipts (2026-08-03 UTC, supersedes the SA-205 block narrative below)

**Production was never running v0.0.0.6, and it was never the developer Mac.** `evidence/SA-205/PRODUCTION_ORIGIN_READBACK.json` concluded the Cloudflare Tunnel origin was a local container from the `v0006-s0` worktree. That is retracted in `evidence/SA-205/PRODUCTION_ORIGIN_CORRECTION_20260803.json`: the public API and the Mac loopback reported different versions at the same instant, no cloudflared existed on the Mac at all, and deploying only the OVH host flipped the public endpoint while the Mac container stayed untouched. The real origin is `vps-83b882b4`, Compose project `/opt/social-archive`. Every prior "invalid production target" observation came from inspecting the wrong host.

The current candidate is now deployed there: `social-archive/core:0.0.0.6`, public API reports `0.0.0.6`, the PWA serves `assets/app.js?v=006-r1` with cache identity `social-archive-ui-v006-r1`, and all three containers are healthy. Rollback artifacts are `/opt/social-archive-rollback/opt-social-archive-source-20260803T055259Z.tar.gz`, the dated `.env` backups beside it, and the retained `:0.0.0.5` images.

**Five real defects were found by running the taskpack's own per-task gates, which prior runs had never done end to end.**

1. **Pairing rotation could never reach a running Core.** Compose publishes each secret as a single-file bind mount, so the container follows the inode; `generate_pairing_code.py` rotated by temp-file plus `os.replace`, which allocates a new one. Core kept serving the pre-rotation record forever, which is why production sat at `one_time_code_available=false, attempts_remaining=0` and no extension could pair. Earlier runs recorded this as an unexplained environment block. Now rotates in place under `flock`, with the reader taking a shared lock. Verified live: minting now flips the public status to available with no restart.
2. **Locale-fragile shell quoting.** `start_readers.sh` and `prepare_systemd_host.sh` interpolated bare `$secret`, `$HOST_DATA_ROOT` and `$key` immediately before full-width punctuation. Under a C/POSIX locale — what systemd units and `docker exec` normally get — bash folds the leading continuation byte into the identifier and `set -u` aborts. All four are braced, with a repo-wide regression.
3. **`doctor.sh --self-test` crashed on the production host** with a `UnicodeDecodeError` naming no file, because a macOS-side copy had left nine AppleDouble sidecars in the tree and two sat beside `api.py` and `db.py`. Removed, and the self-test now names them instead of dying.
4. **The GitHub archive repository pointed at `Private-Database`**, which would have collapsed the object-bytes plane into the structured-facts plane. Repointed, and the dedicated vault recreated — it did not exist, despite an earlier run recording its creation.
5. **Two request models silently accepted unknown fields.** `ExportRequest` returned 202 having exported nothing when a caller wrote `destinations` instead of `destination_ids`, with `skipped_destination_ids` empty too. Both it and `PairingRequest` now forbid extras.

**Real provider receipts now exist.** With the Owner's explicit instruction to lift the standing "no user data uploaded" hold, all 17 pending artifacts — the canary plus a real Bilibili video and a real Xiaohongshu post with their media — replicated to R2 and OCI, 17/17 PASS each. GitHub private Markdown, local Markdown, the Obsidian vault and JSONL all carry the same projection SHA-256, confirmed by independently re-fetching the GitHub copy and hashing it locally. The Private-Database fact synced no-clone and the re-run returned `NO_CHANGE`. Cold backup produced two verified remote copies, both independently restorable to the same plaintext, and object-level recovery passes for real from R2 and OCI. Obsidian never needed a token: the destination prefers a filesystem vault, and the earlier check read `SOCIAL_ARCHIVE_OBSIDIAN_VAULT`, which the product does not read.

**Full application regression on this candidate: 310 passed**, with the single pre-existing non-failing Starlette deprecation warning.

**Four gates remain, and each needs a person; none can be worked around without breaking a boundary.**

- **SA-205** needs the official v0.0.0.6 extension installed in the Owner's logged-in Chrome. No browser is connected to the agent session, so the profile is unreachable. This also gates SA-303's live control state and the SA-305 gate.
- **SA-503** needs a fine-grained token whose only repository is `LinzeColin/Social-Archive-Vault`, with Contents read/write. The repo and config are ready. Fine-grained tokens select repositories by ID, so recreating the name cannot re-attach the orphaned token and no API can widen it. Deliberately not worked around: using the broad local OAuth credential on the host, or retargeting the third copy at `Private-Database`, would each make the command pass while breaking a boundary. This also gates the three-target recovery half of SA-506, where `restore_object.py` correctly fails closed with `GITHUB_RECEIPT_REPOSITORY_MISMATCH`.
- **SA-402** needs a Notion Integration token and a shared `data_source_id`, which exist only behind Notion's own UI. `export_all.py` does emit `notion-import.csv` as a zero-credential manual route.
- **SA-304** needs host disk. The reader stacks want several GB and the 38 GB root sits at 95 percent with roughly 8.9 GB of images and 14 GB of containerd layers for about eight unrelated projects. A real `start_readers.sh karakeep` run exhausted the disk mid-pull; it was fully contained, but it should have been a dry run.

Nothing has been pushed to `origin`. No tag, no release, no timer enabled.

## v0.0.0.6 current execution (2026-08-03 UTC)

- **交接增量：PWA 桥接自动恢复（SA-205，未构成 Canary PASS）**。扩展在 `install` 或 `update` 时，会只查询三个已声明的 Social Archive PWA URL（生产域、`127.0.0.1:8765`、`localhost:8765`），并仅向已完成加载的 PWA 标签页重新注入 `bridge.js`。它不刷新任何页面、不创建标签页、不查询或注入四个平台页、不读取登录态；桥接脚本会移除同版本旧监听器后重新广播 `SA_BRIDGE_READY`，使 v0.0.0.6 PWA 自动重新探测扩展。验证已通过：`node --check` 两个扩展脚本；桥接/包/扩展契约回归 **18 passed**；冻结 SA-205 Stage 2 命令 **17 passed**；`git diff --check` 通过。生产 PWA 仍是 v005-r1，且当前持久 Chrome Profile 仍未检测到扩展；该生产身份与配对服务缺少一次性记录的问题没有被此源代码修复掩盖。后续 agent 必须从 GitHub `main` 继续：先保持同一持久已登录 Chrome Profile，不要求平台重新登录；等待 v0.0.0.6 依 DAG 到达部署阶段并让扩展通过正常受控安装路径可用后，再运行真实四平台 Owner Canary。SA-301 仍禁止启动。

- SA-205 remains an active real-Canary task, not a locally completed provider receipt. Current source commit `ceb02782b9d9a8582ba57a2484282d4d0f9475ff` repairs the extension's concrete persistent-profile defect: connect and verify now prefer the Owner's existing domestic-platform tab, inject into that tab, and never create a second login page when no reusable tab exists. The related 47-test regression and frozen 17-test SA-205 command pass; the rebuilt v0.0.0.6 ZIP is SHA-256 `164546b24d42ff23a8994d9b559eee821735f05159aa0d62a14c3f2b6fb4eff6`. Read-only production inspection confirms it still serves `assets/app.js?v=005-r1`, not the current v0.0.0.6 PWA contract. Four domestic target tabs remain in the persistent external Chrome profile; no platform re-login, Cookie/storage inspection, provider request, pairing code, install/reload, sync, deployment, or production mutation occurred.

- SA-205 production-pairing diagnosis: source commit `5e7e4fc9a638d56b5fe5afc48b037e60d3a87024` adds a non-sensitive pairing-supply status path to the PWA and extension settings. If the service requires pairing but exposes no usable one-time record, the UI stops pairing attempts and explicitly leaves all platform login sessions untouched instead of steering the Owner toward re-login. The earlier no-credential static-asset hash/token claim was retracted because Cloudflare Access intercepted that request before product HTML. Revalidated through the existing authenticated persistent Chrome Profile, the production PWA loads `assets/app.js?v=005-r1`; its bridge source includes `SA_PING`/`SA_CONFIGURE` and is source-envelope compatible with v0.0.0.6, but the visible page state is “尚未检测到插件”。The API reports `pairing_required=true`, `service_ready=true`, `one_time_code_available=false`, and `attempts_remaining=0`. Therefore the precise failure is a non-detected extension in the persistent Profile plus no server-side pairing supply—not a platform re-login failure and not a v005/v006 bridge mismatch. Pairing/bridge regression passed 26/26, frozen SA-205 passed 17/17, and the rebuilt 20-member v0.0.0.6 ZIP is SHA-256 `4628f9a8c0797534d3d10712266c70464fe35ba04e457193ed3fc654f73a8bba`. Do not begin SA-301 or claim the real canary PASS.

- SA-000 is **PASS** at verified head `2d9f624420df34114dd173220a2af414c10ab00e` / integration base `7925695c0078bb3b98d71636f5a1315270d9de87`. A fresh safe extraction from the sealed `Social_Archive_v0.0.0.6_FINAL_TASKPACK_20260802.zip` passed 27 checks in ZIP mode (including zip safety) and a second independent fresh extraction passed the task-graph `START_HERE.py verify` entry with 26 checks; both verified **395/395** manifest entries and ran **97/97** candidate tests (one upstream Starlette deprecation warning). The default macOS `/usr/bin/python3` is 3.9.6 and cannot import `tomllib`; it and a previously cache-contaminated historical `/tmp` extraction were explicitly rejected, while the accepted checks used an existing Python 3.12.13 environment with PyYAML/pytest. No package or interpreter was installed or changed. This proves Task Pack integrity only; product/runtime remains `NOT_RUN`. Evidence is at `evidence/SA-000/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 evidence is retained verbatim at `evidence/SA-000/history/pre-v0.0.0.6-taskpack-integrity/`.
- SA-001 is **PASS** on latest `origin/main` / integration base `19f600472b2be7998ff27c5669b4ba5d36b1fa24`. Its original semantic decision was `REUSE_CORE_REBUILD_PRODUCT_SHELL_AND_CONNECTORS`, with no conflict, blocked, or obsolete classification.
- SA-002 is **PASS** after the Owner explicitly confirmed that the target version is `v0.0.0.6`, not `v0.0.0.5`. The sealed identity phase created recovery tag `social-archive-pre-v0.0.0.6-20260802t212629z` and ignored snapshot `20260802T212629Z`; the 29 tracked active identity declarations changed only the version token. `VERSION`, package, browser-extension and Obsidian identity anchors now read `0.0.0.6`.
- Both sealed legacy-retirement commands returned `ALREADY_RETIRED`: the recorded legacy directory is absent, so no deletion occurred. The exact rollback command and report hashes are in `evidence/SA-002/{RESULT,COMMAND_LOG}.json`; the prior BLOCKED evidence is preserved by `evidence/SA-002/history/pre-owner-v006-version-correction/BLOCKED_PREDECESSOR.json`.
- SA-002 validation: identity-specific focused tests **29 passed** (one dependency deprecation warning), `scripts/check_brand.py` found no prohibited current identity hit, `uv lock --check --offline` passed, and the post-migration classifier has `social_archive_identity=satisfied`, `SA-002=equivalent`, `conflict=0`, `blocked=0`.
- SA-003 is **PASS**. The required sealed `--phase all` command created recovery tag `social-archive-pre-v0.0.0.6-20260802t213736z` and snapshot `20260802T213736Z`: 24 approved replacements and 12 missing files were written, while 93 divergent upstream files were retained in the ignored `.social-archive-candidate-v0.0.0.6/` candidate area. `src/social_archive/db.py` and `service.py` remain byte-identical to the recovery base; the three mandated focused tests passed **5/5**.
- SA-003 additional local safeguards passed: lockfile, account-sync compile, secret/brand scans, 10 changed/additional extension/PWA JavaScript syntax checks, extension ZIP integrity, and `git diff --check`. The only manual normalization removed two trailing spaces from the packaged PWA CSS. The post-apply classifier is `ADAPT_CURRENT_UPSTREAM`, `preserved_transaction_core=satisfied`, `SA-003=equivalent`, `conflict=0`, `blocked=0`. Evidence is at `evidence/SA-003/{RESULT,COMMAND_LOG}.json`; prior active evidence is recoverable through `evidence/SA-003/history/pre-v0.0.0.6-overlay-apply/PREVIOUS_EVIDENCE.json`.
- SA-004 is **PASS** at implementation commit `28e5451bc602443adfa7fbc30cb332f50c56c3ca`. It adaptively attaches the account-mirror coordinator to the preserved RuntimeStore/API/worker core, adds resumable queue/checkpoint/relation-final state, preserves two-complete-absence closure, and routes Chrome bookmark chunks through the extension persistent queue. A legacy `source_account` fixture is now migrated before new account-mirror indexes are created. The frozen v0.0.0.6 `test_extension_e2n_contract.py` replaced the stale v0.0.0.5 contract byte-for-byte; required focused tests passed **13/13**, related core/API/control regressions **14/14**, JS syntax, compile, lockfile, brand and secret scans all passed. Evidence is at `evidence/SA-004/{RESULT,COMMAND_LOG}.json`; the previous active v0.0.0.5 evidence is retained verbatim at `evidence/SA-004/history/pre-v0.0.0.6-sa004-account-mirror/`.
- SA-005 is **PASS** at implementation head `09db0c8c0f9396dfe99e70d62f581f097d6bea93` (the account/table change is `6b8910d0ddbb4880e49c8646e7c4aca758c3ed16`). The frozen v0.0.0.6 Stage 0 account-mirror contract is restored byte-for-byte; account captures now retain relation time, topic, keywords and language, while legacy runtime databases add those columns before the new indexes are created. The API now projects the PWA table’s columns, facets, filters and server sorting, and the stale v0.0.0.4 platform-capability manifest is replaced byte-for-byte with the sealed v0.0.0.6 eight-platform account-mirror contract. The required `doctor --self-test` also now passes completely after aligning static units with the existing moving-main loopback/status-web, `/var/lib` data-plane and per-unit credential-file contracts; it did not start or deploy anything. Frozen command tests passed **4/4**; related migration/recovery/account/API tests passed **31/31** (one dependency deprecation warning) and affected static deployment regressions passed **14/14**. Evidence is at `evidence/SA-005/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 active evidence is retained verbatim at `evidence/SA-005/history/pre-v0.0.0.6-stage0-gate/`.
- SA-101 is **PASS** at implementation commit `21a61a9acd0f87484f91770c5289dbbd77bb61a6`. It retains the current Markdown/Social Archiver ZIP parsing, path-traversal rejection, L0/L1/L3 defaults and idempotent content identity, while filling the missing zero-tech PWA ZIP-import surface. The PWA now validates a local nonempty `.zip` up to 200 MiB, sends it as raw `application/zip` to the protected importer with a safe filename, and refreshes the table after a successful import. The sealed generic-web assertions remain semantically unchanged; the current test retains them and adds an L0/L1/L3 end-to-end check. The task-pack command passed **7/7**; related Stage 1 import/account-batch/extension tests passed **16/16** (one upstream TestClient deprecation warning); JavaScript syntax, brand/secret scans and offline lock check passed. No browser, extension reload/pairing, real account, provider, deployment or production action was attempted. Evidence is at `evidence/SA-101/{RESULT,COMMAND_LOG}.json`; prior v0.0.0.5 active evidence is retained verbatim at `evidence/SA-101/history/pre-v0.0.0.6-stage1-import-gate/`.
- SA-102 is **PASS** at implementation commit `fdb21051135cd22219bad92d23a1be81a3568d74`. The sealed v0.0.0.6 OAuth surface was byte-equivalent at entry, but the Task Pack oracle exposed a cross-layer gap: persisted Reddit `next_cursor` was never read and a final page could evaluate only itself for relation closure. The adaptive slice carries a safe internal cursor through the registry, reads/writes the checkpoint, accumulates all pages before a fresh full-scan closure, and prevents a resumed prior-run checkpoint from being mislabeled as a current full snapshot. HTTP 429 produces `REDDIT_RATE_LIMITED`, `Retry-After`, a retryable `unknown` receipt, and no closure; missing OAuth produces `blocked_environment`; public connector-run requests cannot inject a cursor. The task command passed **13/13**; related account-sync/bridge/control/Stage 1 regressions passed **20/20**; compile, semantic classifier, brand/secret scans, offline lock and diff checks passed. The unrelated `test_v006_account_mirror_contract.py` has a hard-coded missing Task Pack parent path (22 passed, 2 path-resolution failures) and was intentionally not changed in this SA-102-only run. No real Reddit OAuth, account, browser/extension reload or pairing, platform request, deployment, or production action was attempted. Evidence is at `evidence/SA-102/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 active evidence is retained verbatim at `evidence/SA-102/history/pre-v0.0.0.6-reddit-account-mirror/`.
- SA-103 is **PASS** at implementation commit `60ce0b0112cbea62b92cfba9017be9da0cec2fcd`, then validated after the no-conflict latest-main merge at `f3e9a931366da05d104caa1fad83451e7fa62af9` (`origin/main=7925695c0078bb3b98d71636f5a1315270d9de87`). The sealed zero-cost API gate remains fail-closed until explicit confirmation, but the Task Pack oracle exposed a cross-layer gap: X emitted `next_token` without accepting the corresponding `pagination_token`, so account sync could not paginate its own Bookmarks/Likes mirror. The adaptive slice transports the internal checkpoint through the registry, preserves `next_token` checkpoints, emits `X_RATE_LIMITED` / `Retry-After` as a retryable `unknown` receipt, and makes shared fresh-scan/cursor-loop diagnostics provider-specific. Bookmarks and Likes remain independent; continuation from a prior run cannot pretend to be a current full snapshot or close prior relations. The task command passed **11/11**; related OAuth/account-sync/extension/control/Stage 1 regressions passed **29/29**; compile, semantic classifier, brand/secret scans, offline lock, latest-main ancestry and diff checks passed. No real X entitlement, OAuth/account, browser/extension reload or pairing, official export, platform request, deployment, or production action was attempted. Evidence is at `evidence/SA-103/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 active evidence is retained verbatim at `evidence/SA-103/history/pre-v0.0.0.6-x-account-mirror/`.
- SA-104 is **PASS** at implementation commit `3187252b9d62dfadf6de0b2e5cf56a5a57d3f358`; `origin/main=7925695c0078bb3b98d71636f5a1315270d9de87` remained unchanged and is an ancestor of that validated head. The sealed Instagram boundary remains isolated: the core has no `instagram_session` mount, remote payloads do not carry a session, and only restricted relative Sidecar artifacts are accepted. The exact v0.0.0.6 command initially exposed four **Bilibili Sidecar** static-contract failures (while all Instagram isolation assertions already passed): the adaptive Sidecar-only repair fixes documented read-only JSON argv, metadata-only success receipts, HTTP 412/429 `BILI_RATE_LIMITED` degradation, and fresh HOME/XDG boundaries, and aligns the existing named vendor build context. The task command then passed **16/16**; related account-mirror/connector/Stage 1 regressions passed **34/34**; compile, semantic classifier, brand/secret scans, offline lock, latest-main ancestry and diff checks passed. The vendor directory was absent and neither `vendor_sync` nor Docker build ran. No Instagram session, owner account, browser/extension reload or pairing, official export, platform request, deployment, or production action was attempted; real runtime remains **NOT_RUN**. Evidence is at `evidence/SA-104/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 active evidence is retained verbatim at `evidence/SA-104/history/pre-v0.0.0.6-instagram-account-mirror/`.
- SA-105 is **PASS** at implementation commit `8b5b4afa46a07d69e7b392611d33fe93176b67fe`; `origin/main=7925695c0078bb3b98d71636f5a1315270d9de87` remains an ancestor. The frozen gate command passed **7/7**, and related Stage 1/browser/connector/account-sync regressions passed **65/65** (one upstream Starlette deprecation warning). The current S1 fixture suite is stronger than the sealed file-existence check and covers default levels, import idempotency, Reddit/X relation normalization, and Instagram’s isolated Sidecar boundary. The declared `--read-only` platform-canary flag previously still reached live-capable code and wrote receipts; it now fail-closes before Settings, credential reads, network, or runtime writes. Generic-web, Reddit, X, and Instagram each returned `BLOCKED_ENVIRONMENT / OWNER_CANARY_NOT_AUTHORIZED` with all three safety booleans false. This is an honest owner-authorization boundary, not platform success: real accounts, permissions, scopes, totals, collections, incremental arrival, browser/extension pairing, deployment, and production remain **NOT_RUN**. Evidence is at `evidence/SA-105/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 evidence is retained verbatim at `evidence/SA-105/history/pre-v0.0.0.6-stage1-gate/`.
- SA-201 is **PASS** at implementation commit `b79cf1b1914b2df736d5f0d1a991d85e86498f55`; `origin/main=7925695c0078bb3b98d71636f5a1315270d9de87` remains an ancestor. The frozen v0.0.0.6 task target passed **13/13**, and related account-mirror/extension/Stage 2 structure regressions passed **10/10**. The XHS worker Compose profile is byte-identical to the frozen Candidate and passed config-only validation without `.env`, image build, or service start. The browser account-mirror path already preserved chunk accumulation and relation-final closure, but favorite and like share a profile URL: the adaptive slice now confirms the selected relation tab before labeling. Missing or unconfirmed tabs return `partial / RELATION_SCOPE_UNCONFIRMED` without importing or closing relations; collection-scope discovery is covered separately. The only XHS canary used `--read-only` and returned `BLOCKED_ENVIRONMENT / OWNER_CANARY_NOT_AUTHORIZED` with credential/network/runtime-write all false. No real XHS account, Extension reload/pairing, provider request, Sidecar vendor resolution, Docker runtime, deployment, or production action was attempted; real runtime remains **NOT_RUN**. Evidence is at `evidence/SA-201/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 evidence is retained verbatim at `evidence/SA-201/history/pre-v0.0.0.6-xhs-account-mirror/`.
- SA-202 is **PASS** at implementation commit `68e1685e160934d3caf25c7f3bc89833960f853f`; `origin/main=7925695c0078bb3b98d71636f5a1315270d9de87` remained unchanged and is an ancestor. The frozen v0.0.0.6 task target passed **14/14**, and related connector/account-mirror/Extension/Stage 2 regressions passed **21/21**. The DouK experimental Compose Candidate is byte-identical to the frozen file and passed config-only validation without `.env`, image build, or service start. The browser primary path already had independent worker degradation/fallback safeguards, but did not recognize the normal Douyin `/note/` content route: the adaptive slice now preserves both `/video/` and `/note/` collection candidates with their stable IDs, relation and collection metadata. DouK was not resolved or built and remains a disabled `BLOCKED_CANDIDATE`; this does not affect the browser path. The only Douyin canary used `--read-only` and returned `BLOCKED_ENVIRONMENT / OWNER_CANARY_NOT_AUTHORIZED` with credential/network/runtime-write all false. No real Douyin account, Extension reload/pairing, provider request, Cookie/session read, vendor resolution, Docker runtime, deployment, or production action was attempted; real runtime remains **NOT_RUN**. Evidence is at `evidence/SA-202/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 evidence is retained verbatim at `evidence/SA-202/history/pre-v0.0.0.6-douyin-account-mirror/`.
- SA-203 is **PASS** at implementation commit `45effacb53b5069f04a3e72b94baf99408384d0f`; `origin/main=7925695c0078bb3b98d71636f5a1315270d9de87` remained unchanged and is an ancestor. The frozen v0.0.0.6 task target passed **6/6**, and related connector/account-mirror/Extension/Stage 2 regressions passed **21/21**. The KS-Downloader Compose Candidate and platform-capability contract are byte-identical to the frozen files; config-only Compose validation passed without `.env`, image build, or service start. The browser primary path already had independent Worker degradation/fallback safeguards, but favorite and like share a profile URL and it did not recognize Kuaishou `/photo/` content: the adaptive slice now requires an observable selected relationship tab before labeling a shared-profile page and preserves both `/short-video/` and `/photo/` candidates with stable IDs. KS-Downloader was not resolved or built and remains a disabled `BLOCKED_CANDIDATE`; this does not affect the browser path. The only Kuaishou canary used `--read-only` and returned `BLOCKED_ENVIRONMENT / OWNER_CANARY_NOT_AUTHORIZED` with credential/network/runtime-write all false. No real Kuaishou account, Extension reload/pairing, provider request, Cookie/session read, vendor resolution, Docker runtime, deployment, or production action was attempted; real runtime remains **NOT_RUN**. Evidence is at `evidence/SA-203/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 evidence is retained verbatim at `evidence/SA-203/history/pre-v0.0.0.6-kuaishou-account-mirror/`.
- SA-204 is **PASS** at implementation commit `8184cbfc911eae1cf7f6960b674914f15c50ddea`; `origin/main=7925695c0078bb3b98d71636f5a1315270d9de87` remained unchanged and is an ancestor. The frozen v0.0.0.6 task target passed **18/18**, and related connector/account-mirror/Extension/Stage 2 regressions passed **21/21**. Current Compose/Dockerfile keep the stronger host data-plane and named-vendor boundaries; config-only validation passed without `.env`, image build, or service start. The Bilibili Sidecar keeps only read-only JSON favorites/watch-later/history allowlisted commands. The adaptive slice fails closed on empty, non-JSON, or `ok:false` responses rather than importing raw text; 412/429 remain structured degraded and yt-dlp/current-page fallback stays independent. Bilibili likes import only after an observable selected tab; an unconfirmed shared user-space route returns partial. The candidate vendor remains absent/disabled `BLOCKED_CANDIDATE`; the safe Canary returned `BLOCKED_ENVIRONMENT / OWNER_CANARY_NOT_AUTHORIZED` with credential/network/runtime-write all false. No real Bilibili account, Extension reload/pairing, provider request, Cookie/session read, vendor resolution, Docker runtime, deployment, or production action was attempted; real runtime remains **NOT_RUN**. Evidence is at `evidence/SA-204/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 evidence is retained verbatim at `evidence/SA-204/history/pre-v0.0.0.6-bilibili-account-mirror/`.
- SA-205 is **BLOCKED_ENVIRONMENT** (not PASS) at implementation commit `44dbbcf418ae656ccfd7fc9545a3bc2bd7a49f64`; `origin/main=7925695c0078bb3b98d71636f5a1315270d9de87` remained unchanged and is an ancestor. The frozen v0.0.0.6 task target passed **17/17**, and related Stage 2/account-mirror/Extension/connector/worker/fallback/status/Canary regressions passed **75/75**. The minimal adaptive slice makes Core reject any late batch while a run is paused, so it cannot mutate journal counters, checkpoints, receipts, or relation closures; resume returns it to queued and the next batch succeeds. Fixture coverage now exercises XHS, Douyin, Kuaishou, and Bilibili connection, first-full, incremental, partial protection, pause/resume, and platform-scoped closure. Current Chrome read-only tab inventory contained only ChatGPT, not Social Archive or a logged-in low-risk domestic page; no real Owner Canary could be started. The four-platform `--read-only` command returned `BLOCKED_ENVIRONMENT / OWNER_CANARY_NOT_AUTHORIZED` with credential/network/runtime-write all false. The sealed Oracle forbids PASS until real accounts run, so do not advance to SA-301. No real account, Extension reload/pairing, provider request, Cookie/session read, vendor resolution, Docker runtime, deployment, cloud, or production action was attempted; product runtime remains **NOT_RUN**. Evidence is at `evidence/SA-205/{RESULT,COMMAND_LOG}.json`; v0.0.0.5 evidence is retained verbatim at `evidence/SA-205/history/pre-v0.0.0.6-stage2-gate/`.
- 2026-08-03 live pairing diagnosis (not a Task Pack completion): the authenticated website and its installation page both rendered `v0.0.0.5` after a cache-busting navigation, while the page reported no extension bridge. The current v0.0.0.6 source carries a `0.0.0.6` Manifest/runtime config and its PWA previously retained a `v005` Service Worker cache key, so a real v0.0.0.6 Canary against that host would be identity-invalid. Commit `de17c86e0a86e75e8a36792bd8c51d7d1e8acec7` adds active `SA_PING` bridge detection, rejects unpaired or version-mismatched extensions through the safe install/options route, and uses `v006-r1` cache/asset identities with `skipWaiting` and `clients.claim`. The frozen SA-205 command remained **17/17 PASS**; focused PWA/bridge/API checks were **12/12 PASS** (one existing dependency deprecation warning). No pairing code, token, platform request, deployment, or production change was performed.
- 2026-08-03 isolated loopback pairing acceptance (supplementary, not the real Owner Canary): Playwright Chromium 149.0.7827.55 loaded the actual unpacked v0.0.0.6 extension into a disposable profile and served only a local `127.0.0.1:8765` pairing-status fixture. `SA_CONFIGURE` and `SA_PING` returned `detected=true`, `paired=true`, and `version=0.0.0.6`; then the actual PWA loaded its `v=006-r1` app asset, received the same `SA_PONG`, and showed `私人档案馆已连接 · v0.0.0.6`. The temporary profile and local server were removed at completion. Evidence: `evidence/SA-205/LOOPBACK_PAIRING_SMOKE.json`.
- 2026-08-03 isolated pairing-exchange acceptance (supplementary, not the real Owner Canary): a fresh disposable Chrome profile loaded the actual unpacked v0.0.0.6 extension. Its real Options page first showed the pairing UI, exchanged a synthetic one-time code against only the manifest-approved `127.0.0.1:8765` fixture, persisted the returned synthetic device configuration, and then the actual PWA received `SA_PONG` with `detected=true`, `paired=true`, and `version=0.0.0.6`. The temporary profile, loopback server, code, and token were removed; no production API, account, or secret was used. Evidence: `evidence/SA-205/PAIRING_EXCHANGE_SMOKE.json`.
- 2026-08-03 current-image pairing runtime acceptance (supplementary, not the real Owner Canary): a fresh Docker image built from this v0.0.0.6 worktree ran an actual Core at the manifest-approved loopback origin with pairing required and temporary secrets owned `0600 10001:10001`, matching the active Core's secret-file boundary. The actual unpacked extension completed a synthetic code exchange; Core health, the PWA app asset, packaged extension manifest, and `SA_PONG` bridge response all reported `0.0.0.6`. The temporary Core container, secret volume, Chrome profile, code/token, and image tag were removed. No production API, account, provider, Tunnel, or secret was used. Evidence: `evidence/SA-205/CONTAINER_PAIRING_RUNTIME_SMOKE.json`.
- 2026-08-03 current-head Canary preflight (supplementary, not the real Owner Canary): current HEAD `c05f0d42` retained the frozen SA-205 regression result (**17 passed**). The in-app browser had no user tabs; the controlled Chrome surface exposed no authenticated Social Archive or domestic-platform page, and a new read-only navigation to the target connection page returned `ERR_BLOCKED_BY_CLIENT`. The newly created preflight tab was removed. No Cookie/storage inspection, provider request, account action, extension change, production action, or secret access occurred. Evidence: `evidence/SA-205/CURRENT_HEAD_CANARY_PREFLIGHT_20260803.json`.
- 2026-08-03 Access-boundary diagnosis (supplementary, not the real Owner Canary): both controlled browser surfaces returned `ERR_BLOCKED_BY_CLIENT` before the connection page, while an unauthenticated, no-cookie HTTP probe reached the protected origin and received only the Cloudflare Access login boundary (`302`). No response session/routing material was retained, no Access policy was changed, and no authentication was attempted. This establishes a client-side traversal constraint, not a source or pairing defect. Evidence: `evidence/SA-205/ACCESS_BOUNDARY_PREFLIGHT_20260803.json`.
- 2026-08-03 Owner Canary browser readiness (supplementary, not the real Owner Canary): the four domestic target pages were opened in the controlled Chrome surface, with only a page-level likely-authenticated signal observed and no browser session state inspected. The frozen SA-205 regression reran **17/17 PASS** at current source head. The Chrome Extensions manager has no visible `Social Archive` extension, and a safe `SA_PING` at an allowed loopback origin received no response; no extension was installed, enabled, reloaded, or configured. The freshly built official ZIP is `Social Archive` `0.0.0.6` with 20 members and a verified manifest, but is not installed. No pairing code/token, provider request, account connection/sync, deployment, or production action occurred. Evidence: `evidence/SA-205/OWNER_CANARY_BROWSER_READINESS_20260803.json`.
- 2026-08-03 sender-tab capture reconciliation (implementation, not the real Owner Canary): the v0.0.0.6 Overlay had overwritten a preserved upstream guard and made `SA_CAPTURE_ACTIVE` read whichever tab became active after the message was sent. Current source again prefers the message sender tab, passes the context-menu tab explicitly, and falls back to the active tab only when no source tab exists. The extension/API and frozen SA-205 focused set passed **33/33**; the official v0.0.0.6 ZIP was rebuilt from that code. No browser extension installation, pairing, account connection/sync, provider request, deployment, or production change occurred. Evidence: `evidence/SA-205/SENDER_TAB_CAPTURE_RECONCILIATION_20260803.json`.
- 2026-08-03 v0.0.0.6 contract portability reconciliation (test infrastructure, not the real Owner Canary): the focused contract test had hard-coded a Task Pack directory below `GithubProject/`, so isolated worktrees failed before they could inspect the sealed platform matrix or PWA table contract. It now checks the committed platform matrix against the exact sealed SHA-256 and requires all six mandatory labels in the actual PWA HTML. The complete account-mirror/extension/pairing/domestic focused set passed **58/58**. No product behavior, extension configuration, account, provider, deployment, or production state changed. Evidence: `evidence/SA-205/V006_CONTRACT_PORTABILITY_20260803.json`.
- 2026-08-03 formal SA-205 evidence refresh: `RESULT.json` and `COMMAND_LOG.json` now bind the sender-tab capture repair, portable v0.0.0.6 contract verification, current 58/58 focused result, rebuilt 20-member v0.0.0.6 extension ZIP, and latest-main ancestry. The formal task verdict remains `BLOCKED_ENVIRONMENT`, not PASS: the controlled Chrome profile has four domestic target pages but no installed `Social Archive` extension, and production remains an invalid mixed v0.0.0.5 target. No browser profile state, account connection, pairing, provider, deployment, or production state changed.
- 2026-08-03 controlled extension-load capability: neither the normal Chrome Extensions manager controls nor the official DevTools `Extensions.loadUnpacked` command are available through the controlled browser surface; both probes were read-only and left no browser change. This rules out an agent-side normal installation route in the available Chrome context. No bypass, profile inspection, pairing, account connection/sync, provider request, deployment, or production action occurred. Evidence: `evidence/SA-205/BROWSER_EXTENSION_LOAD_CAPABILITY_20260803.json`.
- 2026-08-03 production identity precondition (supplementary, not a Task Pack completion): the active, healthy Cloudflare Tunnel named `social-archive-v0004` still routes both `social-archive.linzezhang.com` and `social-archive-api.linzezhang.com` to the same loopback Core at `127.0.0.1:18765`. In the owner-authorized Chrome session, the visible `/connections` page rendered `v0.0.0.5`; its XHS, Douyin, and Kuaishou cards each reported their preferred Worker unavailable. The minimal XHS `在插件中授权` probe went only to the same `v0.0.0.5` installer page; it did not open a platform tab or initiate an account/sync action. A tunnel name alone is not a product-version assertion, but its readback together with the rendered page proves that the production Canary target has not yet reached the current v0.0.0.6 PWA/extension identity. No Cloudflare, Tunnel, browser-profile, account, provider, deployment, or secret change was made. Evidence: `evidence/SA-205/PRODUCTION_IDENTITY_PRECONDITION.json`.
- 2026-08-03 production-origin readback (supplementary, not a Task Pack completion): the tunnel origin is the running local `social-archive-core-api-1` container from the historical `v0006-s0` worktree. It is tagged `social-archive/core:0.0.0.5`, and its embedded PWA still registers `table-s0` assets/cache; the container's `VERSION` and extension ZIP manifest both say `0.0.0.6`. This mixed image exactly explains the visible v0.0.0.5 UI and missing current bridge even though the downloadable ZIP is newer. No container was rebuilt, restarted, or otherwise changed. Evidence: `evidence/SA-205/PRODUCTION_ORIGIN_READBACK.json`.
- 2026-08-03 extension-package freshness repair (implementation, not a deployment): `dist/` is intentionally untracked, yet the former Dockerfile copied its host ZIP. A clean checkout could therefore fail the image build or inherit an old package even when source had v0.0.0.6 pairing fixes. The Dockerfile now generates the ZIP from `apps/browser-extension` inside the image; `install.sh` also regenerates the host package immediately before Compose build. A no-service, no-secret Docker smoke build read back `package_version=0.0.0.6` and `has_bridge=true` from the image; the temporary local image was deleted afterwards. Targeted extension/PWA/package tests passed **14/14**. This prevents a stale package from being built in a future authorized deployment, but does not mutate production or establish the real SA-205 source-account Canary.
- Earlier v0.0.0.5 evidence, Changelog, and embedded task-pack compatibility contracts remain historical inputs, not authority for this sealed v0.0.0.6 execution. No user-profile extension reload, real pairing code/token, account connection, first sync, provider action, deployment, or production action was attempted.
- **Next task only: SA-205 real Owner Canary.** Do not begin SA-301. The four low-risk domestic target pages are now available, but the same controlled Chrome profile has no installed `Social Archive` extension and no valid current v0.0.0.6 production target. Resume the real Canary only after the official v0.0.0.6 extension is explicitly installed/enabled in that browser and a valid current target is available; never request or receive passwords, Cookies, or tokens. The local fixture gate, extension package, safe bridge ping, and `--read-only` safety result do not establish a provider account connection, browser/extension pairing, real source read, Docker runtime, or production success.

## Current goal

按冻结的 Social Archive v0.0.0.6 Task Pack 逐项完成 Stage 0–5：保留一个经聚焦验证的事务与恢复核心，重建 E2N 产品壳、真实来源连接器、目的地授权与回执、聚合浏览和三地密文存储。每次运行只完成一个 Task；全部任务完成前不推送。

## Final closure status (2026-08-01 UTC)

- Task Pack 与源码发布均已闭合：32/32 `RESULT` 均为 PASS；SA-507 的当前证据为
  `evidence/SA-507/RESULT.json` 及 Phase A–E。冻结功能候选 204 文件的清单 SHA-256
  为 `78126ef0abd193aa18fb0055564786d234a468deeb0ffb2370f4844509493c90`，其在合入
  当时最新 `origin/main` 前后保持一致；唯一适用于此候选的全量应用回归为 235 passed。
- 兼容层 synthetic 验证和 frozen `verify-fast`（26 checks、明确跳过应用测试）均
  PASS；最终结构验证为 PASS 且未重跑 pytest。真实三副本、Private-Database facts、
  三目标恢复及生产/边缘 smoke 分别以 Phase A–E 记录为 PASS。
- 已发布：annotated `v0.0.0.4` 的 peeled target 与 `origin/main` 初始 readback 均为
  `e1f76776668b630b1d9a60a07d07a9791e6c0cf8`；tag object 为
  `272cf897b3ed69858a38f5dfbb302f7af3bc0357`。`RELEASE_REPORT.json` 保存真实回执。
  后续只需清理本 run 的临时资源并保持现有生产/回滚边界，不再启动新的开发 Task。
- 不启用复制或 facts timer；不读取/提交秘密，不删除生产备份、ignored runtime 或受保护
  目录。已有 `social-archive-pre-v0.0.0.4-20260730t095749z` 是非破坏性回滚起点。

## Historical task-by-task state

- 已完成：SA-000、SA-001、SA-002、SA-003、SA-004、SA-005（Stage 0 Gate）、SA-101、SA-102、SA-103、SA-104、SA-105（Stage 1 Gate）、SA-201、SA-202、SA-203、SA-204、SA-205（Stage 2 Gate）、SA-301、SA-302、SA-303、SA-304、SA-305（Stage 3 Gate）、SA-401、SA-402、SA-403、SA-404（Stage 4 Gate）、SA-501、SA-502、SA-503、SA-504、SA-505、SA-506。
- 进度核对：任务图共 32 项，已有 31 项 PASS 证据，剩余 SA-507 一项；SA-000 与 SA-001 的 PASS 证据按兼容层合同保留在 `social-archive-taskpack-compat/v0.0.0.4/evidence/`，其余已完成产品任务证据位于 `social-archive/evidence/`。不得只扫描后者而误报为 29 项完成。
- SA-506（2026-07-31）：冻结 `AC-SA-506` 已 **PASS**。Stage 5 为 5/5；隔离、无业务数据的真实 age Fixture 对精确 `restore.py --latest --verify-only`、恢复、SQLite/FTS 重建和拒绝覆盖均通过；缺少 GitHub 第三收据会在重建前失败；兼容任务包的默认回滚只返回 `ROLLBACK_PLAN`，恢复标签解析且 ignored runtime 受保护。恢复/复制/Private-Database/Release 相关定向回归为 47/47，静态检查通过。真实 R2 与 OCI 均已用专用私有桶、最小 S3 凭据完成 age 加密写入、读回哈希校验和删除探针；不记录 ID 或凭据。GitHub Private Draft 和 Private-Database API 投递仍是 **NOT_RUN**：创建新的 repo-scoped fine-grained token 被 GitHub sudo/passkey 本人确认卡住，现有宽权限 CLI token 和受保护文档标记为已暴露的旧 PAT 均未使用。它们不是 SA-506 的 Fixture blocking assertion，也绝不能伪写为真实三副本业务数据。完整分层证据位于 `evidence/SA-506/`；下一次 Run 才能进入 SA-507。
- 当前产品身份：`social-archive/`、`social_archive`、`v0.0.0.4`。
- 当前唯一事务核心：`src/social_archive/`；SA-003 最终聚焦测试 6/6 通过（含品牌迁移边界）。
- 历史核心已在临时测试中证明 34/34 通过，但因旧包名与 RuntimeStore 合同不兼容而退出当前运行入口；恢复标签和只读快照保留其可恢复证据。
- 277 个与 SA-002 只读快照逐字一致的旧文档、证据和机器清单已从当前产品面退休；历史 Changelog、迁移文档/测试/验证器保留为受控边界。
- SA-003 证据：`evidence/SA-003/`；迁移会话与回滚计划位于被忽略的 `.social-archive-migration/`。
- SA-004：浏览器扩展、配对/API/config/script 与四个 focused tests 共 24 个文件与冻结 Overlay 逐字一致；17/17 聚焦测试和 API/FAB Oracle 通过。证据位于 `evidence/SA-004/`。
- SA-005：激活项目 `.venv` 后的冻结 Stage 0 命令 2/2 通过，覆盖通用网页 L0/L1/L3、检索、任务状态和 SQLite 重开恢复；`doctor.sh --self-test` 通过。阶段测试比冻结候选更强，未改变归档行为；证据位于 `evidence/SA-005/`。裸系统 `python3` 缺少 `pydantic`，是已记录的环境未配置，不是测试断言结果。
- SA-101：三个任务产品源文件与冻结 Overlay 逐字一致；13/13 聚焦测试通过。通用网页通过 Registry→Service 进入 L0/L1/L3；Social Archiver ZIP 重复导入不重复关系、工件或任务；Karakeep 投影可删除后重建且不会反向覆盖 Canonical facts，503 时主档案成功且 reader 为 degraded。证据位于 `evidence/SA-101/`。
- SA-102：`oauth.py` 与冻结 Overlay 逐字一致；4/4 聚焦测试通过。Reddit saved/upvoted 关系独立；带 cursor 的结果为 partial；API 对 partial receipt 不推进缺失计数或关闭关系；无凭证时 Reddit 被阻断而当前页兜底仍可用。证据位于 `evidence/SA-102/`。

- SA-103：`registry.py` 与冻结 Overlay 逐字一致；任务指定的 X 聚焦测试 4/4 通过，扩展、Social Archiver、Markdown 兜底回归 14/14 通过。未确认零费用时，即使存在 X 用户和 token 路径，Registry 也在构造官方 X client 前以 `X_ZERO_COST_NOT_CONFIRMED` 阻断，且不创建 capture；generic current-page 和 Markdown 路径继续可用。确认分支仅由本地 fake connector 覆盖，bookmark/like 的 endpoint、关系、内容 ID 与 partial receipt 保持隔离。真实 X 费用/权益、OAuth、网络均为 `NOT_RUN`。证据位于 `evidence/SA-103/`。

- SA-104：`command.py`、`sidecars/cli-tools/Dockerfile`、`sidecars/cli-tools/server.py` 与冻结 Overlay 逐字一致；指定聚焦测试 6/6、当前页/扩展/镜像隔离回归 13/13 通过。核心 API/worker 均不挂载 `instagram_session`；只有无公开端口的 cli-tools Sidecar 挂载 `/run/secrets/instagram_session` 并带 Instaloader。核心远程请求只传 username/limit，禁止 session object 未被访问且路径穿越工件被拒绝；无导出 session 时 generic-web 当前页保存仍可用。真实 Instagram session、浏览器、Docker 与网络均为 `NOT_RUN`。证据位于 `evidence/SA-104/`。

- SA-105：Stage 1 的五个产品连接器文件仍与冻结 Overlay 逐字一致；阶段门 4/4、五类来源 focused 回归 29/29 通过。阶段门实际覆盖 generic current-page 默认 L0/L1/L3（L2 关闭）、Social Archiver ZIP 幂等导入、Reddit/X OAuth 归一化以及 Instagram isolated HTTP Sidecar 归一化和路径穿越拒绝。五个真实 canary（generic、Social Archiver、Reddit、X、Instagram）均逐项记录为 `NOT_RUN`，不被 fixture PASS 掩盖，也不互相阻断。证据位于 `evidence/SA-105/`。

- SA-201：`compose.workers.yaml` 和 `http_workers.py` 与冻结 Overlay 逐字一致；任务指定 XHS/health 聚焦测试 5/5、加 worker profile 的回归 7/7 通过。XHS fixture 仅发送 URL/download/index/skip，绝不转发 Cookie；Worker `degraded` 时 generic current-page L0/L1 仍成功。`vendor_sync.py` 已兼容冻结的单来源命令和当前 lock schema，把 GPL-3.0 XHS-Downloader 固定在忽略的 Sidecar build context（detached `afaf2fb459…`），不进入核心镜像。SA-201 期间检测到一条全局凭据式 Git URL 重写，已精准删除并用隔离的非交互公共 Git 子进程防止重入；本地产品/vendor 配置与源码扫描均无凭据标记。GitHub 侧凭据轮换/撤销为 `NOT_VERIFIED`，不得写成已完成。真实 XHS、Docker、浏览器和平台请求均为 `NOT_RUN`。证据位于 `evidence/SA-201/`。

- SA-202：`http_workers.py` 与冻结 Overlay 逐字一致；任务聚焦测试 6/6、XHS/OpenAPI/health/worker-profile/generic 回归 15/15 通过。唯一 OpenAPI URL 路由才会发送 URL/download；歧义时零 POST、明确 degraded；Worker→gallery-dl→yt-dlp 的顺序和“全部失败仍不阻断 generic L0/L1”均由 fixture 绑定。锁定 GPL-3.0 TikTokDownloader 于忽略的 `runtime/vendors/TikTokDownloader`（detached `f404781eb…`），不进入核心镜像。冻结 `python main.py api` 与 pinned 上游不兼容：上游 `main.py` 不解析 API 参数，而 Dockerfile 默认 `python main.py`；因此仅将 DouK Compose 改为真实入口，并加 `stdin_open`/`tty` 让 Owner 自行阅读声明后选择 Web API，绝不自动同意、预写 Cookie 或猜测端点。Compose 结构解析通过。真实 DouK/Docker/平台请求和端口可达性均为 `NOT_RUN`。证据位于 `evidence/SA-202/`。

- SA-203：锁定 GPL-3.0 KS-Downloader 于忽略的 `runtime/vendors/KS-Downloader`（detached `f8d812db…`），不进入核心镜像。实际 pinned `main.py` 明确支持 `api` 子命令，FastAPI 源码的 `POST /detail/` 使用 `DetailModel.text`（`cookies`/`proxy` 为可选上游字段）；故 KS Compose 保持冻结的 `python main.py api`，不作不必要改动。`OpenAPIURLWorkerConnector` 已最小适配为只解析本地 OpenAPI `$ref`：仅当恰有一个文档化 detail/download/parse/extract POST、JSON schema、且唯一 `url`/`text` 字符串字段满足全部必需输入时才调用；只发送该链接字段和显式文档化的 boolean `download`，绝不转发 Cookie、代理或认证值。零/多候选时零 POST、明确 degraded，独立媒体/当前页兜底不受影响。任务测试 8/8、相关回归 22/22、KS Compose 结构、品牌与兼容检查均通过；真实 KS/Docker/平台请求和端口可达性均为 `NOT_RUN`。证据位于 `evidence/SA-203/`。

- SA-204：锁定 Apache-2.0 bilibili-cli `v0.6.2` 于忽略的 `runtime/vendors/bilibili_cli`（detached `489607468…`），只作为 `cli-tools` 的命名 Docker build context；不进入第一方核心镜像。冻结 Sidecar 未安装该固定来源、误传不支持的 `--limit` 参数且把成功的无工件列表读成失败，已按真实上游适配：只允许 `favorites`、`watch-later`、`history` 三个只读 `--json` 命令，history 只传 `--max 1..100`；元数据列表 exit-0 即成功；结构化 `rate_limited` 或 Sidecar HTTP 412/429 统一返回可重试 `BILI_RATE_LIMITED/degraded`，不做绕过/自动重试。B站子进程每次使用空白 HOME/XDG，未接收浏览器 Cookie、代理、认证值或 B站专用 secret；上游浏览器凭据提取功能未被调用。任务测试 12/12、相关回归 29/29、静态 Compose、品牌与兼容检查均通过。Docker daemon 不可用，镜像构建和真实 B站授权/平台请求均为 `NOT_RUN`。证据位于 `evidence/SA-204/`。

- SA-205（Stage 2 Gate）：冻结 `test_stage2_domestic.py` 与当前产品逐字一致；任务指定的 Stage 2/平台扫描/范围扫描测试 6/6、覆盖 XHS、DouK、KS、B站、Worker profile、generic current-page 与状态投影的联合 fixture 回归 34/34 通过。三条 HTTP Worker（`xhs-worker`、`ks-worker`、`douk-worker`）独立注册，B站保持为独立 `cli-tools` Sidecar；两份 Compose 都以无 `.env`、无 secret 解析、无构建/启动的静态模式通过。四个固定 Vendor checkout 和 SA-201～204 PASS 证据均已复核。XHS/Douyin/B站降级 fixture 保持 generic current-page 独立，快手的歧义 OpenAPI 走 degraded/no-POST 且平台扫描不连坐；因此满足本地 Fixture 的“单平台失效不连坐”门。四个平台的真实账号/平台/Docker Canary 仍逐项 `NOT_RUN`，不冒充线上连通性。证据位于 `evidence/SA-205/`。

- SA-301：冻结 PWA 和两项 focused tests 起始时逐字一致，但统一库查询直接 join `user_relation`，同一 canonical content 有多条关系时会重复成多张卡片；已用临时 SQLite fixture 复现（同一 content id、2 条关系、修复前 2 行），再最小适配为每内容一条确定代表关系（active→最新→id），关系筛选仍显示匹配关系，Detail 保留全部关系。PWA 现在明确使用 Feed/Grid/Detail（将历史 `list` 偏好迁移为 `feed`），Detail 显示所有关系标签；增加内部 SVG favicon，并由 HTML/manifest/service worker 缓存，消除真实浏览器的默认 favicon 404。任务测试 4/4、跨 Stage 0–2 相关回归 25/25 通过。使用既有本机 Chrome 和临时 loopback fixture 对 1440px 与 390px 真机式视口实测：各一张统一卡片、Detail 显示两条关系、无控制台/资源错误、无横向溢出；临时数据、截图和服务已停止并移入废纸篓。证据位于 `evidence/SA-301/`。

- SA-302：在 SA-301 的“一内容一张卡”基础上完成全文检索、平台/关系/收藏夹/时间复合筛选和关系历史。FTS 将用户输入转为 literal terms，避免把 FTS 运算符当作查询语法；同一内容的新关系不带文本时保留原有全文索引，并聚合所有非空收藏夹标签，故每个关系的收藏夹都可检索。列表的收藏夹及日期范围筛选在代表关系范围内执行；API 对日期端点归一化为 UTC 日起点/含当日终点，非法或倒置范围返回 422。Detail 的关系按最近观察确定排序，PWA 显示关系/收藏夹、有效或已关闭状态、首次/最近观察、完整扫描缺失次数和关闭日期。partial receipt 不改变缺失计数；精确范围内第一次 complete 缺失仍 active，第二次才关闭。指定测试 5/5、相关回归 15/15、兼容/品牌检查均通过；回环 Chrome 在 1440px 与 390px 实测所有复合筛选、全文命中、两条关系历史、零浏览器错误和无横向溢出。临时服务已停止，运行时、fixture 和截图已移入废纸篓。证据位于 `evidence/SA-302/`。

- SA-303：连接器状态现以一次 fresh probe 为准并带最后检查时间、延迟和中文原因；探针异常被转为 `degraded/HEALTH_<异常>`，不会让 Bootstrap、设置页或首页崩溃。`connector_state` 的三个元数据字段是可加性迁移，无重置。目的地卡也显示检查时间与延迟。失败的目的地回执在任务中心独立可见、可一键重试；重试把原终态 job 安全重入队，回执仍保留以供追溯，排队/运行/完成状态均不会被误报成第二次重试。设置页以 `storage.completion` 明确区分 3/3 完成与未齐；临时 loopback DOM 验证渲染 8 个来源、8 个目的地、0/1 未齐提示、失败 markdown 回执和实际 receipt-retry POST，读回为 job queued/receipt failed。任务指定 18/18、新增状态/回执 22/22、相关回归 8/8、JS syntax、兼容和品牌检查均通过。Chrome 150 已移除旧的命令行 unpacked-extension 自动加载，故 native extension shell/optional-host prompt 为 `NOT_RUN`；DOM 使用真实 HTML/JS、临时 Chrome profile、live loopback API 与窄 Chrome API mock，不冒充原生壳验证。临时服务器均已停止，67 MiB 临时运行时已移入系统废纸篓。证据位于 `evidence/SA-303/`。

- SA-304：可选 ArchiveBox、Karakeep、Linkwarden 与 ArchiveWeb/WACZ 投影均保持为非权威、可删除重建的 Sidecar/文件投影，默认不启用 L2。启动脚本现在按选定 profile 只要求相应 secret，并在任何 Docker network 副作用前完成验证；ArchiveBox 的非空队列必须显式设置 `SOCIAL_ARCHIVE_L2_ENABLED=true` 才能提交。WACZ 导入在 L2 关闭时不读取输入、不建 runtime DB、不写 CAS；L2 开启后先验证 canonical content_id，未知 id 不会留下孤立工件，已知 id 只新增 L2 artifact 且不改 Canonical fields。任务指定 focused 9/9、reader/destination/extension 相关回归 29/29、Shell syntax、Compose 静态结构、兼容、秘密及品牌扫描均通过。`compose.readers.yaml` 解析因 Owner reader env 文件缺失而有意跳过 Docker Compose 渲染；Docker、真实 Reader/ArchiveWeb.page 账户、凭证、浏览器扩展与 provider canary 均为 `NOT_RUN`。任务图为准，SA-304 属于 Stage 3，产品文档已同步。证据位于 `evidence/SA-304/`。

- SA-305（Stage 3 Gate）：冻结 `test_stage3_pwa.py` 起始时只验证 PWA 五文件存在，虽 1/1 通过却不能单独证明阶段 Oracle；保留该断言并将同一阶段测试兼容性加固为真实临时运行时的首次一次性配对、Library/独立 extension API host 分离、一次保存、中文查找、失败回执和重试。加固后发现连续汉字被 SQLite `unicode61` 作为单一 token，`q=可检索` 查不到 `可检索内容`；已以参数化、转义的汉字子串回退补足，同时保留非中文字面量 FTS，未改 schema、未重置 runtime。任务指定测试 3/3、Stage 0/1/3 与资料库/配对/UI/extension/回执/reader/storage 相关回归 72/72、PWA JS/manifest、兼容、秘密及品牌检查均通过。临时 loopback Chrome 实测 1440px 与 390px：中文搜索、Detail、三步向导、Feed、9 个中文下一步、零横向溢出、零 console/runtime/network error；临时 API、Chrome profile、夹具、日志、截图已停并移入系统废纸篓。fixture 验证 Library host 路径与 API host 的 Bearer 分离，但真实 Cloudflare Access/Tunnel/JWT、真实 extension/provider 均为 `NOT_RUN`。证据位于 `evidence/SA-305/`。

- SA-401：GitHub Markdown 目的地固定到 `LinzeColin/Private-Database` 的 `Private-MetaDatabase/SocialArchive/markdown/`；每次导出先读仓库元数据且强制 `private=true`，再读确定性 Contents 路径。相同 Git blob SHA 返回 `noop` 并写回绑定/回执；远端 SHA 漂移会带当前 SHA 修复，不信任旧本地 binding；公开仓、错误目标身份、缺失/异常回执均 fail closed 且保留失败 receipt。任务指定 Mock/Fixture 12/12、关联 Stage 0/4 与 capture/storage 回归 8/8、秘密/品牌扫描、语义协调与兼容验证均通过。此前的本地 Private-Database writer/clone+Git-push sync 与仓库永久 no-clone 边界冲突，现已在调用前 fail closed；这不是结构化事实同步完成声明，官方 API-client 同步和冷备仍只属于待办 SA-504。真实 GitHub/Private-Database 授权、仓库元数据、写入与网络均为 `NOT_RUN`。证据位于 `evidence/SA-401/`。

- SA-402：Notion 目的地维持 `Notion-Version: 2026-03-11`、`data_source_id` 页面父级与数据源标题属性主动校验。新 Page 成功返回后、每批最多 100 个确认的 Block 写入/删除后，均先写入 `pending:` binding；最终完成才提升为真实 projection SHA。这样 101-Block fixture 在第二批 `429 Retry-After: 7` 后重试时复用同一 Page、更新已知 100 个 Block、只追加第 101 个，不创建重复 Page；失败回执也保存已确认的 Page id/path，RuntimeStore 采用该重试延时。指定 Mock/Fixture 14/14、关联 storage/capture/reader/Stage-0 回归 11/11、秘密/品牌扫描、语义协调与兼容验证均通过。真实 Notion Token/数据源/标题属性探测及写入均为 `NOT_RUN`。特别注意：确认 Page 后的后续失败已可恢复；若恰在 Page POST 请求中发生响应丢失，远端副作用仍不可确认，未宣称 exactly-once，需 Owner canary/对账后才可作生产声明。证据位于 `evidence/SA-402/`。

- SA-403：第一方 Obsidian 插件和 Chrome 直写桥接固定为 `http://127.0.0.1:27123`；插件只接受 timing-safe Bearer token、`text/markdown`、20 MiB 以内的请求，并拒绝绝对/编码/`..` 路径与不安全 Vault 基目录。同路径同正文返回 `noop`；扩展的被篡改本机地址也会归一到该固定 loopback，不会把本机 token 发送给其他端口。服务端 Vault write/readback 和 REST Markdown PUT 均有 done/noop binding/receipt fixture。标准导出新增 `library.jsonl`、正文 Markdown 和 `snapshot_sha256` manifest；同快照不因时间戳而重写。此前正文只在 FTS、未进入投影的问题已以只读 body 查询修复，未改 Canonical 写入。指定测试 8/8、关联 destination/extension/storage/reader/Stage-0/Stage-4 回归 36/36、秘密/品牌扫描、语义协调与兼容验证均通过。真实 Obsidian、Chrome 可选权限/插件写入均为 `NOT_RUN`；直写路径的跨目的地持久回执/重试门由后续 SA-404 实施但本条不提前宣称。证据位于 `evidence/SA-403/`。

- SA-404（Stage 4 Gate）：Canonical Store 始终先提交；捕获、手动导出、回执重试和 Worker 四个入口都只允许已完成主动 Probe 且当前授权有效的目的地入队或出站。Markdown 与 ArchiveBox 不再因本地配置被默认标为 connected，必须先真实检查写入/回读或可重放 URL 队列；Notion、Obsidian、GitHub、Karakeep、Linkwarden 保持同一门。Provider 暂时 degraded 时，只有已确认过连接且已失败过的 retry job 可恢复；新 capture 与新注入 job 仍 fail closed。未授权或过期目的地只生成独立失败回执而不触发 adapter/provider 请求，单目的地失败不改写或回滚 Canonical fields。Chrome→固定 loopback Obsidian 直写现在向受配对 API 上报独立 `obsidian_local` done/noop/failed 回执；它严格限制 `Social Archive/*.md` 相对路径，使用服务端计算的 Markdown SHA，并与服务端 Vault/REST 的 `obsidian` binding 分离。Sidepanel 可把本机失败回执路由回固定 loopback 重试；该 receipt 是已认证配对扩展的 attestation，不是服务端对用户 Vault 的实时验证。冻结命令 32/32、全量 157/157、JS 语法、品牌/秘密扫描、语义协调和兼容验证均通过。真实 Provider/账户/凭证/Chrome/Obsidian/Docker/部署 canary 均为 `NOT_RUN`。证据位于 `evidence/SA-404/`。

- SA-501：`AgeEncryptor` 以原对象 SHA 与 recipient fingerprint 缓存并复用唯一 `.age` 密文；`S3ReplicaStore` 只接受已校验 `.age` 文件、上传 cipher/original SHA 与算法元数据，再以完整 cipher SHA 下载回读验证。冻结任务图的 `--store r2 --encrypted-canary` 与既有脚本不兼容（原先 argparse 退出 2），现已兼容该拼写，同时保留位置参数；任何实际远端写/读/删必须显式带 `--encrypted-canary`，无确认只返回 `BLOCKED_USER_CONFIRMATION`，缺 recipient/配置返回非零 `BLOCKED_ENVIRONMENT`，绝不以退出 0 冒充探针成功。隔离 `env -i` 运行冻结 canary 只得到缺 recipient 的非零阻断，未读取凭证、运行 age、生成密文或访问网络。任务指定测试 8/8、相关复制/三副本回归 15/15、全量 161/161、品牌/秘密扫描、语义协调与兼容验证均通过。真实 R2/account/age binary/网络回读和写后删除仍为 `NOT_RUN`；fixture PASS 只证明代码路径。证据位于 `evidence/SA-501/`。

- SA-502：冻结任务图的 `scripts/replicate_objects.py --once` 原先 argparse 退出 2，现兼容这一单次、已有的有界执行语义；无 age recipient 时在 `ensure_directories()` 和 `RuntimeStore.initialize()` 之前以非零 `BLOCKED_ENVIRONMENT` 返回，因此隔离 `env -i` 命令不生成运行时状态。OCI 候选仍先由已验证 R2 过滤，且每个对象在任何 OCI 远端调用前必须再将 R2 receipt 的 `status`、原对象 SHA、cipher SHA、age 算法与当前唯一 age 密文逐项精确比对；任一不符只写失败 OCI receipt、绝不上传或回读。Fixture 覆盖了无 R2 不进队、错误 cipher SHA 不调用 OCI，以及匹配 cipher 的 OCI 上传/回读/verified receipt。任务聚焦 13/13、相关复制/完成态回归 18/18、全量 164/164、品牌/秘密扫描、语义协调与兼容验证均通过。真实 R2/OCI/account/age binary/网络回读、上传或删除仍为 `NOT_RUN`；证据位于 `evidence/SA-502/`。

- SA-503：冻结 `github_release_backup.py --upload` 的 Draft Release 路径保留，但先后加固为：无 recipient、无有效 repository、无 `gh` 或私有仓 metadata 失败时均在运行时目录初始化前 fail closed；实际上传前必须以 `gh repo view` 确认返回的 `nameWithOwner` 等于配置目标且 `isPrivate=true`，Draft 创建后还必须回读 `isDraft=true`。每个候选对象先以当前唯一 age 密文逐项核对 R2 与 OCI receipt 的 verified 状态、原对象 SHA、cipher SHA 与算法；任一不符只写失败 GitHub receipt，不创建/上传/下载 Release。成功路径上传 Manifest 与不超过 1.8 GiB 的 `.age` pack 分片，回读 Manifest 原始哈希、重组 pack SHA 和每个密文 SHA 后才写 verified GitHub receipt；三收据由既有 RuntimeStore 完成态门统一收束。任务聚焦 14/14、相关三副本回归 34/34、全量 177/177、品牌/秘密扫描、语义协调与兼容验证均通过。隔离 `env -i` 的冻结 `--upload` 命令以缺 recipient 非零阻断且不访问 `gh`。真实 GitHub/R2/OCI/account/age binary/网络、Draft 创建、资产上传/下载、删除和发布均为 `NOT_RUN`；证据位于 `evidence/SA-503/`。

- SA-504：冻结 Overlay 的本地 Git clone/commit/push 同步和工作树备份均与全仓 Private-Database no-clone/no-local-write 铁律冲突，因此保持 Oracle 而最小适配为官方 `private_db_client.py` 的 clone-free API 路径。仅所有 Artifact 已由既有 R2/OCI/GitHub 同密文三收据标记 `complete` 的内容才会生成确定性、去 `local_path`、去敏感 metadata/query 参数的事实；其规范 JSON SHA 同时是 Outbox 身份和 API ingest batch。每个成功 ingest 后必须让官方 `verify` 证明账本总数=在仓数且缺失为 0；该 client 即使缺对象时可能 exit 0，故不可解析、缺失或数量不等均保持 pending。冷备只接收当前精确匹配 delivered Outbox 的事实，在临时目录生成可恢复 bundle、age 加密一次、R2 上传/回读成功后才镜像同一密文至 OCI；R2 失败会阻断 OCI。移除了 Compose/.env/install/systemd 的本地 Private-Database 工作树配置，sync timer 显式 `--once`，backup service 不再可写 `/opt/social-archive/runtime`。任务/存储聚焦 31/31、全量 186/186、compile/compose/systemd/brand/secret 检查通过；隔离无凭据命令分别以缺 client 与缺 recipient `BLOCKED_ENVIRONMENT` 返回且临时根为空。真实 Private-Database、R2、OCI、age、网络和远端回读仍为 `NOT_RUN`；证据位于 `evidence/SA-504/`。

- SA-505（历史本地合同记录；下节的真实部署验收已取代其“未验收”状态）：冻结 `install.sh --dry-run` 原先在 dry-run 分支前写 runtime/Secret/.env 并依赖默认 `python3>=3.12`；现在自动选择可用 3.12+ 解释器，并在创建任何文件前退出。`doctor.sh --self-test` 是零写入静态检查，不连接 Docker、loopback、外网、runtime 或 Secret。两域名合同保持 Library Access / 独立 API Bearer：Core 只看实际 Host、不接受 `X-Forwarded-Host` 伪装；配对只在 API Host、拒绝无 Content-Length/超过 16 KiB、保留 10 分钟/5 次门并有 10/min 内存后备。状态发布改为 allowlist/redact 后写 `SOCIAL_ARCHIVE_DATA_ROOT/status/social-archive.json`（0640）；`StateDirectory=social-archive` 安全创建宿主机数据目录，`social-archive-status-web.service` 只读该文件、只绑定 `127.0.0.1:8780`、拒绝写方法，Tunnel 示例精确路由 `status.linzezhang.com`。新增 `prepare_systemd_host.sh`：dry-run 零写入检查部署源；apply 仅允许 root 在 `/opt/social-archive` 执行，受限创建账户/host env/Secret 权限、备份并安装 unit、daemon-reload，绝不 enable/start。65 项相关 fixture/回归、冻结两条命令、Compose 静态解析、shell/brand/secret/systemd/deployment 检查均通过。经用户授权的只读公网探针显示：Library/API 域名无 DNS 解析；status 域名的 `GET /health` 为 403，HEAD 为 `200 text/html/no-cache`，均未达到目标 JSON/no-store 合同。真实 OVH 端口、Cloudflare Access/Tunnel/WAF、真实 API、真实 status systemd/Tunnel 路由随后已按下一节验收；证据位于 `evidence/SA-505/`。

## SA-505 completed deployment correction (2026-07-30 UTC)

本节取代本文件内此前所有“SA-505 未验收/等待 Owner 部署”的历史叙述。经受控真实 OVH 与 Cloudflare 验收，SA-505 已 PASS：Core 与 status origin 分别仅监听 loopback 的 18765/18780，外部直连均失败；未登录 Library UI 被 Access 302 阻断，而独立 API health 为 200、业务路由在无 Bearer 或伪造 Access assertion 时为 401。重生成一次性码后的真实 API exchange 为 200，返回 Bearer 的业务状态为 200；Docker secret 源记录保留，消费状态在 Core 数据卷中以 0600 保存。

Cloudflare 受管 Tunnel 健康且有连接，UI/API/status projection/status fallback/default-404 ingress 与三条代理 CNAME 均逐项读回。可见控制台确认 API 不支持方法 Block 规则和活跃的配对路径/IP/1 次每 10 秒/Block 限流规则；外部请求也得到 PUT=403、无效配对首个=409、紧随其后=429。状态 JSON/health 为 200、JSON 为 no-store 且只含脱敏合同键；其 overall=degraded 仅表示未宣称真实第三方连接器授权。临时 Access 服务令牌诊断没有形成通过证据，已顺序清理并复查为零。完整脱敏记录在 `evidence/SA-505/`。

备份、复制与 Private-Database sync timer 仍未启用；SA-506 的 Fixture 验收已完成，但定时执行与 GitHub/Private-Database 的真实授权继续保持受控，不提前视作 SA-507 发布完成。全部任务包完成前不得提交或推送 GitHub。

## Key decisions

- 冻结架构：`PRESERVE_TRANSACTION_CORE_REBUILD_PRODUCT_SHELL_AND_CONNECTORS`。
- 产品不得有双入口、双事务内核或双权威；旧运行入口、旧 Node workspace、旧测试/脚本、旧文档/证据/机器清单已从当前产品面退休。
- SQLite 仅为可重建 Runtime Journal；长期结构化事实进入 Private-Database；真实授权、平台、云副本和部署仍为 `NOT_RUN`，不得写成 PASS。
- 未配置 Owner `.env` 或 `runtime/secrets/` 时，`doctor.sh --self-test` 仅验证 Compose 结构，不渲染 Compose、不读取秘密，也不冒充已部署或服务运行中；语法检查在内存中完成，不遗留源码字节码缓存。
- 通用网页保存是用户当前页 URL 的受控采集路径；Karakeep/Linkwarden 只接受 URL 投影、可删除并重建，绝不成为 Canonical Store 或反向覆盖事实。真实浏览器和真实 reader Provider 仍为 `NOT_RUN`。
- Reddit 仅把用户授权的 OAuth token 作为出站 Bearer header 使用；不保存密码、Cookie、浏览器认证头，也不绕过访问控制。真实 Reddit OAuth/网络仍为 `NOT_RUN`。

- X 官方 API 仅在 `SOCIAL_ARCHIVE_X_API_ZERO_COST_CONFIRMED=true` 时允许进入 connector；缺失、未知或其他值均在构造 client 前 fail closed。凭证、用户 ID 或 token 路径不是收费确认；本轮 positive path 是本地 fixture，不是线上免费权益或授权证明。

- Instagram account export is an isolated cli-tools Sidecar operation. Core services have no `instagram_session` mount, must not send a session in the remote payload, and accept only relative Sidecar output paths; when export is unavailable, generic current-page capture remains the free user-triggered fallback.

- Stage gate local fixture PASS and real provider canary are separate evidence planes: every fixture assertion must pass, while a missing owner credential/browser/provider remains `NOT_RUN` rather than a synthetic PASS; one platform's real canary state cannot block another platform's fixture gate.

- Public vendor Git operations must ignore global/system configuration, environment-injected Git config and interactive prompts. This is a supply-chain and credential-isolation boundary, not a way to bypass platform authorization; XHS product requests still never receive browser Cookies.

- DouK is an experimental, user-controlled Sidecar. The core only probes OpenAPI for a unique safe URL route and never forwards a Cookie; if the owner has not started the upstream Web API mode, the route is ambiguous, or its algorithm fails, the result is degraded and gallery-dl/yt-dlp/current-page fallback remains independent.

- KS-Downloader is a fixed isolated Sidecar. Source-verified `api` startup is retained; the first-party core resolves only local OpenAPI references and accepts exactly one source-documented safe URL/text request route. Optional upstream Cookie/proxy fields are never populated from user input. An ambiguous or malformed document causes degraded with no POST, never endpoint inference.

- Bilibili is a fixed Apache Sidecar-only dependency. The HTTP surface can issue only `favorites`、`watch-later`、`history` with source-documented JSON arguments; all write verbs fail before process execution. A metadata-only successful list does not require a downloaded artifact. Rate limit (source structured result or HTTP 412/429) is `BILI_RATE_LIMITED/degraded`, never a bypass attempt, and its unknown receipt never closes relations. Bilibili has no browser-profile mount or Bilibili credential secret; every subprocess gets a fresh per-run HOME/XDG boundary.

- 统一资料库以 `content` 作为卡片身份而非 `user_relation` 身份：列表始终一内容一行；未筛选时选择 active、最新、稳定 id 的代表关系，按关系筛选时选择该匹配关系，Detail 显示所有关系。这样既不重复平台内容，也不丢失关系事实。

- SA-302 的收藏夹与观察时间是关系事实而非全局内容事实：它们只在选择代表关系时缩小范围，平台与全文仍以 canonical content 为入口。日期只接受 ISO 8601 日期/日期时间，日期终点包含整天；partial receipt 永远不能推进关系关闭，只有精确 scope 的两次 complete 缺失会关闭关系。FTS 标签从该内容的全部非空关系收藏夹重建，防止一次无文本的新关系抹去旧正文索引。

- SA-303 的状态投影遵循“fresh probe 优先且 probe 失败 fail closed”：持久化 healthy 不能遮蔽当前 `blocked_environment`，但连接器检查异常必须降级为带中文下一步的状态数据而非把用户页打断。失败目的地回执是不可变审计事实；重试只改变可执行 job 的状态，不能将旧失败回执伪造为成功或删除。

- Reader/archiver 只投影、不获得 Canonical Store 权威。各 reader profile 的 secret 需求彼此隔离，且任何 Docker network/create/start 副作用前必须先完成 profile 与 secret 校验；读者退出、删除或 degraded 均不得回滚核心采集。

- ArchiveBox 高保真采集和 ArchiveWeb/WACZ 文件导入均是 L2：空队列可安全 no-op，非空 ArchiveBox 队列必须显式启用 L2；WACZ 在未启用 L2、未知 canonical content 或无效输入时 fail closed。只允许既有 canonical content 获得附加 L2 artifact，绝不以投影反向创建或改写权威内容。

- Stage 路由以冻结任务图为权威，不能以旧产品文档替代：SA-304 是 Stage 3 的可选阅读器任务，Stage 4 才进入 Notion、Obsidian、GitHub、Markdown 与 JSONL 目的地。

- Stage 3 阶段门不能仅用“PWA 文件存在”替代用户路径证据：冻结 shell fixture 必须保留，但当前产品测试还必须覆盖一次性配置、Library/extension 身份边界、保存、中文检索、失败回执/重试、移动端及唯一中文下一步。真实 Cloudflare/Provider 证据与本地 fixture 证据保持分层，不得互相冒充。

- SQLite `unicode61` 对连续汉字的整段 token 化不足以支撑用户输入的中文部分匹配。非汉字仍走 quoted FTS literal terms；每个连续汉字片段以参数化、LIKE-escaped 子串在既有 FTS columns 上收窄。这个回退不得接受 SQL/FTS 操作符、不得改写既有内容或重建 Runtime Journal。

- GitHub Markdown 目的地不是任意私有仓写入器：只接受 `LinzeColin/Private-Database`，且路径必须位于 `Private-MetaDatabase/`。本地 SQLite binding 只是投递记录，不能取代每次导出的仓库私有性和远端 Contents SHA 对账；公开、身份不符、SHA/路径/commit 回执不完整均不得确认成功。

- Notion 的本地 binding 是已确认远端 Page/Block 前缀的恢复检查点，不是对未收到 provider 回执之 POST 的臆测。每次追加必须收到与提交 children 一一对应且唯一的 Block ID 才能推进检查点；429 仅在 provider 返回有效 `Retry-After` 时传入 job 延时，网络错误仍保留失败 receipt 和可重试任务。真实 Token/数据源/标题属性与模糊请求副作用继续是 `NOT_RUN`，不得把 Mock 覆盖写成线上 exactly-once。

- Obsidian 本机桥接不是任意 URL 写入器：Chrome 与插件共同固定 `127.0.0.1:27123`，插件目录必须是当前 Vault 内的安全子目录，内容只接受 Markdown 且不超过 20 MiB。同内容返回 `noop`。`content_fts.body` 是导出所需的已保存正文读取面；只读投影可读取它，但不得把 StandardExporter、Markdown/JSONL 或 Obsidian 输出说成 Canonical 写入、Private-Database 同步或三地密文备份。真实插件/Chrome canary 仍为 `NOT_RUN`；SA-404 已把其配对扩展 attestation 以独立 `obsidian_local` receipt/binding 接入任务中心与重试，绝不把它冒充服务端 Vault/REST 读回验证。

- SA-404 的授权门要求“当前 live configuration + 持久化 enabled/last_checked_at + connected 成功状态”，配置本身不是授权。Capture、手动 export、receipt retry 与 Worker 都会复核；未通过者不得调用 adapter/provider。若连接在既有失败 job 后暂时降为 `degraded`，Worker 只会在该 job 已有失败尝试（`attempt_count > 0`）时允许恢复；新 capture、首次尝试和新注入 job 都不会自动调度。每个 destination 的 done/noop/failed receipt 独立保存，失败可重试性只对 429、5xx、网络错误或明确 `degraded` 传播；认证、配置、策略错误不做无意义自动重试。

- SA-501 的 age recipient 是可公开的加密接收者；私钥/identity 只允许未来显式 restore drill 使用，`AgeEncryptor`、R2/OCI 复制和 probe 都不得读取它。真实对象 canary 必须显式带 `--encrypted-canary`，仅 `--store` 返回 `BLOCKED_USER_CONFIRMATION`；缺 recipient 或 R2 配置为非零 `BLOCKED_ENVIRONMENT`。密文文件、远端 metadata 和回读 SHA 才是可验证副本证据；本地 plaintext、secret file 内容和 private identity 均不得进入远端、runtime report 或日志。SA-501 只绑定 R2 入口，OCI/GitHub 第二、第三副本和完成态仍由 SA-502/SA-503 负责。

- SA-502 不把“R2 的 verified 状态”单独当作 OCI 授权：同一 artifact 的 R2 receipt 必须与本次 `EncryptedObject` 的 original SHA、cipher SHA 和算法完全相同，才允许 OCI `put_encrypted` 和回读；缺少、未验证或任一字段漂移都不触发远端调用。`--once` 是冻结兼容拼写，不启动守护循环；recipient 守卫必须先于任何本地 runtime 初始化，避免一次失败的命令留下伪进度。

- SA-503 同样不信任“OCI 已 verified”这一状态位：GitHub 第三副本只可复用已同时由 R2 与 OCI 回读确认的当前 age 密文；两份 receipt 的 status、original SHA、cipher SHA、算法必须逐项精确一致，任何漂移都留下失败 GitHub receipt 而不产生 Draft 或 Asset 调用。`--upload` 是显式写入意图，但仍先验证目标 `nameWithOwner/isPrivate`，再验证新建 Release 的 `isDraft`；私有性、目标身份或 Draft 状态任一未知/错误均无本地 runtime 初始化和无远端资产写入。

- Private-Database 禁止 clone、挂载工作树、直接本地写入、Git commit 或 Git push。SA-504 已以官方 API client 的 `ingest`/严格 `verify` 实现完成态事实同步，并让 cold backup 只消费精确 matching 的 delivered Outbox facts；Runtime SQLite 和 Markdown projection 仍不是长期事实权威。真实 provider/账户验证与 local fixture PASS 严格分层，前者仍为 `NOT_RUN`。

- SA-505 的 Core 对 Library Access 的 Host/Header 检查是 Tunnel/Cloudflare Access 边界后的最小防线，不是已验证的 Cloudflare JWT/provider 配置证明。真实验收必须确认 Cloudflare 会在 API Host 去除/不信任伪造 Assertion、UI Host 的 Access 会话实际注入 Assertion，且 Tunnel 的公网与 loopback 边界符合文档。`status.linzezhang.com` 的本地 origin 已收束为受限 systemd 服务；`prepare_systemd_host.sh` 消除了宿主机账户、文件权限、env/unit 安装的隐式前提，但其 apply 尚未在真实 OVH 执行。最新只读公网证据显示状态路由尚未按合同上线；其 OVH 启动状态、Tunnel、TLS、缓存和路由仍必须由真实证据证明；不得把本地 fixture 说成已发布。

## Verification

- `python -m pytest -q tests/focused/test_core_capture.py tests/focused/test_runtime_store.py tests/focused/test_legacy_migration.py tests/focused/test_brand_migration.py`
- `python scripts/check_brand.py`（仅历史 Changelog、迁移文档/测试/验证器可出现旧身份）
- `python ../social-archive-taskpack-compat/v0.0.0.4/scripts/validate_compatibility.py --base-zip <frozen-v0.0.0.4-zip>`（使用 Python 3.12）
- `python -m pytest -q tests/focused/test_extension_e2n_contract.py tests/focused/test_cloud_pairing.py tests/focused/test_extension_api.py tests/focused/test_beginner_journey.py`
- `source .venv/bin/activate && python3 -m pytest -q tests/stage/test_stage0_walking_skeleton.py && bash scripts/doctor.sh --self-test`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_generic_web_connector.py tests/focused/test_markdown_importer.py tests/focused/test_social_archiver_import.py tests/focused/test_reader_projection.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_reddit_connector.py tests/focused/test_oauth_connectors.py`

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_x_connector.py tests/focused/test_x_zero_cost_gate.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_extension_e2n_contract.py tests/focused/test_social_archiver_import.py tests/focused/test_markdown_importer.py`

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_instagram_connector.py tests/focused/test_command_connectors.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_generic_web_connector.py tests/focused/test_extension_e2n_contract.py tests/focused/test_worker_profiles.py`

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/stage/test_stage1_western.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_generic_web_connector.py tests/focused/test_social_archiver_import.py tests/focused/test_reddit_connector.py tests/focused/test_oauth_connectors.py tests/focused/test_x_connector.py tests/focused/test_x_zero_cost_gate.py tests/focused/test_instagram_connector.py tests/focused/test_command_connectors.py tests/focused/test_extension_e2n_contract.py`

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 python3 scripts/vendor_sync.py --source xhs_downloader --resolve-and-lock`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_xhs_connector.py tests/focused/test_health_gated_connector.py tests/focused/test_worker_profiles.py`

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 python3 scripts/vendor_sync.py --source douk --resolve-and-lock`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_openapi_probe_connector.py tests/focused/test_health_gated_connector.py`
- `docker compose -f compose.workers.yaml --profile douk-experimental config`（仅结构解析；不启动服务）

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 python3 scripts/vendor_sync.py --source ks_downloader --resolve-and-lock`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_openapi_probe_connector.py tests/focused/test_scan_platform_isolation.py`
- `docker compose -f compose.workers.yaml --profile kuaishou config`（仅结构解析；不启动服务）

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 python3 scripts/vendor_sync.py --source bilibili_cli --resolve-and-lock`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_command_connectors.py tests/focused/test_scan_scope_isolation.py`
- `docker compose -f compose.yaml config --no-env-resolution --no-interpolate --no-path-resolution -q`（仅结构解析；不读取 `.env`、不启动服务）

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/stage/test_stage2_domestic.py tests/focused/test_scan_platform_isolation.py tests/focused/test_scan_scope_isolation.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/stage/test_stage2_domestic.py tests/focused/test_xhs_connector.py tests/focused/test_openapi_probe_connector.py tests/focused/test_health_gated_connector.py tests/focused/test_command_connectors.py tests/focused/test_scan_platform_isolation.py tests/focused/test_scan_scope_isolation.py tests/focused/test_worker_profiles.py tests/focused/test_generic_web_connector.py tests/focused/test_status_projection.py`
- `docker compose -f compose.workers.yaml --profile xiaohongshu --profile kuaishou --profile douk-experimental config --no-env-resolution --no-interpolate --no-path-resolution -q`（仅结构解析；不读取 `.env`、不启动服务）

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_library_api.py tests/focused/test_ui_contract.py`
- `node --check apps/pwa/app.js && python3 -m json.tool apps/pwa/manifest.webmanifest >/dev/null`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_library_api.py tests/focused/test_replica_completion.py tests/focused/test_scan_scope_isolation.py tests/focused/test_ui_contract.py tests/stage/test_stage0_walking_skeleton.py tests/focused/test_beginner_journey.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_extension_e2n_contract.py tests/focused/test_destination_probes_and_receipts.py tests/focused/test_storage_completion_contract.py tests/focused/test_pwa_contract.py tests/focused/test_extension_api.py tests/focused/test_status_projection.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_destinations.py tests/focused/test_runtime_store.py tests/focused/test_connector_run_api.py tests/focused/test_health_gated_connector.py`
- `node --check apps/browser-extension/options.js && node --check apps/browser-extension/sidepanel.js`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_reader_profiles.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_reader_profiles.py tests/focused/test_reader_projection.py tests/focused/test_destinations.py tests/focused/test_destination_probes_and_receipts.py tests/focused/test_free_destination_contract.py tests/focused/test_generic_web_connector.py tests/focused/test_quota_guard.py tests/focused/test_extension_api.py`
- `/bin/bash -n scripts/start_readers.sh && /bin/bash -n scripts/archivebox_sync.sh && /bin/bash -n scripts/stop_readers.sh`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_compose.py compose.readers.yaml && python3 scripts/secret_scan.py && python3 scripts/check_brand.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/stage/test_stage3_pwa.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_private_database_writer.py tests/focused/test_private_database_sync.py tests/focused/test_destination_probes_and_receipts.py tests/focused/test_destinations.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_destination_probes_and_receipts.py tests/focused/test_destinations.py tests/focused/test_extension_api.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_obsidian_bridge_contract.py tests/focused/test_free_destination_contract.py tests/focused/test_exports.py && node --check apps/obsidian-plugin/main.js`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/stage/test_stage0_walking_skeleton.py tests/stage/test_stage1_western.py tests/stage/test_stage3_pwa.py tests/focused/test_beginner_journey.py tests/focused/test_capture_api.py tests/focused/test_cloud_pairing.py tests/focused/test_social_archiver_import.py tests/focused/test_library_api.py tests/focused/test_pwa_contract.py tests/focused/test_ui_contract.py tests/focused/test_extension_e2n_contract.py tests/focused/test_extension_api.py tests/focused/test_status_projection.py tests/focused/test_destination_probes_and_receipts.py tests/focused/test_storage_completion_contract.py tests/focused/test_replica_completion.py tests/focused/test_reader_profiles.py tests/focused/test_reader_projection.py tests/focused/test_destinations.py tests/focused/test_free_destination_contract.py tests/focused/test_quota_guard.py tests/focused/test_runtime_store.py tests/focused/test_core_capture.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_destination_probes_and_receipts.py tests/focused/test_extension_api.py tests/focused/test_destinations.py tests/focused/test_reader_projection.py tests/focused/test_reader_profiles.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q`
- `node --check apps/browser-extension/shared.js && node --check apps/browser-extension/background.js && node --check apps/browser-extension/options.js && node --check apps/browser-extension/popup.js && node --check apps/browser-extension/sidepanel.js`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_brand.py && PYTHONDONTWRITEBYTECODE=1 python3 scripts/secret_scan.py .`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_encrypted_replication.py tests/focused/test_s3_replication.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_encrypted_replication.py tests/focused/test_s3_replication.py tests/focused/test_replication_pipeline.py tests/focused/test_replica_completion.py tests/focused/test_free_destination_contract.py tests/stage/test_stage4_replication_exports.py`
- `/usr/bin/env -i PYTHONDONTWRITEBYTECODE=1 <project-venv-python> scripts/probe_object_store.py --store r2 --encrypted-canary`（预期非零 `BLOCKED_ENVIRONMENT`；剥离所有凭证环境，不发生远端探针）
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_replication_pipeline.py tests/focused/test_replica_completion.py tests/focused/test_s3_replication.py`
- `/usr/bin/env -i PYTHONDONTWRITEBYTECODE=1 <project-venv-python> scripts/probe_object_store.py --store oci --encrypted-canary`（预期非零 `BLOCKED_ENVIRONMENT`；剥离所有凭证环境，不发生远端探针）
- `/usr/bin/env -i PYTHONDONTWRITEBYTECODE=1 <project-venv-python> scripts/replicate_objects.py --once`（预期非零 `BLOCKED_ENVIRONMENT`，且 recipient 守卫先于 runtime 初始化）
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_release_pack.py`
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_release_pack.py tests/focused/test_encrypted_replication.py tests/focused/test_s3_replication.py tests/focused/test_replication_pipeline.py tests/focused/test_replica_completion.py tests/focused/test_free_destination_contract.py tests/focused/test_storage_completion_contract.py tests/stage/test_stage4_replication_exports.py`
- `/usr/bin/env -i PYTHONDONTWRITEBYTECODE=1 <project-venv-python> scripts/github_release_backup.py --upload`（预期非零 `BLOCKED_ENVIRONMENT`；无 recipient 时先于 runtime 和 `gh`）
- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' python3 -m pytest -q tests/focused/test_private_database_writer.py tests/focused/test_private_database_sync.py tests/focused/test_private_database_backup.py tests/focused/test_replication_pipeline.py tests/focused/test_release_pack.py tests/stage/test_stage4_replication_exports.py`
- `/usr/bin/env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 SOCIAL_ARCHIVE_DATA_ROOT=<isolated-empty-temp>/sync <project-venv-python> scripts/sync_private_database.py --once`（预期非零 `PRIVATE_DATABASE_CLIENT_UNAVAILABLE`，根为空）
- `/usr/bin/env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 SOCIAL_ARCHIVE_DATA_ROOT=<isolated-empty-temp>/backup <project-venv-python> scripts/backup.py --once`（预期非零 `AGE_RECIPIENT_MISSING`，根为空）

## Next task

仍是 SA-506，不能进入 SA-507：先补齐专用于 Social Archive 的 R2 endpoint/bucket/最小 S3 凭据、OCI S3-compatible endpoint/bucket/可读写回删列举凭据，以及离线 age recovery identity 方案。其他项目的 R2 凭据、单向 OCI PAR 与现有主机备份密钥均不等价、不得复用。收到这些输入或明确授权创建它们后，运行显式合成密文 canary；只有 R2、OCI、GitHub Private 三份真实同密文读回收据与恢复结果都 PASS，SA-506 才可收束，之后才允许 SA-507。全部 32 项均 PASS 前不得 Git stage、commit、push、merge 或创建发布物。

## Recovery boundary

- 恢复标签：`social-archive-pre-v0.0.0.4-20260730t095749z`。
- 默认只生成 rollback plan；实际回滚需要任务包要求的精确确认。
- 不读取、复制、迁移或删除遗留忽略运行时目录。
- 保留本任务生成的 `runtime/vendors/XHS-Downloader`、`runtime/vendors/TikTokDownloader`、`runtime/vendors/KS-Downloader`、`runtime/vendors/bilibili_cli` 与最新单来源 `runtime/vendor-resolved.json` 供后续国内连接器阶段使用；最终任务包完成后再按清理合同处理派生运行时。

## SA-507 frozen candidate gate (2026-07-30 UTC)

本节覆盖此前“下一任务仍是 SA-506”及“任务包完成前不得提交”的历史状态：SA-506 已完成；当前已经在同一工作树完成本地 checkpoint、合入冻结前的最新 `origin/main`、并运行 SA-507 唯一一次全量应用回归。候选为 `2cde65edf30cefac7f33e2eb1f4192d31bbd2d9a`，产品树为 `fbda32ab30ecaab76651f3dd92801d36b7b513e8`。`214 passed`；兼容任务包 `verify-fast` 为 26/26 PASS；结构性 `scripts/final_verify.py` 为 PASS，且 `application_suite_rerun=false`。回滚仍只返回 `ROLLBACK_PLAN`，恢复标签及 ignored legacy runtime 保护不变。

严格发布状态是 **DEGRADED，不是 PASS**：R2 与 OCI 的专用私有桶 age 密文写入、读回校验、删除 canary 已在 SA-506 通过，但 GitHub Private Draft 的第三同密文读回、Private-Database 官方 clone-free 对账、Docker image digest 与部署 smoke 仍是 `NOT_RUN`。本机 Docker daemon 不可用；用于新建最小权限 GitHub fine-grained 授权的 Owner sudo/passkey 尚未完成。宽权限 CLI 授权及已知不安全的旧备份 credential 均未使用；受保护目录只做过文件名/权限元数据检查，未读取任何 secret 内容。

`evidence/SA-507/RESULT.json`、`COMMAND_LOG.json`、`RELEASE_REPORT.json` 与 `evidence/final-verification.json` 已记录候选哈希、唯一全量测试、结构复验、回滚计划与所有 `NOT_RUN` 边界。由于第三副本/对账未闭合，尚未创建 release tag、GitHub source push、GitHub Release、Private-Database fact、镜像或部署；不能把本地任务包验证误报成生产发布。

### Resume point

1. Owner 完成 GitHub sudo/passkey，提供/配置只限 Social Archive 私有归档仓所需操作的最小权限 fine-grained 授权；同时配置官方 Private-Database clone-free client 与专用授权。
2. 在候选代码未变化的前提下，运行 GitHub Draft 同密文上传/下载回读、Private-Database ingest/verify、三目标恢复和镜像/部署 smoke；仅更新环境证据，不重复全量应用测试。
3. 只有这些真实收据均通过后，才把 SA-507 从 `DEGRADED` 收束为 PASS，创建版本 tag，并按 Owner 已授权的“任务包整体完成后再上传”策略推送到 `main`。若候选源代码改变，先重冻新候选并对新候选运行唯一一次全量回归。

## SA-507 candidate update (2026-07-31 UTC)

本节覆盖上一节中以 `2cde65ed` 为候选且“Docker 不可用”的历史记录。Docker 已在本机可用后发现并修复两项真实 P0：先补上 `.dockerignore`，使 `.env`、运行时、凭据邻近文件和缓存不进入 Docker build context；随后发现服务在容器内绑定 `127.0.0.1` 导致端口映射不可达，故仅在 Docker image 默认环境中设为 `SOCIAL_ARCHIVE_HOST=0.0.0.0`，不改变宿主机 Compose 的 loopback 映射策略。二者均由 `tests/focused/test_container_build_context.py` 固化。

当前经测试的功能候选为 `2de08bdf098b5a340654677c0682d8746a55c407`，完整树 `6e67c856abd8b26710ae1d93c7e49b558b434f67`、产品树 `dadbdfebd64ab8bda546cf6b9d616cad4324ce76`、清单 SHA-256 `f94c6d1fd1b1a0c7716fc9c65e0c69294e41d6c7956b7dfb8c729d9c8033f78e`。它在冻结后唯一一次全量应用回归为 `217 passed`（1 条既有依赖弃用警告，8.44s）；冻结兼容任务包 `verify-fast` 26/26 PASS；`scripts/final_verify.py` 为 PASS 且 `application_suite_rerun=false`；回滚脚本只返回 `ROLLBACK_PLAN`，恢复标签和 ignored runtime 保护保持不变。`2cde65ed`（214 passed）和 `26713a3`（216 passed）均因后续 P0 修复而明确废弃，绝非对未变化候选的重复全量测试。

当前候选本机 Docker build 成功，local-only image id 为 `sha256:4dbbcd63375cda08e67f326584deb1a33c95ad72001dd60d1e09eafc34629ac2`；无任何卷挂载的临时容器在仅本机回环端口映射下 `/health` 通过。临时容器已停止，两张本轮候选 image tag 已精确删除；未运行全局 Docker 清理。此结果只证明本机镜像可构建和启动，**不等于**远端 image push、OVH/Cloudflare 部署或生产 smoke。

严格发布状态仍为 **DEGRADED，不是 PASS**：GitHub Private Draft 的第三同密文上传/下载回读、Private-Database 官方 clone-free `ingest`/严格 `verify`、三目标真实恢复及生产部署 smoke 都尚未执行。现有宽权限 GitHub CLI OAuth 与受保护目录中已知不安全的旧凭据仍未使用，且受保护目录未读取 secret 内容。没有 GitHub source push/tag/release、Private-Database 写入、用户数据上传、生产部署、定时器启用、额外 worktree 或 destructive rollback。

### Updated resume point

1. 仅由 Owner 完成 GitHub sudo/passkey 后，配置只限 Social Archive 私有归档仓所需操作的最小权限 fine-grained 授权；同时在正式主机配置官方 Private-Database clone-free client、专用授权与生产部署入口。
2. 若 `2de08bdf` 的功能源码未变，仅执行 GitHub 同密文 Draft/readback、Private-Database ingest/verify、三目标恢复和生产 smoke，并更新环境证据；**不得**为未变化候选重跑全量应用测试。
3. 只有所有真实收据通过后才把 SA-507 收束为 PASS、创建版本 tag、推送到 `main`，并收尾唯一工作树；任何功能源码改变都先产生新候选并只对该新候选运行一次完整回归。

## SA-507 candidate update (2026-07-31 UTC, worker health correction)

本节覆盖上一节中以 `2de08bdf` 为当前候选的记录。线上只读检查发现 `core-worker` 继承了 image 内仅适用于 API 的 `/health` probe；worker 本身不监听 HTTP，因此即使进程实际运行也会永久显示 `unhealthy`。最小修复只在 `compose.yaml` 的 `core-worker` 明确声明 `healthcheck.disable: true`，并由 `tests/focused/test_deployment_contract.py` 固化。没有修改事务核心、连接器、用户数据、存储契约或宿主机 API 的 loopback 暴露策略。

当前经测试的功能候选为 `752b8bb493e3bd57f899cd98ac6bc8b1e9c41a3c`，完整树 `cc9f2963319e60510e884dbb53005a3f928a2a0d`、产品树 `9b8682d70bfa8c2d4e728e7e10f1cb7e8301dc0c`、产品清单 SHA-256 `806f7627e2cd95ae342053f7453fedf2b32064017cacb2813157fc52929fd113`。该候选在冻结后唯一一次全量应用回归为 `218 passed`（1 条既有 Starlette/httpx 弃用警告，8.16s）；兼容任务包 `verify-fast` 26/26 PASS；回滚脚本只给出 `ROLLBACK_PLAN`，恢复标签仍为 `social-archive-pre-v0.0.0.4-20260730t095749z`。此前 `2cde65ed`（214 passed）、`26713a3`（216 passed）及 `2de08bdf`（217 passed）均因后续真实 P0 而明确废弃，绝非对同一候选重复全量测试。

本机镜像 `sha256:974036a7e8376b1beff973fdda44d7408cbf1486a4caa58df10ef2b958c15101` 构建成功；无卷挂载的临时 API 容器通过仅本机回环端口的 `/health`。临时容器和精确候选 image tag 已删除。一次错误的 worker `--help` 探针进入循环后立即中断，未作为验收证据且未留下容器。线上只读 Compose diff 证明差异仅为这一 worker healthcheck 声明；在保留 `/opt/social-archive/compose.yaml.pre-worker-healthcheck-20260731T002200Z` 回滚副本后，只重建了 `core-worker`，API 仍为 healthy，worker 状态变为 `no-healthcheck`。这只是最小运行纠偏，**不是**当前源代码的完整生产部署。

严格发布状态仍为 **DEGRADED，不是 PASS**。部署的 GitHub secret 文件为空且归档目标非 canonical，不能创建所需 GitHub Private Draft/asset 的第三同密文收据；宽权限本地 OAuth 与已知不安全旧凭据均未使用。Private-Database 的配置 client 路径不存在；主机上发现相同的 `private_db_client.py` 副本但没有权威目标映射或专用授权，因此没有 `ingest`/严格 `verify`。没有 GitHub source/tag/release push、Private-Database 写入、用户数据上传、镜像推送、完整生产部署、计时器启用、额外 worktree 或破坏性回滚。

### Updated resume point (752b8bb4)

1. 在不改变候选功能源码的前提下，先取得只限 Social Archive canonical 私有归档仓的最小权限 fine-grained GitHub 授权，并由权威配置确定 Private-Database clone-free client 的唯一目标和专用授权；不得回退使用宽权限或旧凭据。
2. 仅在这些环境门通过后，执行 GitHub Draft 同密文上传/下载回读、Private-Database `ingest`/严格 `verify`、三目标恢复、镜像推送及完整生产部署 smoke；这些均须生成真实收据。
3. 所有真实收据均通过后，才将 SA-507 标记为 PASS、创建 tag、按整体任务包完成后的授权推送 `main` 并收尾唯一工作树。任何功能源码变化都必须新冻候选，并只对该新候选运行一次完整应用回归。

## SA-507 candidate update (2026-07-31 UTC, Private-Database legacy manifest verification)

本节覆盖上一节中以 `752b8bb4` 为候选的记录。官方 `Private-Database` clone-free client 的 `verify Private-MetaDatabase` 对当前账本返回 exit 0，但摘要把 5 条历史 EEI 记录列为“缺失”；原因不是对象丢失，而是这些不可变历史条目的 `object_path` 保留了 `Private-MetaDatabase/` 前缀，而旧 verifier 会再拼接一次 area。此处不能以文字摘要直接放行，也不能改写私有账本或复制 client：`scripts/sync_private_database.py` 只在官方摘要的总数关系严格成立时，经同一官方 client 只读取 `manifest.jsonl`，校验内容寻址路径、唯一性和总数，再逐个读回 5 个 legacy 对象并核对精确字节数和 SHA-256；任一不符仍失败。

当前经测试的功能候选是 `0a9fbf3b2051640e61c42b17173bf86deaca3e5d`，完整树 `db5351cfa0d76df90e7b11ba2b1ef7068044d67e`、产品树 `b12b55272d156abd5045c17ac19ebaef7592714d`、276 个产品追踪文件的清单 SHA-256 为 `c3cab908cd5edc7eda7b9c3eb13404c1f2573ed5efc79ffa1e90f98f235ab591`。它的冻结后唯一一次全量应用回归为 `220 passed`（1 条既有 Starlette/httpx 弃用警告，7.93s）；兼容任务包 `verify-fast` 26/26 PASS；结构验证保持 `application_suite_rerun=false`。`752b8bb4`（218 passed）因上述严格兼容问题明确废弃；这是功能源码变更后的新候选，不是对未变化候选重复跑全量测试。

真实只读账本核验结果为：官方 exit 0、账本 31 条、canonical 路径 26 条、历史全前缀路径 5 条，五个对象均经官方 client 读回并 SHA-256 匹配。没有 `ingest`、checkout、clone、commit、push 或 Private-Database 持久写入。这个 PASS 只修复全局历史账本的读兼容；当前并没有 Social Archive 完成态事实，产品 fact `ingest`/严格 `verify` 与冷备仍是 `NOT_RUN`。

为解除第三密文副本的身份门，已创建空私有仓 `LinzeColin/Social-Archive-Vault`，并读回 `private=true`、`visibility=private`、`default_branch=main`。未上传源码、用户数据、密文、Release、Asset 或 tag。GitHub 中已暂存一个未提交的 30 天 fine-grained token 表单：唯一选择该仓，`Contents: Read and write`，强制 `Metadata: Read-only`；这仍不是 token、未写入服务端、未产生 Draft/asset。旧受保护备份 PAT 已有明文暴露记录，本机宽权限 OAuth 也不复制到服务端，二者均不用于归档上传。

严格发布状态仍为 **DEGRADED，不是 PASS**：R2/OCI canary 与本地 Docker/API、worker health correction 通过；GitHub Private Draft 同密文 readback、Social Archive facts sync、三目标恢复、镜像发布及完整生产部署 Smoke 尚未执行。没有 GitHub source push/tag/release、Private-Database fact、用户数据上传、完整源代码生产部署、timer enablement、额外 worktree 或破坏性回滚。

### Updated resume point (0a9fbf3b)

1. 在 GitHub token 表单最终生成前，取得即时确认；生成后只把 token 以 0600 服务端 secret 配置给 `LinzeColin/Social-Archive-Vault`，不显示、不提交或复用宽权限/暴露旧凭据。
2. 在功能候选不变的前提下，运行 GitHub Draft 同密文上传/下载回读；在权威生产 client/auth 下运行 Social Archive facts `ingest`/严格 `verify`、三目标恢复、镜像发布和完整部署 Smoke；只更新环境证据，不重跑全量应用套件。
3. 只有所有真实收据通过后，才将 SA-507 收束为 PASS、创建 tag、推送/合并 `main` 并收尾唯一 worktree；若功能源码变更，先冻结新候选并只对该候选运行一次完整应用回归。

## SA-507 environment continuation (2026-07-31 UTC)

Owner 已明确授权创建无过期、唯一范围为 `LinzeColin/Social-Archive-Vault` 的 fine-grained token；最终 token 仅有 Contents read/write 和必需的 Metadata read。第一枚在 provider 的一次性显示页被自动化渲染后立即撤销、从未安装；替换 token 未输出到证据，按一次性 stdin 写入生产机 `github_token`，核验为 `0600 root:root`，本地临时载体已删除。使用该 token 的 `gh repo view` 已读回 `LinzeColin/Social-Archive-Vault` 为 private。

实际在生产机运行 `scripts/github_release_backup.py --upload`，以受保护 age identity 导出的**公开 recipient**只注入该受限进程，结果为 `PASS / object_count=0 / 没有待复制对象`。因此没有创建 Draft、Asset、密文或 GitHub receipt；SA-507 继续是 **DEGRADED，不是 PASS**。这不是 token 或 GitHub 权限失败：此前 SA-506 的 R2/OCI canary 已按合同删除，生产 `.env` 的 R2/OCI endpoint 与 bucket 均为空、四个相关 secret file 都不可读，当前没有任何具备 R2+OCI verified receipt 的 runtime artifact，不能手工制造/补写第三副本前置收据。

下一步需要 Owner 对创建并配置**专用私有** R2 与 OCI S3-compatible bucket、最小读写/回读凭据给出即时确认；不得复用其他项目 R2 credential、OCI 单向 PAR 或旧主机备份密钥。获准后，用真实核心路径创建不含用户数据的持久 storage canary，依序由 R2、OCI 和 GitHub Draft 取得同一 age ciphertext 的真实读回收据；之后才可进入 Private-Database 完成态事实、三目标恢复和完整部署 smoke。功能源码仍保持冻结候选 `0a9fbf3b2051640e61c42b17173bf86deaca3e5d`，无需重跑全量应用套件。

## SA-507 candidate update (2026-07-31 UTC, platform canary authentication)

本节覆盖上一节末尾的 `0a9fbf3b` 候选声明。生产 loopback 的无效请求确认 pairing-required core 会返回 `401`，同时暴露 `scripts/platform_canary.py` 的 generic-web 分支此前没有发送受限 Bearer token；这会让本应可执行的无用户数据 storage canary 被错误地阻断。最小修复只在该脚本读取既有 `api_token_file`，在 token 存在时传入 Authorization header；若 pairing-required 且 token 缺失，则在本地返回 `BLOCKED_ENVIRONMENT/API_TOKEN_MISSING`，不发 capture 请求。新增 focused tests 2/2 绑定这两个分支；没有真实 capture、用户数据、token 输出或额外 secret 写入。

当前功能候选为 `0325be9af5f65a8a3834d97f66c2c936f066ed6d`，完整树 `39f46b17947a7065070614980d1d8c3d53515e07`、Social Archive 树 `1fc42ac97ca39d288f72c3b7570efb8e9dc000fa`、277 个产品追踪文件清单 SHA-256 为 `f92f8f8d75d1c207000231dabf40e5aac7b5ab8fbb8505a5eeaecc21ff3d2130`。唯一全量应用回归为 `222 passed`（1 条非失败 Starlette/httpx 弃用警告，7.98s）；兼容层 synthetic 验证与兼容任务包 `verify-fast` 为 PASS/26/26，后者以 `--skip-tests` 保证不重复应用套件；结构验证为 PASS 且 `application_suite_rerun=false`。测试时仅 SA-507 evidence/HANDOFF continuation 文件未提交，所有应用源码匹配该候选。

当前候选本地 Docker image `sha256:f353a31f2788a504eb111a9bbc7f4d5c7363ddd38742c75086776ef0a42a99d9` 构建成功，零 Mount 的临时容器在仅本机回环端口上于第 2 次 `/health` 成功；容器和精确 image tag 均已删除。该结果只证明本机当前候选可构建/启动，不是镜像推送、完整生产部署或 release smoke。

严格发布状态仍为 **DEGRADED，不是 PASS**：GitHub token 仅解决 Vault 目标授权，真实 upload 因 `object_count=0` 未产生 Draft/Asset/ciphertext/receipt；生产 R2/OCI endpoint、bucket 与可读 secret 仍未配置，因此不能凭 SA-506 已删除 canary 手工补写前置回执。Social Archive facts ingest/verify、三目标真实恢复、镜像发布和完整部署 smoke 均仍 `NOT_RUN`。没有 GitHub source/tag/release push、Private-Database fact、用户数据上传、完整源码生产部署、timer enablement、额外 worktree 或破坏性回滚。

### Updated resume point (0325be9a)

1. 取得创建并配置专用私有 R2 与 OCI S3-compatible bucket、最小读写/回读（含 list/delete）凭据的即时授权；不得复用其他项目 credential、OCI 单向 PAR 或旧备份密钥。
2. 以当前 pairing token 的生产 0600 secret 和真实核心路径生成无用户数据持久 storage canary，先获得 R2、OCI 的验证回执，再用已安装的 Vault token 取得同一 age ciphertext 的 GitHub Draft readback；只更新环境证据，不重跑全量应用测试。
3. 在权威生产 Private-Database client/auth 下执行 Social Archive facts ingest/strict verify 和三目标恢复；随后发布镜像、执行完整生产部署 smoke。全部真实收据通过后才把 SA-507 收束为 PASS、创建 tag、推送/合并 `main` 并收尾唯一 worktree。若功能源码再变，先产生新候选且只为它运行一次完整回归。

## SA-507 bounded Phase A continuation (2026-07-31 UTC)

本节是对上述 0325be9a 历史快照的当前补充，不修改冻结 v0.0.0.4 任务包，也不把 SA-507 总状态从 **DEGRADED** 改为 PASS。当前功能候选为 `bca021bf91baad3f1585dd6ae15044836752e156`（完整树 `fbb3dff65a2610111ed09a49f7581644b25c897b`、Social Archive 树 `568494a3b7b3cfcc8bad65af1aba16eb08378ed1`、278 个跟踪文件清单 SHA-256 `83a6bc2c1e552b4e0264a6874e9e6b21ffa87028204ee91d9f9fe1d70cab195e`）。它在这一功能候选上唯一一次全量应用回归为 `227 passed`，另有 1 条既有非失败 Starlette/httpx 弃用警告；兼容层验证当前为 PASS，仍精确得出 `PRESERVE_TRANSACTION_CORE_REBUILD_PRODUCT_SHELL_AND_CONNECTORS`、保留单一事务核心且默认回滚仅为 `ROLLBACK_PLAN`。

本阶段发现并以最小变更修复三项生产 P0：CLI 容器显式加入配置的宿主数据组，以便与 Core 共用数据目录而不放宽 secret；`read_secret()` 只接受文档化 `%d` systemd credential 目录内 root:root 只读 credential；配对 API token 仅由请求服务的 Core API 强制要求，离线复制/status 维护单元不再被误阻断。两次对应的新候选完整回归均已分别执行，当前 `bca021bf` 的 227 测试结果是其唯一全量应用套件证据。

生产 Phase A 已闭合：Core loopback `/health` 为 `ok`，status unit `Result=success/ExecMainStatus=0`，generic-web 使用预定义的非用户数据 canary 并留下 runtime receipt，`object-replication` 为 PASS。相同 age-x25519 密文已由 R2、OCI 和私有 Vault GitHub Draft 各自回读验证；公共状态投影显示三处均为 `verified` 且各有 1 个对象。GitHub Draft 仍是 Draft（2 个资产），没有源码、明文用户内容或 Git source Release。生产 `github_token` 只以 `0600 root:root` secret 存在，值从未进入日志、证据或 Git。复制 timer 保持 disabled。

为这次 SSH 恢复创建的 3 个临时容器、专用网络和服务目录已精确删除并在主机复核不存在；对应的 3 个 Coolify service、空 environment 与临时 project 元数据也已通过 UI 删除，项目 URL 返回 404。Docker 的宽范围 image/builder cleanup 被显式取消，未执行。没有增加 worktree、没有 Git source push/tag/release、没有发布镜像、没有启用 timer，也没有进入下一阶段。

正式机器可审计证据在 `evidence/SA-507/PHASE_A_PRODUCTION_20260731.json`。该文件的 scoped `phase_status=PASS` 仅表示生产拓扑与持久三副本 canary；总 SA-507 仍为 **DEGRADED**，因为 Social Archive 的 Private-Database fact `ingest`/严格 `verify`、真实三目标 recovery、以及后续完整生产 release smoke 均尚未运行。状态投影整体 degraded 也仍可能由尚未授权/配置的连接器和目的地造成，不能覆盖 storage 3/3 的已验证事实。

### Resume point after Phase A

1. 先停在此边界；下一次 run 必须只选择一个任务包 phase，并先写新的 Run Contract。
2. 优先候选是 Private-Database 完成态事实与严格回读，或真实三目标恢复；两者不可在同一 run 混做，且不得把现有 canary 代替恢复证据。
3. 只有所有任务包 gate（包括真实恢复、目的地/连接器所需证据及完整部署 smoke）都闭合后，才可把 SA-507 标为 PASS，并按 Owner 的“全包完成后”策略处理 Git source 推送/合并与工作树收尾。

## SA-507 bounded Phase B precheck (2026-08-01 UTC)

本轮只执行 `evidence/SA-507/PHASE_B_PRIVATE_DATABASE_FACTS_RUN_CONTRACT.md` 所定义的 Private-Database 完成态事实同步前置，不进入 backup、restore、复制、Vault Release、timer、部署或 source push。生产首次 `--dry-run` 正确以 `PRIVATE_DATABASE_CLIENT_UNAVAILABLE` fail closed；根因是 `.env` 的标准官方 client 路径没有文件。已从官方 KMOS 工具源安装单一、非 checkout 的 `private_db_client.py`（SHA-256 `8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa`，`root:socialarchive 0550`），保留精确回滚副本；随后 runtime dry-run 为 `READY`，有 1 条完成态待投递事实、0 条已投递。该过程没有 clone 或写入 Private-Database。

为防止未来部署把缺 client 伪装为“准备完成”，`prepare_systemd_host.sh` 现在在任何宿主机写入前要求 `SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT` 是已安装、非符号链接的官方 `private_db_client.py`，并有 focused regression 覆盖。生产脚本已备份后更新，`--dry-run` 通过；同步 service 仍 inactive、timer 仍 disabled。当前本地候选的 focused deployment/sync 回归为 26/26，唯一完整应用回归为 229 passed（1 条既有非失败弃用警告），static/secret/compatibility 均 PASS；兼容结论仍为 `PRESERVE_TRANSACTION_CORE_REBUILD_PRODUCT_SHELL_AND_CONNECTORS`，默认回滚仍只产生 `ROLLBACK_PLAN`。

Phase B **仍是 BLOCKED_OWNER_AUTHENTICATION，不是 PASS**：`private_database_token` 只有 `root:root 0600` 的空占位，GitHub 已在已登录 Owner 会话显示 sudo/passkey 页面。下一步只能由 Owner 完成该 passkey 后创建新的、只限 `LinzeColin/Private-Database`、`Contents read/write` + 必需 `Metadata read-only` 的专用 fine-grained token。严禁复用 Vault-only token、宽权限 local OAuth 或历史暴露 backup PAT。token 写入后，仍只在此 Phase B 内运行一次 `ingest`/strict `verify` 与一次 `NO_CHANGE` 幂等复验，并更新 `PHASE_B_PRIVATE_DATABASE_FACTS_*` 证据；在此之前不得宣称 delivered、不得开始三目标恢复。

## SA-507 bounded Phase B completion (2026-08-01 UTC)

本节取代上一节的“BLOCKED_OWNER_AUTHENTICATION”状态：Owner 完成 GitHub sudo/passkey 后，已创建无过期的 `social-archive-private-db-prod` fine-grained token，唯一仓库为 `LinzeColin/Private-Database`，只有 `Contents: read/write` 和必需的 `Metadata: read-only`，没有 Account permission。token 从 GitHub 一次性展示直接经内存/SSH stdin 写入生产 `private_database_token` source secret；未输出、未写入本机文件、未进入日志，生产元数据为 `root:root 0600`。受限 token 已读回目标为 private；Vault-only token、宽权限 OAuth 与历史暴露 backup PAT 均未使用。

生产 facts sync 首轮为 `PASS`（1 个候选、1 个实际投递、0 个既有投递、无失败）；第二轮为 `NO_CHANGE`（同 1 个候选、1 个既有 delivered）。官方 clone-free verifier 当前报告账本 32 条、27 条常规内容寻址路径、5 条历史全前缀路径；这是已知 legacy verifier 兼容面。实际 sync 仅在其严格 manifest/逐对象 byte+SHA-256 readback 成功后才标记 Outbox delivered，故首轮 `PASS` 是 strict completion 的真实运行证据，而非把官方 legacy 摘要的 5 条缺失文字直接放行。同步 oneshot 最终 inactive/result=success，timer 仍 disabled，临时 verifier unit 已收集为 0。完整脱敏证据见 `evidence/SA-507/PHASE_B_PRIVATE_DATABASE_FACTS_20260801.json`。

Phase B 现为 **PASS**，但总 SA-507 仍为 **DEGRADED，不是 PASS**：真实三目标恢复、完整生产 release/deploy smoke 和其余任务包 gate 还没有执行。本 run 到此为止，严格不混入下一 phase；下一 run 必须在新的 Run Contract 下只选择“真实三目标 recovery”或“完整 release/deploy smoke”之一。继续禁止 Git source push/tag/merge、timer enablement 和宽范围资源清理，直至整个任务包的最终验收完成。

## SA-507 bounded Phase C completion (2026-08-01 UTC)

本轮只执行 `evidence/SA-507/PHASE_C_THREE_TARGET_OBJECT_RECOVERY_RUN_CONTRACT.md` 定义的真实三目标对象恢复，不进入 upload、Release 创建、完整 deployment smoke、timer、source Git 或新的平台 Canary。任务包原本仅有 Private-Database 冷备 `restore.py`，不足以证明“分别从 GitHub、R2、OCI 恢复同一对象”；现增加 `scripts/restore_object.py`，它只读 Runtime SQLite（read-only URI）中的一条完成态 artifact/三份 `verified` 收据，拒绝任一非同密文、非 `age-x25519`、非内容寻址键、错误 GitHub Vault/Draft、非空目标或 Runtime/staging/Private-Database 数据面。R2/OCI 同时验证远端 metadata 与密文 SHA-256；GitHub 必须先验证 private Draft、Pack manifest、每个 asset/对象密文，再取目标密文；三者都以 age 解密并复算明文 SHA-256。

生产 root-only `scripts/restore_object_systemd.sh` 解决了手工 shell 不应读取 source secret 的现实边界：它让 PID 1 只为当前 store 创建 `--wait --collect` transient credential scope，R2/OCI/GitHub 分别最小注入对应 credential，绝不使用 `private_database_token`。早期测试曾因 systemd 展开 `${args[@]}` 而使 CLI 收到空参数；已改为纯位置参数分支，新增 focused regression，且生产 SHA-256 与本地一致。三条 production dry-run 均 `READY`；随后对同一个持久、非用户数据 canary 在三个分别隔离的 private `/tmp` 目标完成实际 `restore`：R2、OCI、GitHub Private Draft 均 `PASS`、均写入目标、均验证同一密文和同一解密后明文哈希。unit 退出后目标在宿主机不可见、transient unit 为 0、复制 timer 仍 disabled；只读后检仍是一个完成对象、三份一致收据。完整脱敏证据为 `evidence/SA-507/PHASE_C_THREE_TARGET_OBJECT_RECOVERY_20260801.json`。

当前功能候选的唯一完整应用回归为 **235 passed**（1 条既有非失败 Starlette/httpx 弃用警告）；聚焦对象恢复为 24 passed，静态/doctor/systemd/brand-secret 通过。Phase C 现为 **PASS**，但总 SA-507 仍为 **DEGRADED，不是 PASS**：下一次必须在新 Run Contract 下只做“完整 production release/deploy smoke 与 SA-507 最终收束”，不混入其他 phase。继续禁止 Git source stage/commit/push/tag/merge、Release 发布、timer enablement、额外 worktree 和宽范围资源清理，直到全部任务包 gate 严格通过。

## SA-507 bounded Phase D completion (2026-08-01 UTC)

本轮只执行 `evidence/SA-507/PHASE_D_PRODUCTION_RELEASE_DEPLOY_SMOKE_RUN_CONTRACT.md`：生产基线确认 Core 仅 loopback、Core/Worker/CLI 三容器健康、Cloudflared 与隔离 status service 运行，两个 storage-dependent timer 仍 disabled。生产目录不是 Git checkout，故部署一致性以 SHA-256 绑定；`compose.yaml`、Dockerfile、Systemd、恢复路径与本地候选一致，仅 `scripts/install.sh` 与 `scripts/doctor.sh` 未包含 Phase B/C 的静态合同。二者已在 root-only 临时 staging 中校验 SHA-256 后原子替换，替换前的两个文件有精确、root-only 回滚副本保留；没有复制 `.env`、runtime、Secret、SQLite、CAS 或用户内容，也没有 Docker build/restart、配对码刷新、timer enablement、provider 写入或 source Git 操作。

生产端 `doctor.sh --self-test`、`install.sh --dry-run`、`prepare_systemd_host.sh --dry-run` 全部 PASS；loopback Core/status health 都为 200。无 Cookie/Bearer/配对码的公网 smoke：UI health 为 Access login 302，独立 extension API health/配对状态为 200，无 Bearer 或伪造 Access assertion 的业务 route 都为 401，status health/脱敏 allowlist JSON 为 200。SA-505 已有经认证控制平面回读的 Access/Tunnel/DNS/WAF/Rate Limit 证据；本轮不读取或复用受保护目录中的任何凭据，也不伪称真实 Owner 浏览器 Access 正向会话。完整脱敏记录是 `evidence/SA-507/PHASE_D_PRODUCTION_RELEASE_DEPLOY_SMOKE_20260801.json`。

Phase D 为 **PASS**，总 SA-507 仍为 **DEGRADED，不是 PASS**：下一独立 phase 只能进行最终 SA-507 证据收束、冻结/结构复验与发布前审计；在它严格通过前继续禁止 source Git stage/commit/tag/push/merge、source Release、timer enablement及宽范围资源清理。该最终 phase 若所有门都 PASS，才按 Owner 已授权顺序发布源码并收尾唯一工作树和本轮临时资源。

## v0.0.0.5 Task Pack execution handoff (2026-08-02)

- Goal: merge the frozen Social Archive v0.0.0.5 candidate into MetaDatabase main without weakening newer upstream behavior.
- Integration base: `963ecd800`; implementation commit: `c7ce42aa91f878aaa751420e70cc3048370d39b1`.
- Semantic task dispositions: satisfied 2, apply 2, adapt 10, equivalent 18, conflict/blocked/obsolete 0.
- Local acceptance: unique full suite `241 passed`; sealed Task Pack `PASS` with 73 candidate tests and 383 manifest hashes; `git diff --check` PASS.
- Preserved stronger upstream: fail-closed pairing/Host rules, destination active-Probe authorization, no-clone Private-Database client, production systemd/Cloudflare/restore surfaces, PWA feed/grid/date/collection/relation history and ZIP import.
- Environment-bound commands: R2, OCI, GitHub Release backup, Private-Database sync, cold backup and real restore stopped fail-closed because local production inputs were absent. No plaintext fallback or remote mutation occurred.
- Product runtime verdict: `NOT_RUN`; do not claim v0.0.0.5 production deployment from this run.
- Evidence: `evidence/v0.0.0.5/VALIDATION_REPORT.json` and `evidence/SA-*/{RESULT,COMMAND_LOG}.json`.
- Next: validate evidence schema, commit/push the evidence commit, merge the PR to main, then run production/provider gates only from an authorized environment with existing secret delivery.
- Preservation correction: pre-final canonical task evidence is retained byte-for-byte under `evidence/SA-*/history/pre-v0.0.0.5-final-evidence/`; see `evidence/v0.0.0.5/PRESERVED_UPSTREAM_EVIDENCE_INDEX.json`.
