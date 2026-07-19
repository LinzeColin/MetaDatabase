# 第 3 步激活手册:模拟盘(070 Paper+Shadow)开跑所需的 15 分钟

**前提**:主节点已 bootstrap、72h 烤机已完成(第 2 步)。本手册只做「填凭据 → 起数据线 → 起模拟盘」,
全程 owner 在服务器上亲自操作敏感值,Claude 只引导不经手。

## 为什么这一步必须 owner 在场
契约 `specs/MOOMOO_ADAPTER_CONTRACT.md`:模拟盘 = Moomoo **SIMULATE** 交易环境,必须经
OpenD 网关连真实券商会话;`ISSUE_QUEUE` 070 目标写明「**真实行情下** 3 个交易日」。
故 3 日模拟盘无法用免费日线替代,必须先有券商登录。此为设计约束,非工程缺口。

## 步骤(约 15 分钟)

1. **owner SSH 登录服务器**(用部署 key),**先拉最新代码**:
   ```
   sudo -u alpha bash -c 'cd /opt/alpha/MetaDatabase && git pull --ff-only'
   ```

2. **装凭据**(交互、静默输入,值不回显/不落日志):
   ```
   sudo bash /opt/alpha/MetaDatabase/Alpha/deploy/load_env_interactive.sh
   ```
   依次输入:moomoo acc_id、登录密码、解锁密码、发件 Gmail、Gmail 应用专用密码、邮件指令令牌。

3. **放 OpenD 的 RSA 私钥**到 `/opt/alpha/opend_rsa_private.pem`(权限 600,属主 alpha),
   与 moomoo 后台登记的公钥配对。

4. **起 OpenD 并首次登录**(手机验证码):
   ```
   sudo systemctl start alpha-opend
   sudo journalctl -u alpha-opend -f     # 按提示输入验证码
   ```

5. **起数据线三进程**:
   ```
   sudo systemctl start alpha-trading-worker alpha-notify-worker
   sudo systemctl status alpha-opend alpha-trading-worker alpha-notify-worker --no-pager
   ```

6. **三连验收**(Claude 引导执行):
   - 真实探针:`sudo -u alpha /opt/alpha/venv/bin/python -m scripts.probe_real_machine`
     → OpenD 连接/行情/账户三状态 + 辖区探针正常;
   - 手机收到一封测试邮件(通知链路通);
   - 控制页(经 SSH 隧道)能查状态、能停机/恢复一次。

## 之后(自动,owner 只收邮件)
- 070 连续跑 3 个合格美股交易日 Paper(SIMULATE)+ Shadow,按 `REPORT_TEMPLATE_3DAY.md` 出报告;
- `strategy_promotion.yaml` 四条自动判定:全绿→校验预签授权→进 080 首个 MICRO_LIVE 真实订单;
  任一红→邮件说明原因→回 050 网格内零成本调参重跑。

## 安全不变量(任何时候)
- `LIVE_TRADING_ENABLED` 保持 0;十一门禁未全过前系统只会 SIMULATE,不触真实订单;
- 秘密只在 `/opt/alpha/env`(600)与 `opend_rsa_private.pem`(600),永不进 Git/日志;
- 080 首个真实订单前,owner 另需预签 `/opt/alpha/runtime/LIVE_AUTHORIZATION.json`。
