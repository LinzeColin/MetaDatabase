#!/usr/bin/env bash
# BLK-005 部署日凭据装载(owner 亲自在服务器上运行,交互式)。
#   ssh ubuntu@HOST      # owner 自己登录
#   sudo bash /opt/alpha/MetaDatabase/Alpha/deploy/load_env_interactive.sh
# 红线:秘密用静默输入(read -s),只写 /opt/alpha/env(600, 属主 alpha);
#   绝不回显、绝不写日志、绝不进 Git;Claude 全程不经手这些值。
# 幂等:可重复运行覆盖;留空=保持原值不动。
set -euo pipefail
ENVFILE=/opt/alpha/env
[ -f "$ENVFILE" ] || { echo "缺 $ENVFILE(先跑 bootstrap_primary.sh)"; exit 1; }
[ "$(id -u)" = "0" ] || { echo "请用 sudo 运行"; exit 1; }

echo "=== Alpha 凭据装载(输入不回显;直接回车=不改该项)==="
read -rs -p "1/6 moomoo 账户号 acc_id: " V_ACC; echo
read -rs -p "2/6 moomoo 登录密码: " V_LOGIN; echo
read -rs -p "3/6 moomoo 交易解锁密码: " V_UNLOCK; echo
read -rs -p "4/6 发件 Gmail 地址: " V_GMAIL; echo
read -rs -p "5/6 Gmail 应用专用密码(16位): " V_APPPW; echo
read -rs -p "6/6 邮件指令令牌(自拟随机串,收指令邮件用): " V_IMAPTOK; echo
export V_ACC V_LOGIN V_UNLOCK V_GMAIL V_APPPW V_IMAPTOK

# 用 Python 安全改写(避免密码含 / & 等破坏 sed);只改非空项。
V_ACC="$V_ACC" V_LOGIN="$V_LOGIN" V_UNLOCK="$V_UNLOCK" V_GMAIL="$V_GMAIL" \
V_APPPW="$V_APPPW" V_IMAPTOK="$V_IMAPTOK" python3 - "$ENVFILE" <<'PY'
import os, sys
path = sys.argv[1]
m = {
    "ALPHA_EXPECTED_ACC_ID": os.environ.get("V_ACC", ""),
    "MOOMOO_LOGIN_PASSWORD": os.environ.get("V_LOGIN", ""),
    "MOOMOO_UNLOCK_PASSWORD": os.environ.get("V_UNLOCK", ""),
    "ALPHA_SMTP_USERNAME": os.environ.get("V_GMAIL", ""),
    "ALPHA_SMTP_APP_PASSWORD": os.environ.get("V_APPPW", ""),
    "ALPHA_IMAP_COMMAND_TOKEN": os.environ.get("V_IMAPTOK", ""),
}
lines = open(path, encoding="utf-8").read().splitlines()
seen = set()
out = []
for ln in lines:
    hit = False
    for k, v in m.items():
        if ln.startswith(k + "=") and v.strip():   # 留空不动
            out.append(f"{k}={v}")
            seen.add(k); hit = True; break
    if not hit:
        out.append(ln)
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
changed = ",".join(sorted(seen)) or "(无改动)"
# 只报改了哪些键,绝不打印值
print("已更新键:", changed)
PY

chown alpha:alpha "$ENVFILE"; chmod 600 "$ENVFILE"
REMAIN=$(grep -c "<REQUIRED>" "$ENVFILE" || true)
echo ">> env 权限 600 属主 alpha;仍含 <REQUIRED> 占位行数: $REMAIN"
echo ">> 下一步(仍由 owner 决定时机):"
echo "   1) OpenD 首次登录(手机验证码)-> systemctl start alpha-opend"
echo "   2) 起交易/通知/影子: systemctl start alpha-trading-worker alpha-notify-worker"
echo "   3) 验收: /opt/alpha/venv/bin/python -m scripts.probe_real_machine(真实探针)+ 收测试邮件"
echo "   4) 预签实盘授权文件另置 /opt/alpha/runtime/LIVE_AUTHORIZATION.json(080 才需)"
echo ">> LIVE_TRADING_ENABLED 保持 0;十一门禁未全过前系统只会 SIMULATE。"
