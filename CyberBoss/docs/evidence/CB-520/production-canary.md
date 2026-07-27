# CB-520 Production Canary

- 精确 current release：`bb5a201a0aec38117a7e14f470662b6f45bd49c7`；保留的
  `previous`：`82b47668c33cc403fee9194ad42b77e49c8b7da3`。两者都有不可变
  manifest，产品版本均为 `v0.0.0.5`。
- 有限只读/拒绝集合通过：loopback health 与 Timeline 返回 200；受保护 Status 的
  授权读取返回 200、匿名读取返回 401；公网路径返回 Cloudflare Access challenge 302；
  `readyz=503` 正确表示真实 WeChat channel 仍 pending，而非伪绿。
- Release-code canary 覆盖允许只读、未授权拒绝、32 KiB+1 oversize 拒绝和 `/stop`
  的已绑定 turn 取消语义；它没有启动 Runtime turn、Provider、simulator 或模型。
- 真正执行了 `current → previous → current` 指针切换和三次受控 service start；每个
  release 都在切换后通过 loopback Status/Timeline predicate。spool 与 canonical
  状态保留。
- 受控 app switch 会停止其专用 tunnel unit；同一 Run 已确定性重启并验证该既有、
  enabled 的 tunnel，随后刷新全局 Status。其自动联动强化留给后续 CB-540，不将该
  运行事实写成已完成的自愈功能。
- 真实 WeChat credential 仍缺失，真实 channel delivery 明确保持
  `pending_missing_real_wechat_credential`；这不被当作 E2E 成功。
