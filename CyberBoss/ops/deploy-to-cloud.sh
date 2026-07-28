#!/usr/bin/env bash
# 把当前提交部署到云服务器。
#
# 沿用服务器上已有的机制，不另起一套：不可变 release 目录 + current 指针移动。
# 新版本先完整落到 releases/<sha>/，装好依赖、自检通过，才移动指针。
# 失败就把指针放回原处并把老版本拉起来——回滚是一次指针移动，不是一次重装。
#
# 用法：
#   ops/deploy-to-cloud.sh            部署当前 HEAD
#   ops/deploy-to-cloud.sh --rollback 回到上一个版本

set -euo pipefail

HOST="${CB_DEPLOY_HOST:-139.99.61.6}"
USER_NAME="${CB_DEPLOY_USER:-ubuntu}"
KEY="${CB_DEPLOY_KEY:-$HOME/Documents/Codex/GithubProject/_protected/alpha_deploy_private/linze_ovh_production_ed25519}"
APP_ROOT="/opt/cyberboss-cloud"
SERVICE="cyberboss-cloud.service"

GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
step() { printf '  %s\n' "$*"; }
die()  { printf '\n%s✗ %s%s\n\n' "$RED" "$*" "$RESET"; exit 1; }

[ -f "$KEY" ] || die "找不到 SSH 私钥：$KEY"
chmod 600 "$KEY" 2>/dev/null || true
SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$USER_NAME@$HOST")

remote() { "${SSH[@]}" "$@"; }

# ── 回滚 ────────────────────────────────────────────────
if [ "${1:-}" = "--rollback" ]; then
  printf '\n正在回滚……\n\n'
  remote "sudo test -L $APP_ROOT/previous" || die "服务器上没有 previous 指针，没得回滚"
  remote "
    set -e
    PREV=\$(readlink -f $APP_ROOT/previous)
    CUR=\$(readlink -f $APP_ROOT/current)
    sudo ln -sfn \"\$CUR\" $APP_ROOT/previous.tmp
    sudo ln -sfn \"\$PREV\" $APP_ROOT/current
    sudo mv -Tf $APP_ROOT/previous.tmp $APP_ROOT/previous
    sudo systemctl restart $SERVICE
  "
  sleep 3
  remote "systemctl is-active $SERVICE" >/dev/null && ok "已回滚，服务在跑" || die "回滚后服务没起来"
  remote "readlink -f $APP_ROOT/current"
  exit 0
fi

# ── 部署 ────────────────────────────────────────────────
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PROJECT="$(pwd)"
SHA="$(git -C "$PROJECT" rev-parse HEAD)"
[ -n "$(git -C "$PROJECT" status --porcelain -- .)" ] \
  && die "工作树有未提交的改动。先提交，否则服务器上跑的东西在仓库里查不到出处"

printf '\n部署 %s 到 %s\n\n' "${SHA:0:12}" "$HOST"

# 1. 打包：只带仓库里跟踪的文件，node_modules 在服务器上重装
step "正在打包……"
TARBALL="$(mktemp -t cbdeploy).tar.gz"
trap 'rm -f "$TARBALL"' EXIT
git -C "$PROJECT" archive --format=tar HEAD . | gzip > "$TARBALL"
ok "打包完成（$(du -h "$TARBALL" | cut -f1)）"

# 2. 上传到暂存区
step "正在上传……"
remote "sudo mkdir -p $APP_ROOT/staging && sudo chown $USER_NAME $APP_ROOT/staging"
scp -q -i "$KEY" -o BatchMode=yes "$TARBALL" "$USER_NAME@$HOST:$APP_ROOT/staging/$SHA.tar.gz"
ok "上传完成"

# 3. 展开成新的 release 并装依赖。这一步做完之前不碰 current。
step "正在安装（第一次装依赖会慢）……"
remote "
  set -e
  DEST=$APP_ROOT/releases/$SHA
  sudo rm -rf \"\$DEST\"
  sudo mkdir -p \"\$DEST\"
  sudo tar -xzf $APP_ROOT/staging/$SHA.tar.gz -C \"\$DEST\"
  sudo rm -f $APP_ROOT/staging/$SHA.tar.gz
  sudo chown -R cyberboss:cyberboss \"\$DEST\"
  sudo -u cyberboss env HOME=/var/lib/cyberboss npm --prefix \"\$DEST/app\" install --omit=dev --silent
" || die "安装失败。current 指针没有动过，线上还是老版本"
ok "新版本已就位（还没切过去）"

# 4. 自检：在新 release 上跑一次语法检查，跑不过就不切
step "正在自检……"
remote "sudo -u cyberboss env HOME=/var/lib/cyberboss npm --prefix $APP_ROOT/releases/$SHA/app run check --silent >/dev/null" \
  || die "新版本自检没过。current 指针没有动过，线上还是老版本"
ok "自检通过"

# 5. 移动指针。previous 记住切换前的那个，回滚就是把它换回来。
step "正在切换到新版本……"
remote "
  set -e
  OLD=\$(readlink -f $APP_ROOT/current || true)
  [ -n \"\$OLD\" ] && sudo ln -sfn \"\$OLD\" $APP_ROOT/previous
  sudo ln -sfn $APP_ROOT/releases/$SHA $APP_ROOT/current
  sudo sed -i \"s|^Environment=CB_RELEASE_ROOT=.*|Environment=CB_RELEASE_ROOT=$APP_ROOT/releases/$SHA|; s|^Environment=CB_EXPECTED_RELEASE_ID=.*|Environment=CB_EXPECTED_RELEASE_ID=$SHA|\" /etc/systemd/system/$SERVICE
  sudo systemctl daemon-reload
  sudo systemctl restart $SERVICE
"
sleep 5

# 6. 真的起来了吗。没起来就自动回滚——不留一个"部署成功但服务是死的"状态。
if remote "systemctl is-active $SERVICE" >/dev/null 2>&1; then
  ok "服务已启动"
else
  printf '\n%s新版本没能启动，正在自动回滚……%s\n' "$RED" "$RESET"
  remote "
    PREV=\$(readlink -f $APP_ROOT/previous)
    sudo ln -sfn \"\$PREV\" $APP_ROOT/current
    sudo systemctl restart $SERVICE
  " || true
  printf '\n最近的日志：\n'
  remote "sudo journalctl -u $SERVICE -n 25 --no-pager" 2>&1 | tail -25
  die "部署失败，已回滚到上一个版本"
fi

printf '\n%s────────────────────────────────────%s\n' "$DIM" "$RESET"
ok "部署完成：${SHA:0:12}"
printf '\n  看日志：  ops/cloud-logs.sh\n'
printf '  回滚：    ops/deploy-to-cloud.sh --rollback\n\n'
