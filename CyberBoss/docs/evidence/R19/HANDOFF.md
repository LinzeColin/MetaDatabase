# R19 交接（CB-840 的交接部分；PG-8 未密封）

CB-840 由「交接」与「exact Subject 密封 + PG-8 出口闸门」两半组成。前者可以现在
完成并交付，后者依赖 CB-830 的四项外部输入，未做也不得做。本文只是前者。

## Exact Subject

| 项 | 值 |
|---|---|
| 仓库 | `LinzeColin/MetaDatabase`，子树 `CyberBoss/` |
| 分支 | `claude/cyberboss-v0-0-0-8-taskpack-fc4d1f` |
| 工作树 | `~/Documents/Codex/MetaDatabase/cyberboss-v0-0-0-8-taskpack-fc4d1f` |
| 任务包 | `CyberBoss_v0.0.0.8_SEALED_TASKPACK_FINAL_R19_SHARED_BOT_DEEPSEEK_V4_PRO_20260728` |
| 生产主机 | OVH `139.99.61.6`（`vps-83b882b4`），服务 `cyberboss-cloud.service`，隧道 `cyberboss-cf-tunnel.service` |
| 公网后台 | `https://boss.linzezhang.com/admin`（无主人时免令牌） |
| 目标树套件 | **661/661 通过** |

## 本轮闭环状态

| 节点 | 状态 | 证据 |
|---|---|---|
| CB-600 | 闭环 | `CB-600.json`、两份探针原始 JSON、`docs/r19/ADAPTATION_PLAN.md` |
| CB-610 | 闭环 | `CB-610.json`；`008` 迁移在生产库副本上验证 |
| CB-620 | 闭环 | `CB-620/STATUS.json`、`CB-620/browser_public_scan_report.json` |
| CB-630 | 闭环 | `CB-630.json` |
| CB-640 | 闭环 | `CB-640.json`；Blind Set 8 条真跑 |
| CB-700 | 仅代码路径 | `CB-700.json`；无真实 DeepSeek 调用 |
| CB-710/720/730/740 | 闭环 | 四份同名 JSON；PG-7 标 NOT_SEALED |
| CB-800 | 仅代码路径 | `CB-800.json`；R2 写权限缺失 |
| CB-810/820 | 闭环 | 两份同名 JSON |
| CB-830 | 部分 | `CB-830.json`；9 条验收完成 5 条 |
| CB-840 | 交接完成，密封未做 | 本文 + `CB-840.json` |

四项阻塞的查证过程见 `BLOCKERS-VERIFIED.json`——那不是断言，是搜过之后的结论。

## 解除阻塞后的续作程序

**给到 DeepSeek 密钥后**（不要贴进仓库或聊天记录，直接放到服务器）：

```bash
printf '%s' '<KEY>' | sudo tee /etc/cyberboss/credentials/deepseek-api-key >/dev/null
sudo chmod 600 /etc/cyberboss/credentials/deepseek-api-key
sudo chown cyberboss:cyberboss /etc/cyberboss/credentials/deepseek-api-key
```

随后即可推进 CB-700 的真实调用与 CB-830 的 DeepSeek E2E、Canary。
`loadRuntimeTextSecret` 会优先读 systemd credential，密钥不进环境变量、不进日志。

**给到 R2 写权限后**：在 Cloudflare R2 面板为 `cyberboss-cold` 生成一对 S3
Access Key / Secret（不是 API token——已验证 API token 换算出来的凭据对该桶只有
读权限，PUT 返回 403 AccessDenied 而非 SignatureDoesNotMatch，说明签名实现本身
是对的）。填入后 CB-800 的双副本收据与 CB-830 的备份收据即可闭环。

**Owner 的 iLink 授权**：在受保护的 `/ops/wechat` 路由扫一次授权二维码。这是 R19
规定的唯一激活方式；本轮之前自创的「主人认领码 / 10 分钟绑定窗口」已按 R19 判为
obsolete，不要再用。

**五位真实用户**：五人分别加共享 Bot 并发送「开始」；第六人必须在 DeepSeek 调用
**之前**被拒绝，这条是 AC-039 的硬要求。

## 接手前必须知道的三件事

**一、真实链路只有一条。** 消息路径是
`bin/cyberboss.js → app/scripts/cloud-supervisor.js → durable inbox → job scheduler
→ dispatchDurableRuntimeJob`。本轮反复出现「测试全绿但那段代码在真实链路上从未被
执行」——四次。改任何东西之前，先确认它在这条链上可达。

**二、还有一个已知未修的缺口。** 非主人的消息无法在建 job 之前分流：JobScheduler
要求 `dispatchRuntime` 返回真实的 `threadId`/`turnId`，所以普通用户、入门回复、状态
这三条路必须在 `DurableInboxCoordinator` 建 job **之前**就分流掉，而
`app/src/services/inbox/durable-inbox.js` 目前没有这个钩子。这条直接卡住 R19 的
席位语义（第六人要在 DeepSeek 调用前被拒绝）。

**三、overlay 的命名空间需要路径适配。** `apply_overlay.py` 把 155 个文件装进
`v8-prebuilt/` 子树但不改写文件内部按 starter_kit 布局写死的相对路径。本轮的处理
是只重写「指向 overlay 之外」的引用，内部兄弟引用一律不动。重新应用 overlay 时要
重做这一步，见 `CB-620/STATUS.json` 的 `namespace_adaptation` 段。

## 回滚

生产回滚已实测四步（`b555aece → 371cd78d → 回滚 → 再前滚`，公网全程 200）：

```bash
CyberBoss/ops/deploy-to-cloud.sh --rollback
```

回滚只改写 `/etc/cyberboss/cyberboss-live.env` 里的 `CB_RELEASE_ROOT` 与
`CB_EXPECTED_RELEASE_ID` 并重启，旧 release 目录一个字节不动。

## 未声称

PG-6、PG-7、PG-8 均未密封；共享 Bot 未激活；无任何一次真实 DeepSeek 调用；
双副本备份收据不存在；五席位未对真实用户验证。以上任何一项都不得由本文或任何
证据文件的存在推定为已完成。
