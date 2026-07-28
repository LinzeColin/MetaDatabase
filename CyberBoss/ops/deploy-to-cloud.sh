#!/usr/bin/env bash
# 把当前提交部署到云服务器。
#
# 沿用服务器上已有的机制，不另起一套：不可变 release 目录 + 指针移动。
# 新版本先完整落到 releases/<sha>/，装好依赖、自检通过，才切过去。
# 失败就把绑定放回原处并把老版本拉起来——回滚是一次改写 + 重启，不是一次重装。
#
# ── 为什么绑定不是移动 current 符号链接 ──────────────────────
# systemd 的 ExecStart 脚本读的是 CB_RELEASE_ROOT / CB_EXPECTED_RELEASE_ID
# 这两个环境变量，**不是** current 指针。这两个变量由 /etc/systemd/system/
# cyberboss-cloud.service.d/ 下的 drop-in 提供，主 unit 文件里根本没有这两行。
# 上一版脚本用 sed 去改主 unit 文件，改了个空——于是 current 每次都动，服务却
# 一直在跑几个版本之前的那个 release，而且 systemctl is-active 还是 active，
# 所以每次都"部署成功"。这里改成写一个排在最后的 drop-in（99- 压过所有 90-），
# 并且在重启之后真的去核对进程报出来的 release 号。
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
DROPIN_DIR="/etc/systemd/system/$SERVICE.d"
DROPIN="$DROPIN_DIR/99-cyberboss-live.conf"
STATE_DIR="/var/lib/cyberboss"
PORTAL_PORT="${CB_PORTAL_PORT:-8787}"
NODE="$APP_ROOT/shared/toolchains/bin/node"

GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
step() { printf '  %s\n' "$*"; }
die()  { printf '\n%s✗ %s%s\n\n' "$RED" "$*" "$RESET"; exit 1; }

[ -f "$KEY" ] || die "找不到 SSH 私钥：$KEY"
chmod 600 "$KEY" 2>/dev/null || true
SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$USER_NAME@$HOST")
remote() { "${SSH[@]}" "$@"; }

# 写发布绑定。CB_CHANNEL_ACTIVATION_MODE=required 是让 cloud-supervisor 真的去
# 拉起 bridge：pending 模式下它只打一行 component_pending 然后永远挂起，微信和
# 后台页面一个都不会起来。CYBERBOSS_STATE_DIR 指回 /var/lib/cyberboss，是因为
# 微信账号、两把密钥和运行库都在那里，而 50- 那个 drop-in 把它改到了子目录。
write_binding() {
  local sha="$1"
  remote "
    set -e
    sudo mkdir -p $DROPIN_DIR
    [ -f $DROPIN ] && sudo cp -a $DROPIN $DROPIN.prev || true
    sudo tee $DROPIN >/dev/null <<EOF
[Service]
Environment=CB_RELEASE_ROOT=$APP_ROOT/releases/$sha
Environment=CB_EXPECTED_RELEASE_ID=$sha
Environment=CB_CHANNEL_ACTIVATION_MODE=required
Environment=CYBERBOSS_STATE_DIR=$STATE_DIR
EOF
    sudo systemctl daemon-reload
  "
}

# 真的起来了吗。三件事都得成立才算：服务在跑、进程报出来的 release 号是新的、
# 后台端口真的在应答。少一件都不叫部署成功。
verify_live() {
  local sha="$1" short="${1:0:12}" attempt
  remote "systemctl is-active $SERVICE" >/dev/null 2>&1 || return 1
  # 日志在独立 namespace 里（LogNamespace=cyberboss），不带 --namespace 查不到。
  remote "sudo journalctl --namespace=cyberboss -u $SERVICE --since '-2min' --no-pager 2>/dev/null | grep -q 'release=$short'" || return 1
  for attempt in $(seq 1 30); do
    if remote "curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:$PORTAL_PORT/healthz 2>/dev/null | grep -q '^200$'"; then
      return 0
    fi
    sleep 2
  done
  return 1
}

# ── 回滚 ────────────────────────────────────────────────
if [ "${1:-}" = "--rollback" ]; then
  printf '\n正在回滚……\n\n'
  PREV_SHA="$(remote "basename \$(readlink -f $APP_ROOT/previous)" 2>/dev/null || true)"
  [ -n "$PREV_SHA" ] || die "服务器上没有 previous 指针，没得回滚"
  remote "sudo ln -sfn $APP_ROOT/releases/$PREV_SHA $APP_ROOT/current"
  write_binding "$PREV_SHA"
  remote "sudo systemctl restart $SERVICE"
  if verify_live "$PREV_SHA"; then
    ok "已回滚到 ${PREV_SHA:0:12}，服务在跑，后台在应答"
  else
    printf '\n最近的日志：\n'
    remote "sudo journalctl --namespace=cyberboss -u $SERVICE -n 25 --no-pager" 2>&1 | tail -25
    die "回滚后没能通过验证"
  fi
  exit 0
fi

# ── 部署 ────────────────────────────────────────────────
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PROJECT="$(pwd)"
SHA="$(git -C "$PROJECT" rev-parse HEAD)"
TREE="$(git -C "$PROJECT" rev-parse 'HEAD^{tree}')"
[ -n "$(git -C "$PROJECT" status --porcelain -- .)" ] \
  && die "工作树有未提交的改动。先提交，否则服务器上跑的东西在仓库里查不到出处"

printf '\n部署 %s 到 %s\n\n' "${SHA:0:12}" "$HOST"

OLD_SHA="$(remote "basename \$(readlink -f $APP_ROOT/current)" 2>/dev/null || true)"

