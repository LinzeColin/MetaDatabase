#!/usr/bin/env bash
# 从开发机把本工作树部署到生产（v0.0.0.7）。
#
# ## 为什么要有这个脚本
#
# 在它之前，每次部署都是现敲的一串 ssh 命令。2026-08-04 那次就是这么塌的：
# 为了让 rsync 写得进去，我随手敲了
#
#     sudo chown -R ubuntu:ubuntu /opt/social-archive
#
# 它把 runtime/secrets/ 下每个密钥的属组从 **10001**（socialarchive-secrets）
# 改成了 1000。容器里的 Core 跑在 uid 10001，密钥是 0640——属组一变，
# 它就再也读不到 /run/secrets/social_archive_api_token。
#
# **而 /health 全程 200。** 健康检查不读密钥，所以容器一直"健康"，
# 每一条要鉴权的业务路由却全是 500。这正是 prepare_systemd_host.sh 第 205 行
# 早就写下的那句话：「只给前者，容器 /health 照样 200 而业务路由一律 401，
# 界面永远『同步中』」。我读过那句话，然后还是踩了同一个坑——
# 因为部署路径没被固化下来，那条经验只存在于注释里，拦不住现敲的命令。
#
# ## 这个脚本守住的四件事
#
#   1. **不做任何递归 chown。** 属主问题用 sudo 定点解决，不用大扫除。
#   2. **部署前后各量一次密钥不变量**（uid:gid:mode），漂了就大声说。
#   3. **上线前先给正在跑的镜像打 :rollback 标签**，不占额外磁盘（同一批层）。
#   4. **验收打的是要鉴权的路由，不是 /health。** 上面那 10 分钟就是被
#      /health 的 200 骗过去的。
#
# 用法：bash scripts/deploy_to_production.sh [--host linze-ovh] [--dry-run]

set -euo pipefail

HOST="${SOCIAL_ARCHIVE_DEPLOY_HOST:-linze-ovh}"
REMOTE_DIR="${SOCIAL_ARCHIVE_DEPLOY_DIR:-/opt/social-archive}"
DRY_RUN=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --dir) REMOTE_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) printf '未知参数：%s\n' "$1" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d '[:space:]' < VERSION)"
IMAGE="social-archive/core:${VERSION}"

fail() { printf '\n部署中止：%s\n' "$1" >&2; exit 1; }
step() { printf '\n=== %s ===\n' "$1"; }

# 容器挂进 /run/secrets/ 的密钥。属组必须是 10001（socialarchive-secrets），
# 否则 Core（uid 10001）读不到——见文件头。
MOUNTED_SECRETS=(
  social_archive_api_token cli_worker_token
  google_oauth_client_secret github_oauth_client_secret credential_age_identity
  github_markdown_token notion_token obsidian_rest_token
  karakeep_api_token linkwarden_api_token x_oauth_token reddit_oauth_token
)

# **每一处都要 sudo。** runtime/secrets 是 0700 且属主 10001，
# 部署账号（ubuntu）连 `test -e` 都做不到——第一版没加 sudo，于是十二个密钥
# 全被报成「缺失」。那次它**失败在安全的一侧**（中止部署），但一个总是喊狼来了
# 的判据用不了几次就会被人绕过去，等于没有。
secret_fingerprint() {
  ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && for f in ${MOUNTED_SECRETS[*]}; do
    if sudo test -e runtime/secrets/\$f; then
      printf '%s %s:%s %s\n' \"\$f\" \"\$(sudo stat -c %u runtime/secrets/\$f)\" \"\$(sudo stat -c %g runtime/secrets/\$f)\" \"\$(sudo stat -c %a runtime/secrets/\$f)\"
    else printf '%s 缺失\n' \"\$f\"; fi
  done"
}

step "0) 本地闸门：工作树干净 + 发布门全绿"
[[ -z "$(git status --porcelain)" ]] || fail '本工作树有未提交改动。部署的必须是已入库的那一版，否则生产上跑的东西没有对应的提交。'
.venv/bin/python scripts/final_verify.py >/dev/null || fail '发布门未通过。'
.venv/bin/python scripts/build_extension_package.py >/dev/null || fail '扩展包没打出来——用户下载到的会是旧版本。'
printf '  工作树干净；发布门通过；扩展包已重打。\n'

step "1) 部署前量一次密钥不变量"
BEFORE="$(secret_fingerprint)"
printf '%s\n' "$BEFORE" | sed 's/^/  /'
if printf '%s\n' "$BEFORE" | grep -qv ':10001 '; then
  printf '%s\n' "$BEFORE" | grep -v ':10001 ' | sed 's/^/  异常：/'
  fail '有密钥的属组不是 10001（socialarchive-secrets）。先修好再部署——带着这个状态上线，/health 会是 200 而所有业务路由 500。'
