# v0.0.0.7 交接 — 2026-08-03

接手前只需读三样：本文件、`09_ROADMAP/TASK_DAG.json`、`evidence/T00/CURRENT_TRUTH.json`。
其余结论都已落在证据文件里，**不要重新调研**。

## 工作位置

```
worktree  ~/Documents/Codex/GithubProject/_scratch/metadatabase-social-archive-v0007
分支      claude/social-archive-v0007  ← origin/main @ 49bbe45c
sparse    .github + social-archive
台账      ~/.claude/goal/sessions/<session_id>.sa-ledger.json
```

主树 `GithubProject/MetaDatabase` 停在 main、0 脏文件，没被污染（铁律 2）。

## DAG 状态

| 任务 | 状态 | 说明 |
|---|---|---|
| T00 | **done** | 证据 `evidence/T00/CURRENT_TRUTH.json` |
| T01 | **done** | 证据 `evidence/T01/MIGRATION_COUNTS.json` |
| T02 | **in_progress** | 制品✓ 测试✓；Acceptance `NOT_RUN`，卡在真实 OAuth 凭据 |
| T03 | **可以开工** | `depends_on` 只有 T00，不受 T02 阻塞 |
| T04–T18 | pending | T04 依赖 T02+T03 |

19 个任务的分类（apply 15 / adapt 4 / conflict 0）在 `CURRENT_TRUTH.json`。

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

干净基线：**288 passed / 11 failed**。这 11 个失败与本轮改动无关，
分属 T03/T04 等后续任务射程。清单在 `evidence/T01/MIGRATION_COUNTS.json`
的 `pre_existing_failures`。

HANDOFF.md 记的「235 passed」已过时。
**不要拿「全绿」当可用判据**——`GOLDEN_TRANSACTION.md` 本来就把它列在
「不能拿来当 PASS 的证据」里。

当前分支：**322 passed / 同样 11 failed**（新增 34 个测试全过，既有一个没弄坏）。

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
T18 部署前必须先 `sqlite3 .backup` 取快照并交给 `scripts/rollback_0007.sh`（已实证可用）。

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
末尾挂 `globalThis.SAMirrorCore`）。引用面**已实测**共 6 处：

| 文件 | 处理 |
|---|---|
| `apps/browser-extension/background.js` | **最难的一块**——它驱动整条扫描编排。删抓取器等于要重写编排层，而替代品（MAIN-world 拦截）属于 T08。建议 T03 只拆到"不再调用 DOM 扫描"，拦截实现留给 T08 |
| `apps/browser-extension/manifest.json` | 从 `content_scripts` 摘掉 |
| `tests/focused/test_extension_account_mirror_core.py` | 整体过时，反转为守卫 |
| `tests/focused/test_v006_account_mirror_contract.py` | 整体过时，反转为守卫 |
| `tests/focused/test_scan_platform_isolation.py` | 需逐函数看，可能有仍有效的覆盖 |
| `tests/focused/test_extension_e2n_contract.py` | 同上 |

**(b) 配对码链路**，散在 6 个文件。服务端侧入口在 `src/social_archive/api.py`：
`/v1/pairing/status`、`/v1/pairing/exchange`、`/v1/pair`、`require_pairing_edge`、
`PAIRING_PATHS` / `PAIRING_BODY_LIMIT_BYTES` / `PAIRING_RATE_LIMIT_PER_MINUTE` /
`PAIRING_STATE_FILENAME`、`_read_pairing_record`、`settings.pairing_code_file`。

**(c) 扩展改长期可撤销令牌**。T01 已经建好 `extension_token` 表
（`token_hash` 唯一、带 `revoked_at`），T02 已经有会话——签发路径可以直接接：
已登录页面向服务端取令牌，经既有 bridge 交给扩展，用户不接触令牌文本。

> 顺序建议：先做 (b) 和 (c)——它们互补（撤掉配对码的同时补上令牌，扩展始终可用），
> 且不依赖 T08。(a) 里 `background.js` 那部分最好与 T08 一起做，否则会出现一个
> "抓取器删了、拦截还没有"的空窗期，扩展在那段时间是装得起来但什么都做不了的。
