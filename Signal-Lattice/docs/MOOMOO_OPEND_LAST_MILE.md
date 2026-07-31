# Moomoo OpenD 最后一公里

Signal Lattice 只使用 Moomoo OpenD 的行情接口，不创建交易上下文、不调用下单接口。

目标环境要求：

- OpenD 与 Signal Lattice 位于同一 OVH 节点或受保护的同主机回环网络；
- `MOOMOO_OPEND_HOST=127.0.0.1`；
- 默认端口 `11111`；
- Build Agent 必须确认市场数据许可并设置 `SIGNAL_LATTICE_MARKET_LICENSE_CONFIRMED=1`；
- 未满足许可、连接、Freshness 或 Point-in-time 门时，系统只能 `SYSTEM_BLOCKED`，不能报告网站可用。

验证命令：

```bash
/opt/signal-lattice/current/venv/bin/python /opt/signal-lattice/current/scripts/verify_moomoo_opend.py
sudo systemctl start signal-lattice-cycle.service
curl -fsS http://127.0.0.1:8787/api/v1/cycles/latest
```
