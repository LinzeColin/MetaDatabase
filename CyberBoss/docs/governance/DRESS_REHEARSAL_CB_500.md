# CB-500 Clean Staging Dress Rehearsal Card

本 card 是一个 clean, isolated, local deterministic rehearsal receipt 的解释卡；它不是
真实 production promotion、Cloudflare Access/DNS、Private-Database、R2/OCI、Timeline、
Global Status、服务安装或 live Canary 的声明。

| Rehearsal surface | Local evidence and expected result |
| --- | --- |
| staging | 每次由临时空目录创建 candidate/status/restore/receipts 四个受限子目录，再在同一进程内彻底删除；无 persistent installation、无 current switch |
| candidate / rollback | CB-440 candidate ID bb86be91… 与 manifest digest 4f83d414… 不变；P0 为 discard_staging_keep_current，rollback pointer 是 previous |
| operator | 8 条既有 command contract 可复制、安全、无隐藏 prerequisite；operator corrections 为 []，无源码知识要求 |
| Status / Access / Timeline | redacted Status、deny-by-default Access loopback、canonical Timeline unit fixtures 均由 credential-free validator 复跑；真实公开面仍 activation_pending |
| E2E / fault | simulator-only path 与 14-case fault matrix 复跑；lost messages、duplicate execution、duplicate side effects、unbounded retries 均为 0 |
| backup / restore | 本地 online snapshot、R2/OCI simulator 和 network-disabled isolated restore 复跑；真实 R2 仍 hazard_blocked，OCI 仍 activation_pending |
| canary | 8 条 frozen request-count predicates 已在 local candidate contract 复验；live request-count Canary 为 activation_pending |
| activation plan | 9 个 authority-bound external operations 只形成 ordered plan；没有实际 provider call、service install、DNS mutation 或 current switch |

## Fixed local go/no-go

    local_rehearsal = go_local_only
    production_promotion = activation_pending
    real_external_activation = activation_pending

所有 rehearsal step 都必须同时满足 copy_safe=true、source_code_knowledge_required=false、
undocumented_prerequisites=0，且 network/provider operations、deployment mutations、
control-plane LLM calls、operations LLM calls、real-time waits 均为 0。没有 macOS
launchd dependency。

## Operator corrections and external truth

本次 deterministic rehearsal 的 operator corrections 为 []。如果未来真实 activation
发现缺失 authority、DNS/Access 对象、Private-Database receipt、R2/OCI receipt、Status
endpoint 或可逆 rollback 证据，必须将该项保持为 activation_pending 或
hazard_blocked，修订 runbook 后重新执行相应原生节点；不得把本卡替换为外部事实源。

本 card 同时绑定 FA-AC-015、FA-AC-018、FA-AC-019、FA-AC-024 及
AC-056、AC-067、AC-068、AC-070 的本地可执行部分。真实激活留给后续
CB-510、CB-520、CB-530 与 CB-540 的独立证据，且每个任务边界重新运行
TaskPack Skill Router。