fi
# **属组对了还不够，权限位也要给组。**
#
# 2026-08-04 实测抓到的：instagram_session 的属组是对的（10001），
# 而权限是 **0600**——组权限为零。cli-tools 跑在 uid 10002 / gid 10001，
# 于是它读不到自己的密钥，Instagram 从来就没能工作过。
# 只查属组的话，这个文件在上面那一关是"合格"的。
#
# 判据：mode 的中间那一位（组）必须包含读位（4/5/6/7）。
BAD_MODE="$(printf '%s\n' "$BEFORE" | awk '{ split($3, m, ""); if (m[2] != "" && m[2] !~ /^[4567]$/) print "  " $1 " mode=" $3 " —— 组读位是 0，容器读不到" }')"
if [[ -n "$BAD_MODE" ]]; then
  printf '%s\n' "$BAD_MODE"
  fail '有密钥的组读位是 0。挂进容器的密钥，容器必须读得到（cli-tools 是 uid 10002 / gid 10001，只能靠组权限）。跑一次 scripts/install.sh 会把它们统一成 0640。'
fi

if $DRY_RUN; then
  printf '\n--dry-run：没有同步、没有构建、没有重启。\n'
  exit 0
fi

step "2) 同步源码"
# 三条硬规矩：
#   · **不带 --delete**：远端有我自己留的 .env.pre-* 备份，删了就回不去。
#   · **不同步 runtime/ 与 .env**：那是数据与密钥，本机的版本是空的。
#   · **不做任何 chown**：写不进去就定点 sudo chown 那一个路径，不搞递归。
rsync -az --omit-dir-times \
  --exclude '.git' --exclude '.venv' --exclude 'node_modules' \
  --exclude 'runtime/' --exclude '.env' --exclude '__pycache__' \
  --exclude '.pytest_cache' --exclude '*.pyc' --exclude '.DS_Store' \
  ./ "$HOST:$REMOTE_DIR/" || fail 'rsync 失败。'
LOCAL_ZIP="$(shasum -a 256 dist/social-archive-extension.zip | cut -d' ' -f1)"
REMOTE_ZIP="$(ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && sha256sum dist/social-archive-extension.zip | cut -d' ' -f1")"
[[ "$LOCAL_ZIP" == "$REMOTE_ZIP" ]] || fail "扩展包没同步过去（本地 ${LOCAL_ZIP}，远端 ${REMOTE_ZIP}）。"
printf '  源码已同步；扩展包 sha256 逐字节一致。\n'

step "3) 给正在跑的镜像打 :rollback"
ssh -o ConnectTimeout=20 "$HOST" "docker image inspect '$IMAGE' >/dev/null 2>&1 && docker tag '$IMAGE' social-archive/core:rollback && docker images --format '  {{.Repository}}:{{.Tag}}  {{.ID}}' | grep social-archive/core || echo '  （没有同名旧镜像，首次部署）'"

