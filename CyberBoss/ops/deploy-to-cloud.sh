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
LIVE_ENV="/etc/cyberboss/cyberboss-live.env"
STATE_DIR="/var/lib/cyberboss"
# 注册表校验要求这个值正好是某一个工作区的根目录。服务器上它被设成了**工作区
# 基目录**（少一层），于是 assertAllowedRoot 拒绝，报 workspace_root_not_
# allowlisted。注册表本身只允许一个别名 cyberboss，所以正确值是确定的。写在这
# 里而不是手工改服务器：这一整轮的问题都是"服务器配置漂移、没有任何东西发现"，
# 放进版本控制才不会再漂回去。
WORKSPACE_ROOT="${CB_WORKSPACE_ROOT:-/srv/cyberboss-workspaces/cyberboss}"
PORTAL_PORT="${CB_PORTAL_PORT:-8787}"
# 后台和设置页面对外的地址。用 boss.* 而不是 cyberboss.*：后者前面挂着
# Cloudflare Access，朋友点开设置链接会被拦在一个他登不进去的登录页上。
PUBLIC_ORIGIN="${CB_PUBLIC_ORIGIN:-https://boss.linzezhang.com}"
# 这条隧道是公网唯一入口。它挂了的话，本机 8787 照样 200，公网却什么都打不开
# ——上一次它 dead 了一整天都没人发现，因为 Access 在隧道之前就把请求挡了。
TUNNEL_SERVICE="${CB_TUNNEL_SERVICE:-cyberboss-cf-tunnel.service}"
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
  # 入口脚本会核对 release-manifest.json，没有这个文件的 release 一绑上去服务
  # 就起不来。回滚时尤其要挡：上一次事故就是回滚指向了一个契约不全的 release，
  # 结果"自动回滚"把服务从"跑着旧版本"变成了"彻底起不来"。
  remote "sudo test -f $APP_ROOT/releases/$sha/release-manifest.json" \
    || die "release $sha 缺 release-manifest.json，绑上去只会让服务起不来"
  # 值写在 EnvironmentFile 里，不写成 Environment=。
  #
  # systemd 的规则是「EnvironmentFile 里的设置覆盖 Environment= 的设置」，与
  # 文件排序无关。主 unit 引了 /etc/cyberboss/cyberboss.env，里面有一份旧的
  # CYBERBOSS_WORKSPACE_ROOT；drop-in 50 又引了一份 cb510-state.env，里面有
  # 旧的 CYBERBOSS_STATE_DIR。于是不管这个 drop-in 排在多后面，只要用
  # Environment= 写，这两个值都会被那两个文件悄悄盖掉——而
  # `systemctl show -p Environment` 只打印 Environment= 指令、不展开
  # EnvironmentFile，所以查出来一切正常，实际进程里却是旧值。
  #
  # 换成自己的 EnvironmentFile，并且让它排在最后被引入，才真的覆盖得掉。
  remote "
    set -e
    sudo mkdir -p $DROPIN_DIR
    [ -f $DROPIN ] && sudo cp -a $DROPIN $DROPIN.prev || true
    [ -f $LIVE_ENV ] && sudo cp -a $LIVE_ENV $LIVE_ENV.prev || true
    sudo tee $LIVE_ENV >/dev/null <<EOF
# 由 ops/deploy-to-cloud.sh 生成。这里的值覆盖 /etc/cyberboss/cyberboss.env
# 和各 drop-in 里的同名项——手改会在下一次部署时被覆盖。
CB_RELEASE_ROOT=$APP_ROOT/releases/$sha
CB_EXPECTED_RELEASE_ID=$sha
CB_CHANNEL_ACTIVATION_MODE=required
CYBERBOSS_STATE_DIR=$STATE_DIR
CYBERBOSS_WORKSPACE_ROOT=$WORKSPACE_ROOT
CB_PORTAL_ORIGIN=$PUBLIC_ORIGIN
EOF
    sudo chmod 0644 $LIVE_ENV
    sudo tee $DROPIN >/dev/null <<EOF
[Service]
EnvironmentFile=$LIVE_ENV
# 主人那把 AI 密钥。前几个扫码进来的人共用它，用完席位的人才要自己填。
#
# 密钥一直在 /etc/cyberboss/credentials/deepseek-api-key 躺着，但 unit 里没有
# 这一行，systemd 就不会把它交给进程——loadRuntimeTextSecret 读的是
# \$CREDENTIALS_DIRECTORY，没有 LoadCredential 时那个变量根本不存在。
# 于是"前 5 个人用我的额度"整条路是通的，却没有任何东西可取，每个访客都被
# 推去自己填密钥。文件在 ≠ 进程读得到。
#
# 写在部署脚本里而不是手工改服务器：这一整轮的问题都是"服务器配置漂移、
# 没有任何东西发现"，放进版本控制才不会再漂回去。
LoadCredential=deepseek-api-key:/etc/cyberboss/credentials/deepseek-api-key
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
  local ready=1
  for attempt in $(seq 1 30); do
    if remote "curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:$PORTAL_PORT/healthz 2>/dev/null | grep -q '^200$'"; then
      ready=0
      break
    fi
    sleep 2
  done
  [ "$ready" -eq 0 ] || return 1
  # 隧道必须活着并且开机自启，否则公网入口是空的。
  #
  # 这里必须 restart 而不是 enable --now：隧道的 unit 写了
  # Requires=cyberboss-cloud.service，所以每次部署重启应用，systemd 都会顺带把
  # 隧道停掉；而对一个「已经停了」的 unit，enable --now 不会再把它拉起来。
  # 上一次部署就是这样：应用起得好好的，隧道却是 inactive，公网 530。
  remote "sudo systemctl enable $TUNNEL_SERVICE >/dev/null 2>&1 || true"
  remote "sudo systemctl restart $TUNNEL_SERVICE >/dev/null 2>&1 || true"
  remote "systemctl is-active $TUNNEL_SERVICE" >/dev/null 2>&1 || return 1
  # 最后一关：从这台开发机走公网真的打开后台。本机 200 不代表别人打得开。
  for attempt in $(seq 1 20); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$PUBLIC_ORIGIN/admin")" = "200" ]; then
      return 0
    fi
    sleep 5
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

