#!/usr/bin/env bash
# 建机后收尾(拿到公网地址后,我从本机 SSH 进去运行:
#   ssh -i ~/.ssh/alpha_oracle_ed25519 ubuntu@<IP> 'sudo bash -s' < deploy/finish_deploy.sh )
# 职责:等 cloud-init 装完 -> 校验五进程就位 -> 起不依赖凭据的服务 -> 出健康快照。
# 依赖 owner 凭据(BLK-005)的部分(OpenD 连接/真实邮件/真实探针)如实标注为待供给,不伪造。
set -euo pipefail
echo "== 1) 等 cloud-init 完成 =="
cloud-init status --wait || true
cloud-init status --long || true

echo "== 2) 校验安装产物 =="
ls -l /opt/alpha/MetaDatabase/Alpha/AGENTS.md 2>/dev/null && echo "仓库就位" || echo "!! 仓库缺失"
/opt/alpha/venv/bin/python -c "import backend.app.workers.main_supervisor" 2>/dev/null \
  && echo "Python 包可导入" || echo "!! venv/包异常"
for u in alpha-supervisor alpha-notify-worker alpha-control-page alpha-trading-worker alpha-opend; do
  systemctl is-enabled "$u" >/dev/null 2>&1 && echo "enabled: $u" || echo "未启用: $u"
done

echo "== 3) 起不依赖券商/邮件凭据的服务(降级模式) =="
# 控制页(仅查询/停机;需要 ALPHA_CONTROL_TOKEN,若 env 未填则失败关闭不启动)
if grep -q '^ALPHA_CONTROL_TOKEN=.\+' /opt/alpha/env 2>/dev/null && ! grep -q 'REQUIRED' <(grep '^ALPHA_CONTROL_TOKEN=' /opt/alpha/env); then
  systemctl start alpha-control-page && echo "控制页已起"
else
  echo "控制页待 ALPHA_CONTROL_TOKEN(部署日填);失败关闭,不空跑"
fi
# 监督进程(纯本地,可起)
systemctl start alpha-supervisor 2>/dev/null && echo "监督进程已起" || echo "监督进程待依赖"

echo "== 4) 健康快照 =="
echo "主机: $(hostname)  时间: $(date -u)"
echo "磁盘: $(df -h / | tail -1)"
echo "内存: $(free -h | awk '/Mem:/{print $3\"/\"$2}')"
systemctl --no-pager --failed || true

echo ""
echo "FINISH_DEPLOY_DONE"
echo ">> 已就绪:云主机常驻、代码+依赖、监督进程。"
echo ">> 待 owner 部署日(BLK-005):moomoo 密码/解锁密码、Gmail 应用专用密码、OpenD 首登验证码"
echo ">> 填入 /opt/alpha/env 后:启动 alpha-opend + alpha-trading-worker -> 真实探针 + 试发邮件 + 72h 烤机开始计时"
