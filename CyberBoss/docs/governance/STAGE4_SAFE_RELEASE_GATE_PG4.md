# PG-4 Safe Release Gate Card

## 决策

PG-4 只接受一个局部、确定性的 decision：

~~~
stage_4_local_gate = passed
formal_final_acceptance = activation_pending
~~~

该 decision 需要同一冻结 Subject 上的五份已封口 evidence：software correctness、
model safety fixture、security/privacy/supply-chain assurance、fault/restore matrix 和
immutable candidate contract。任何缺项、hash 不一致、未接受 P0/P1 或外部状态伪绿都会
将结果 fail closed。

## Release candidate seal

- candidate release ID：
  bb86be91fedac363301d7704030a67925c166dc826b11f97a0f5cf4222495ad0
- immutable candidate manifest digest：
  4f83d414e4d950506c9430665e2b4875d9ad58e68b2e75bd31c5722dca9a66e4
- operator runbook digest：
  d26533392f38e0de26e1deab4c07a9365cdbc97a5f948503554c1db35afc9c9f
- request-count predicates：8；真实请求数 Canary 不执行
- P0 action：immediate_pointer_restore_no_wait；current 保持不变

candidate/current/previous 在本 Gate 中仍是不可安装的 local fixture slots。没有真实
candidate installation、current switch、DNS、Cloudflare Access、Private-Database、
R2、OCI、Timeline、Status、服务、Canary 或 rollback operation。

## 真相状态

所有真实 provider/data/service 操作与 real model/control-plane/operations LLM calls 为
0。Private-Database、Cloudflare Access/DNS/Analytics、OCI、Timeline、global Status、
self-heal、timer、candidate installation/current switch/live Canary/live rollback 仍为
activation_pending；R2 仍为 hazard_blocked。macOS launchd dependency 为 false。

因此本 Card 不是 production release approval，也不会代替 Owner 的未来外部授权。PG-4
完成后可进入 CB-500 的 clean staging dress rehearsal contract；真实 activation 仍必须由
后续原生节点在获得适当外部 authority 后单独处理。