# 回滚要回到**真正在跑的**那个 release，也就是绑定里写的那个——不是 current
# 指针指的那个。这两者在事故期间可以差好几个版本，照着 current 回滚等于把服务
# 推到一个从来没跑起来过的版本上。
OLD_SHA="$(remote "sudo sed -n 's|^CB_EXPECTED_RELEASE_ID=||p' $LIVE_ENV 2>/dev/null | tail -1" 2>/dev/null || true)"
[ -n "$OLD_SHA" ] || OLD_SHA="$(remote "basename \$(readlink -f $APP_ROOT/current)" 2>/dev/null || true)"
[ -n "$OLD_SHA" ] && step "当前在跑：${OLD_SHA:0:12}"

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

  # 工具链目录只有 root 和 cyberboss 能进，部署账号 ubuntu 直接执行会 Permission
  # denied，于是版本号取到空串，manifest 参数校验再报一个跟真实原因无关的错。
  NODE_VERSION=\$(sudo $NODE -v 2>/dev/null | head -1)
  CODEX_VERSION=\$(sudo $APP_ROOT/shared/toolchains/bin/codex --version 2>/dev/null | head -1)
  [ -n \"\$NODE_VERSION\" ] || { echo NO_NODE_VERSION; exit 1; }
  [ -n \"\$CODEX_VERSION\" ] || CODEX_VERSION=unknown
  # if 而不是 a && b：后者在条件不成立时整条命令返回非零，会被 set -e 当成失败。
  if sudo test -f $STATE_DIR/.codex/auth.json; then AUTH_PRESENT=true; else AUTH_PRESENT=false; fi
  sudo $NODE \"\$DEST/release/write-release-manifest.js\" \
    --release-root \"\$DEST\" \
    --release-commit $SHA \
    --source-tree $TREE \
    --source-archive-sha256 $ARCHIVE_SHA256 \
    --node-version \"\$NODE_VERSION\" \
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
  ok "验证通过：跑的就是 ${SHA:0:12}，公网 $PUBLIC_ORIGIN/admin 打得开"
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

# 7. 清掉旧版本。
#
# 这一步不是洁癖，是这台机器上真正让产品停摆的那件事：每次部署留一份 ~220M，
# 攒到 47 份就是 9.6G，磁盘干到 91%，I/O 全在排队，负载冲到 11（2 核），
# ResourceReadinessGate 判 load_pressure 直接 hold 住所有新任务——用户发消息
# 石沉大海，而每一个组件的自检都是"正常"。
#
# 保留规则：当前这版、回滚要用的上一版、以及最近 KEEP 份。删的都是不可达的
# 旧构建，每一份都能从对应的 git sha 重新构建出来。
KEEP="${CB_KEEP_RELEASES:-5}"
step "正在清理旧版本（保留最近 $KEEP 份 + 当前 + 回滚目标）……"
PRUNED="$(remote "
  cd $APP_ROOT/releases 2>/dev/null || exit 0
  PROTECT=\$(printf '%s\n%s\n' '$SHA' '$OLD_SHA'; ls -1t . | head -$KEEP; \
    grep -rhoE 'releases/[0-9a-f]{40}' /etc/systemd/system/$SERVICE.d/ /etc/cyberboss/ 2>/dev/null | sed 's#releases/##')
  n=0
  for d in \$(ls -1 . | grep -E '^[0-9a-f]{40}\$'); do
    printf '%s\n' \"\$PROTECT\" | grep -qx \"\$d\" && continue
    sudo rm -rf \"./\$d\" && n=\$((n+1))
  done
  printf '%s %s' \"\$n\" \"\$(df -h $APP_ROOT | awk 'NR==2{print \$5}')\"
" 2>/dev/null || true)"
if [ -n "$PRUNED" ]; then
  ok "清掉 ${PRUNED% *} 个旧版本，磁盘现在用了 ${PRUNED#* }"
fi

printf '\n%s────────────────────────────────────%s\n' "$DIM" "$RESET"
ok "部署完成：${SHA:0:12}"
printf '\n  看日志：  ops/cloud-logs.sh\n'
printf '  回滚：    ops/deploy-to-cloud.sh --rollback\n\n'