step "3.5) systemd 单元有没有漂"
# **rsync 只同步 /opt/social-archive，装着的 unit 在 /etc/systemd/system。**
#
# 2026-08-04 实测：我在仓里给 social-archive-backup.service 加了第二条
# ExecStart（备份运行库），部署、daemon-reload、systemctl start 全都
# `Result=success`——**而跑的还是旧的那一条**。装着的 unit 从来没被更新过。
# 差一点就把「备份跑通了」写进证据。
#
# **只报，不自动装。** unit 以 root 跑，自动安装的爆炸半径太大；
# 这里给出那一行 cp，由人来敲。
DRIFT=""
for unit in deploy/systemd/*.service deploy/systemd/*.timer; do
  [[ -e "$unit" ]] || continue
  name="$(basename "$unit")"
  if ! ssh -o ConnectTimeout=20 "$HOST" "sudo diff -q /etc/systemd/system/${name} ${REMOTE_DIR}/${unit} >/dev/null 2>&1"; then
    DRIFT="${DRIFT}  ${name}\n"
  fi
done
if [[ -n "$DRIFT" ]]; then
  printf '  **这些 systemd 单元与仓里的不一致**（装着的是旧的）：\n'
  printf "$DRIFT"
  printf '  同步它们（unit 以 root 跑，所以由你来敲）：\n'
  printf "    ssh %s 'sudo cp %s/deploy/systemd/{%s} /etc/systemd/system/ && sudo systemctl daemon-reload'\n" \
    "$HOST" "$REMOTE_DIR" "$(printf "$DRIFT" | tr -d ' ' | paste -sd, -)"
  fail 'systemd 单元有漂移。改了 unit 而不装上去，跑的还是旧的——而 systemctl 照样报 success。'
fi
printf '  所有 systemd 单元与仓里一致。\n'

step "4) 构建前先看磁盘"
# **每次部署都会造一个 1GB 的镜像，旧的那个变成孤儿。** 我一天里部署了十几次，
# 生产盘从 8.3G 可用掉到 3.0G（93%）。紧接着 /v1/accounts 报过一次
# `sqlite3.OperationalError: unable to open database file`——SQLite 建不出
# -wal/-shm 时就是这句话。复现不了（清完盘之后连打三次全 200），
# 所以「磁盘」只是最合理的怀疑，不是已证实的根因。
#
# 但门槛该有：**盘紧的时候不许再往上叠一个 1GB 的镜像。**
FREE_GB="$(ssh -o ConnectTimeout=20 "$HOST" "df -BG --output=avail / | tail -1 | tr -dc '0-9'")"
printf '  根分区可用 %sG\n' "$FREE_GB"
if [[ -n "$FREE_GB" && "$FREE_GB" -lt 5 ]]; then
  printf '  可以安全回收的（只删悬空镜像，不碰同机其它项目）：\n'
  ssh -o ConnectTimeout=20 "$HOST" 'sudo docker images -f "dangling=true" --format "    {{.ID}}  {{.Size}}  {{.CreatedSince}}"' || true
  fail "可用空间不足 5G，拒绝构建。先回收：ssh $HOST 'for id in \$(sudo docker images -f dangling=true -q); do sudo docker rmi \$id; done'  —— **只删悬空镜像，不要用 docker system prune**（这台机器还跑着 memory-atlas / gatus / coolify 等别人的项目）。"
fi

step "5) 构建并上线"
ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && docker compose build core-api 2>&1 | tail -3 && docker compose up -d core-api core-worker 2>&1 | tail -4"

step "6) 部署后再量一次密钥不变量"
AFTER="$(secret_fingerprint)"
if [[ "$BEFORE" != "$AFTER" ]]; then
  printf '  部署前：\n'; printf '%s\n' "$BEFORE" | sed 's/^/    /'
  printf '  部署后：\n'; printf '%s\n' "$AFTER"  | sed 's/^/    /'
  fail '密钥的属主/权限在部署过程中变了。这就是 2026-08-04 那次断线的根因，别放过它。'
fi
printf '  与部署前逐字节一致。\n'

step "7) 验收：打一条要鉴权的路由（不是 /health）"
sleep 8
ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR'
  PORT=\$(grep -oP '(?<=^SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT=)[0-9]+' .env 2>/dev/null || echo 18765)
  curl -sf --max-time 10 \"http://127.0.0.1:\$PORT/health\" >/dev/null || { echo '  /health 都不通'; exit 1; }
  TOK=\$(sudo cat runtime/secrets/social_archive_api_token)
  CODE=\$(curl -s -o /tmp/sa_deploy_check.json -w '%{http_code}' --max-time 10 -H \"Authorization: Bearer \$TOK\" \"http://127.0.0.1:\$PORT/v1/accounts\")
  rm -f /tmp/sa_deploy_check.json
  if [ \"\$CODE\" != 200 ]; then echo \"  /v1/accounts 返回 \$CODE —— 上线没成，立刻回滚\"; exit 1; fi
  echo '  /health 200，/v1/accounts 200。鉴权链路是通的。'" \
  || fail "验收失败。回滚：ssh $HOST \"cd $REMOTE_DIR && docker tag social-archive/core:rollback $IMAGE && docker compose up -d core-api core-worker\""

step "8) 验收：下载页真正下发的那个包，是不是刚部署的这个"
# **磁盘上有那个文件**和**下载路由下发那个文件**是两件不同的事，
# 而 Owner 拿到的是后者。第 2 步只比过 dist/ 下的字节。
#
# 而且必须从机器内部打，并且**要看 content-type**：
# 2026-08-05 在外网 curl 了一次，拿回来的是 Cloudflare Access 的登录页，
# 34963 字节、哈希漂亮得很——差点据此断定「下载页发的是另一个包」。
# 一个 200 + text/html 的登录页，和一个包，哈希看起来一样体面。
ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR'
  PORT=\$(grep -oP '(?<=^SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT=)[0-9]+' .env 2>/dev/null || echo 18765)
  TYPE=\$(curl -s -o /tmp/sa_zip_check.zip -w '%{content_type}' --max-time 30 \"http://127.0.0.1:\$PORT/downloads/social-archive-extension.zip\")
  SERVED=\$(sha256sum /tmp/sa_zip_check.zip | cut -d' ' -f1)
  rm -f /tmp/sa_zip_check.zip
  case \"\$TYPE\" in
    application/zip*) ;;
    *) echo \"  下载路由回的不是包，是 \$TYPE —— 别拿它的哈希当数\"; exit 1 ;;
  esac
  if [ \"\$SERVED\" != '$LOCAL_ZIP' ]; then
    echo \"  下载页下发的不是刚部署的包（下发 \${SERVED:0:16}，本地 ${LOCAL_ZIP:0:16}）\"; exit 1
  fi
  echo '  下载页下发的就是刚部署的那个包，逐字节一致。'" \
  || fail "下载页下发的包对不上。Owner 装到的会是别的东西——这一步不能放过。"

printf '\n部署完成。回滚一行命令：\n'
printf '  ssh %s "cd %s && docker tag social-archive/core:rollback %s && docker compose up -d core-api core-worker"\n' "$HOST" "$REMOTE_DIR" "$IMAGE"
