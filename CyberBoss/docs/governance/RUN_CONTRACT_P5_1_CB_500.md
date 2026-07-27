# P5.1 / CB-500 Run Contract — Clean staging dress rehearsal

## 目标与固定边界

本 Run 只关闭原生节点 CB-500：从干净、可丢弃的本地 staging fixture 复演
immutable candidate、operator runbook、Status/Access/Timeline、故障矩阵、备份/隔离恢复、
request-count predicate 与 rollback contract。它不 promotion、不切换 current、不安装服务，
也不写入 Private-Database、R2、OCI、Cloudflare、DNS、Status 或任何真实 provider。

产品版本固定为 v0.0.0.5，设计基线固定为 v0.0.0.4，TaskPack 固定为
v0.0.0.7，ZIP SHA-256 固定为
77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a。
前置 PG-4 closure 为
a5802bca6ac63c435121ab3bc970a6adededb7de（tree
a505be6c6c5d68090b5cd7eee3742377b7c6cbdf）。

## Skill Router

- Router 在本任务边界返回：CB-500 → webapp-testing，
  NATIVE_IF_PRESENT_ELSE_EMBEDDED，最大轻量 Skill body load 为 1。
- 当前本地 catalog 没有 webapp-testing；依 TaskPack 的冻结 fallback
  machine/skill_microplaybooks.json，只使用已有 HTTP/DOM/unit fixtures 的
  embedded microplaybook，不联网、不安装 browser、不持久化 browser。
- 实际 Skill body load 为 0。未加载 Verifier、Teleiosis、Persona、SubAgent、第二模型或
  动态研究 Skill。

控制面与运维模型调用永久为 0；禁止 macOS launchd、真实时间等待、sleep、soak、凭据等待、
新仓库、submodule、Private-Database clone 与平行事实源。

## Clean-shell rehearsal sequence

operator 只需在已检出的本仓根目录执行下列复制安全命令；每条命令的成功条件由
validate_cb500.py 固定检查，且不要求 shell history、源码阅读、真实凭据或 provider 权限：

1. node app/scripts/dress-rehearsal-suite.js rehearse --mode=local
2. node app/scripts/dress-rehearsal-suite.js rehearse --mode=activation-plan
3. node --test app/test/canonical-dress-rehearsal.test.js
4. node --test tests/dress-rehearsal-suite.test.js
5. node --test app/test/canonical-timeline-projection.test.js app/test/canonical-status-export.test.js app/test/canonical-access-domain.test.js
6. node --test app/test/canonical-backup-runtime.test.js app/test/canonical-fault-recovery-matrix.test.js app/test/canonical-immutable-release.test.js
7. node --test app/test/canonical-sync.test.js app/test/software-correctness-suite.test.js
8. python3 scripts/validate_cb500.py --prepare

演练的顺序固定为：clean slot preflight → immutable candidate → additive migration →
redacted Status → Access loopback → simulator E2E → fault matrix → backup snapshot →
isolated restore → request-count predicates → rollback dry run → staging cleanup。任何 P0、
未记录前置条件、非零 network/provider operation、非零 deployment mutation、非零控制面/运维
模型调用或残留 staging 都必须 fail closed，动作仅为
discard_staging_keep_current。

## Acceptance、证据与 stop condition

本地可验证的 acceptance 为：

- FA-AC-015：frozen core tests PASS；
- FA-AC-018：loss=0、duplicate execution=0 且 rollback/restore valid；
- FA-AC-019：release hashes 固定、previous rollback pointer valid；
- FA-AC-024：所有 local operator commands 按指定 exit code 完成；
- AC-056、AC-067、AC-068、AC-070：缺凭据 fixture 不阻塞本地工作、无隐藏操作、
  可追溯且无 wait/soak。

输出严格限于本仓的 rehearsal card、Run Contract、测试、validator 与
docs/evidence/CB-500/{summary,subject}.json。真实 candidate installation/current switch、
live request-count Canary、live rollback、Private-Database、Cloudflare Access/DNS/Analytics、
Timeline/Global Status、OCI 与 self-heal 均为 activation_pending；R2 为
hazard_blocked。这些 pending/hazard 状态绝不因本地演练而标记 verified。

停止条件是 operator 无法在无源码知识和无隐藏干预下完成、任何输出不可复现、需要不可逆操作却
没有 rollback，或出现外部 authority/凭据需求。回滚只丢弃 staging，保留当前 accepted
release。下一原生节点只能是 CB-510，并必须在其边界重新运行 Skill Router。