# 1. 打包：只带仓库里跟踪的文件，node_modules 在服务器上重装
step "正在打包……"
TARBALL="$(mktemp -t cbdeploy).tar.gz"
trap 'rm -f "$TARBALL"' EXIT
git -C "$PROJECT" archive --format=tar HEAD . | gzip > "$TARBALL"
ARCHIVE_SHA256="$(shasum -a 256 "$TARBALL" | cut -d' ' -f1)"
ok "打包完成（$(du -h "$TARBALL" | cut -f1)）"

# 2. 上传到暂存区
step "正在上传……"
remote "sudo mkdir -p $APP_ROOT/staging && sudo chown $USER_NAME $APP_ROOT/staging"
scp -q -i "$KEY" -o BatchMode=yes "$TARBALL" "$USER_NAME@$HOST:$APP_ROOT/staging/$SHA.tar.gz"
ok "上传完成"

# 3. 展开成新的 release，补齐发布契约，装依赖。这一步做完之前不动绑定。
#
#    release-manifest.json / health-contract.json / process-tree.txt 三个文件
#    是部署期产物，不在仓库里；入口脚本会逐个核对，缺一个就 exit 2。上一版
#    脚本没有生成它们，所以就算绑定改对了，新版本也起不来。
step "正在安装（第一次装依赖会慢）……"
remote "
  set -e
  DEST=$APP_ROOT/releases/$SHA
  sudo rm -rf \"\$DEST\"
  sudo mkdir -p \"\$DEST\"
  sudo tar -xzf $APP_ROOT/staging/$SHA.tar.gz -C \"\$DEST\"
  sudo rm -f $APP_ROOT/staging/$SHA.tar.gz

  # implementation-kit 同样只在服务器上，从当前在跑的那个 release 原样带过来。
  LIVE=\$(readlink -f $APP_ROOT/current || true)
  if [ ! -d \"\$DEST/implementation-kit\" ] && [ -n \"\$LIVE\" ] && [ -d \"\$LIVE/implementation-kit\" ]; then
    sudo cp -a \"\$LIVE/implementation-kit\" \"\$DEST/implementation-kit\"
  fi
  sudo test -x \"\$DEST/implementation-kit/scripts/run-cyberboss.sh\" || { echo NO_ENTRYPOINT; exit 1; }

  # 两个契约文件指回仓库里的定义，和线上现有 release 的做法保持一致。
  sudo ln -sfn docs/product_design/v0.0.0.4/implementation-kit/config/cloud-process-health.json \"\$DEST/health-contract.json\"
  sudo ln -sfn docs/product_design/v0.0.0.4/implementation-kit/config/cloud-process-tree.txt \"\$DEST/process-tree.txt\"

  CODEX_VERSION=\$($APP_ROOT/shared/toolchains/bin/codex --version 2>/dev/null | head -1 || echo unknown)
  AUTH_PRESENT=false
  sudo test -f $STATE_DIR/.codex/auth.json && AUTH_PRESENT=true
  sudo $NODE \"\$DEST/release/write-release-manifest.js\" \
    --release-root \"\$DEST\" \
    --release-commit $SHA \
    --source-tree $TREE \
    --source-archive-sha256 $ARCHIVE_SHA256 \
    --node-version \"\$($NODE -v)\" \
    --codex-version \"\$CODEX_VERSION\" \
    --codex-auth-file-present \"\$AUTH_PRESENT\" >/dev/null

  sudo chown -R cyberboss:cyberboss \"\$DEST\"
  sudo -u cyberboss env HOME=$STATE_DIR npm --prefix \"\$DEST/app\" install --omit=dev --silent
" || die "安装失败。绑定没有动过，线上还是老版本"
ok "新版本已就位（还没切过去）"

# 4. 自检：在新 release 上跑一次语法检查，跑不过就不切
step "正在自检……"
remote "sudo -u cyberboss env HOME=$STATE_DIR npm --prefix $APP_ROOT/releases/$SHA/app run check --silent >/dev/null" \
  || die "新版本自检没过。绑定没有动过，线上还是老版本"
ok "自检通过"

# 5. 切换：改 current 指针（给人看）+ 改绑定（给 systemd 看），然后重启
step "正在切换到新版本……"
[ -n "$OLD_SHA" ] && remote "sudo ln -sfn $APP_ROOT/releases/$OLD_SHA $APP_ROOT/previous" || true
remote "sudo ln -sfn $APP_ROOT/releases/$SHA $APP_ROOT/current"
write_binding "$SHA"
remote "sudo systemctl restart $SERVICE" || true

# 6. 真的起来了吗。没起来就自动回滚——不留一个"部署成功但服务是死的"状态。
step "正在验证（服务在跑 + 版本号对得上 + 后台在应答）……"
if verify_live "$SHA"; then
  ok "验证通过：跑的就是 ${SHA:0:12}，后台端口 $PORTAL_PORT 在应答"
else
  printf '\n%s新版本没能通过验证，正在自动回滚……%s\n' "$RED" "$RESET"
  printf '\n最近的日志：\n'
  remote "sudo journalctl --namespace=cyberboss -u $SERVICE -n 30 --no-pager" 2>&1 | tail -30
  if [ -n "$OLD_SHA" ]; then
    remote "sudo ln -sfn $APP_ROOT/releases/$OLD_SHA $APP_ROOT/current" || true
    write_binding "$OLD_SHA" || true
    remote "sudo systemctl restart $SERVICE" || true
    printf '\n已回滚到 %s\n' "${OLD_SHA:0:12}"
  fi
  die "部署失败"
fi

printf '\n%s────────────────────────────────────%s\n' "$DIM" "$RESET"
ok "部署完成：${SHA:0:12}"
printf '\n  看日志：  ops/cloud-logs.sh\n'
printf '  回滚：    ops/deploy-to-cloud.sh --rollback\n\n'
