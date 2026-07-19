#!/usr/bin/env bash
# OpenD 首次登录(owner 在服务器上运行一次;之后 systemd 常驻不再要验证码)。
#   sudo bash /opt/alpha/MetaDatabase/Alpha/deploy/opend_first_login.sh
# 职责:从 /opt/alpha/env 读登录账号+密码 -> 现算 MD5 写 OpenD.xml(明文不落盘、
# 不回显、不进日志)-> 前台起 OpenD 让 owner 输手机验证码 -> 成功后 Ctrl+C ->
# 本脚本收尾启用 systemd 常驻。红线:本脚本不打印任何秘密。
set -euo pipefail
ENVFILE=/opt/alpha/env
XML=/opt/alpha/opend/OpenD.xml
[ "$(id -u)" = "0" ] || { echo "请用 sudo 运行"; exit 1; }
[ -f "$ENVFILE" ] || { echo "缺 $ENVFILE(先跑 load_env_interactive.sh)"; exit 1; }
[ -x /opt/alpha/opend/OpenD ] || { echo "缺 /opt/alpha/opend/OpenD(OpenD 未安装)"; exit 1; }

get() { grep "^$1=" "$ENVFILE" | head -1 | cut -d= -f2-; }

ACC="$(get MOOMOO_LOGIN_ACCOUNT)"
if [ -z "$ACC" ] || [ "$ACC" = "<REQUIRED>" ]; then
  read -r -p "moomoo 登录账号(牛牛号/手机号/邮箱,手机号带国家码): " ACC
  python3 - "$ENVFILE" "$ACC" <<'PY'
import sys
path, acc = sys.argv[1], sys.argv[2]
txt = open(path, encoding="utf-8").read()
lines = [l for l in txt.splitlines() if not l.startswith("MOOMOO_LOGIN_ACCOUNT=")]
lines.append(f"MOOMOO_LOGIN_ACCOUNT={acc}")
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
  chown alpha:alpha "$ENVFILE"; chmod 600 "$ENVFILE"
fi

PW="$(get MOOMOO_LOGIN_PASSWORD)"
[ -n "$PW" ] && [ "$PW" != "<REQUIRED>" ] || { echo "env 里 MOOMOO_LOGIN_PASSWORD 未填(先跑 load_env_interactive.sh)"; exit 1; }

# 写 OpenD.xml:账号 + 密码MD5(python 内算,不经命令行参数,不回显)
ENVFILE="$ENVFILE" XML="$XML" python3 - <<'PY'
import hashlib, os, re
env = {}
for ln in open(os.environ["ENVFILE"], encoding="utf-8"):
    if "=" in ln and not ln.startswith("#"):
        k, v = ln.rstrip("\n").split("=", 1)
        env[k] = v
xml_path = os.environ["XML"]
xml = open(xml_path, encoding="utf-8").read()
md5 = hashlib.md5(env["MOOMOO_LOGIN_PASSWORD"].encode()).hexdigest()
acc = env["MOOMOO_LOGIN_ACCOUNT"]
xml = re.sub(r"<login_account>.*?</login_account>",
             f"<login_account>{acc}</login_account>", xml, count=1)
# 启用密文行(替换注释模板),移除明文密码行
xml = re.sub(r"<!--\s*<login_pwd_md5>.*?</login_pwd_md5>\s*-->",
             f"<login_pwd_md5>{md5}</login_pwd_md5>", xml, count=1)
if "<login_pwd_md5>" not in xml:  # 模板变体兜底
    xml = xml.replace("</login_account>",
                      f"</login_account>\n\t\t<login_pwd_md5>{md5}</login_pwd_md5>", 1)
xml = re.sub(r"<login_pwd>.*?</login_pwd>", "", xml, count=1)
open(xml_path, "w", encoding="utf-8").write(xml)
print("OpenD.xml 已写入(账号+密码MD5;明文未落盘)")
PY
chown alpha:alpha "$XML"; chmod 600 "$XML"

systemctl stop alpha-opend 2>/dev/null || true
echo ""
echo "==== 现在前台启动 OpenD 做首次登录 ===="
echo "看到提示要验证码时,先看手机短信,然后在下面输入(格式照打):"
echo "    input_phone_verify_code -code=你收到的6位数字"
echo "看到 Login successful / 登录成功 后,按 Ctrl+C 退出前台,脚本会自动收尾。"
echo "========================================"
set +e
sudo -u alpha bash -c 'cd /opt/alpha/opend && ./OpenD -config /opt/alpha/opend/OpenD.xml'
set -e
echo ""
echo ">> 前台退出,转 systemd 常驻:"
systemctl enable alpha-opend >/dev/null 2>&1 || true
systemctl start alpha-opend
sleep 3
systemctl is-active alpha-opend && echo "OPEND_SERVICE_UP" || { echo "OPEND_SERVICE_DOWN(看 journalctl -u alpha-opend)"; exit 2; }
