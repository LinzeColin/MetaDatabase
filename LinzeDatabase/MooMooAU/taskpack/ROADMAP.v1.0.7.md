# MooMooAU Archive Roadmap v1.0.7

## 当前结论

T0702 protected Raw-only Beta 已通过并满足 M3 前序。v1.0.7 已补齐此前缺失的独立 protected M3
Budget-1 云端入口，但当前 Run Contract 仍明确 `m3_authorized=false`；因此只证明本地机制可执行且
默认关闭，不证明 T0703 protected Oracle、生产或最终 Acceptance。

## 已完成

- 冻结 v1.0.6 直接前序，不改变 34 RQ、34 AC、58-task DAG、Kill Criteria 或产品不变量；
- 独立 M3 protected bootstrap：
  - exact eight-Secret allowlist；
  - GitHub App 单私有仓装配；
  - Gmail metadata verification → verified Raw → Processed complete/safe-deferred；
  - Raw + Processed remote decrypt/digest recovery；
  - 第二次 sender verification；
  - `users.messages.trash` exact message、Budget 1、确认后聚合输出；
  - Timeline/schedule/Blue-Green/GA 不可达；
- main-only protected workflow：
  - owner/actor、repository numeric identity、exact SHA、GitHub-hosted、attempt 1；
  - T0702 PASS receipt SHA-256 与同树 M3 gate SHA-256；
  - 当前 authority false 时在 Secret 读取前关闭；
  - 无 cache、artifact、自托管 runner、控制仓写权限或 `git push`；
- 合成装配验证：
  - Processed recovery 先于 exact Trash；
  - age ciphertext-only private objects；
  - Gmail collateral mutation 0；
  - tmpfs identity 与 credential cleanup；
  - 公开结果只含 buckets/布尔门，不含 message/thread/sender/subject/private locator。

## 未完成且未声称

- T0703 protected M3 first attempt；
- 真实 Processed private writes 与 exact Gmail Trash；
- T0704 Blue-Green/Timeline protected run；
- T0705 真实 04:30 Australia/Sydney GA；
- T0706 owner-created passive Codex Automation；
- T0707 real Recovery Key drill；
- T0708 protected patch lifecycle；
- 34 项最终 Acceptance、整体复审、复审修复与最终一次性 GitHub 发布。

## 后续严格顺序

1. 新的明确 T0703 Run Contract 授权唯一一次 Budget-1 protected first attempt；
2. exact-main 本地/CI/包/Secret/发布门全部通过后，才配置 `moomooau-m3` 并 dispatch；
3. 从公开安全 run receipt 与只读远端恢复核验生成 T0703 证据；任何失败都令 M3 再次关闭；
4. T0703 PASS 后，按 DAG 逐一补齐 T0704、T0705、T0706、T0707、T0708，不使用固定自然日等待；
5. 整体任务包完成后才执行整体复审、修复复审问题与最终一次性 GitHub 上传。
