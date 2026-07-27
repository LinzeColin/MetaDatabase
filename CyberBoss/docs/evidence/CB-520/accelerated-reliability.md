# CB-520 Accelerated Reliability Receipt

本 Run 使用有限请求数而非真实时间观察：完整本地 App regression 与新增 CB-520 focused
tests 均以退出码 0 通过；目标 release 运行同一无网络 release-code canary。生产侧
执行的有限闭环为：candidate promotion、已验证 previous rollback、candidate restore，
每次均以 systemd 状态、loopback HTTP predicate 和受保护 Status snapshot 判定。

控制面与运维模型调用均为 0；没有真实 Codex turn、WeChat adapter dispatch、simulator、
固定 sleep 或时间 soak。若切换 predicate 失败，控制脚本会停止 intake、恢复已验证
previous 并保留 spool/证据；本次最终没有 P0 数据、重复副作用或 release 不一致。

R2/OCI restore 仍属于 CB-530，Analytics 与 tunnel 联动自愈仍属于 CB-540；本 receipt
不提前声明它们已激活。
