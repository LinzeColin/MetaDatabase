# MooMooAU 当前交接

更新时间：2026-07-26（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0705，并停止在 T0706 前。
- 未创建新任务包；继续使用当前 `1.0.34` 控制包与不可变前序。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_GA_PASS_SCHEDULE_ENABLED_T0705_COMPLETE`。
- T0705 protected schedule-mode rehearsal 已在 exact main、attempt 1、rerun 0 下 PASS。
- T0705/S7AC-005 已闭合；final Acceptance、Stage 7 完成和最终发布未声明。

## 已冻结前序

- T0702、T0703、T0704 protected PASS receipts 和全部失败账本保持不变。
- 所有 T0705 失败 exact-main head 与两个 pre-Secret 失败 head 均只执行 attempt 1、rerun 0；
  永不得 rerun/redispatch。
- 最新失败曾越过 canonical Raw/Processed recovery 与 Timeline snapshot commit，停止于
  `TIMELINE_SNAPSHOT_RECOVERY`；公开输出不证明精确 exception。
- 确定性 fixture 独立证明：immutable append 可接受的合法对象可能超过 current pointer 的
  2 MiB 上限。修复后 immutable recovery 使用独立 64 MiB bound，current pointer 仍为 2 MiB，
  response SHA、size、age envelope 与 canonical Git blob SHA 校验不变。

## T0705 PASS 与日常运行

- protected rehearsal 公开桶化结果：verified/recovered 为 `TEN_PLUS`，source mutation 为
  `ONE`，remote recovery 100%，Full Reconcile 为首次导入 `NOT_COMPARABLE`，Timeline 1，
  checkpoint recovery PASS，collateral/duplicate/unresolved 为 0。
- Gmail label confirmation 固定 `fields=id,labelIds`；不确定 Trash response 只允许一次只读
  label reconciliation，mutation retry 为 0。
- 日常 workflow 只接受 `schedule` event，目标 `04:30 Australia/Sydney`；repository variable
  为 true 时进入现有 `moomooau-beta` Environment。
- 日常运行复用八个精确 Secret 名称，配置只在内存派生；Identity 只进入 `/dev/shm`，结束后清理。
- 日常安全与规划均使用 live UTC；无历史 fixture、无手工审批、无 Codex Automation。

## 当前安全边界与下一步

- one-shot rehearsal authority 必须保持不存在；日常只保留 schedule enablement variable。
- T0705 无 routine 手工动作；schedule 失败不在同一 run 内无限重试，下一次运行依靠 checkpoint
  与幂等恢复补偿。
- 不使用真实时间 Soak、观察期、等待窗口、后台空转或全量测试作为开发前置。
- 不进入 T0706，不创建 Codex Automation，不运行 Recovery Drill/Patch Lifecycle，不做最终发布。
