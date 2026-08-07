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
# ## 这个脚本守住的六件事
#
#   1. **不做任何递归 chown。** 属主问题用 sudo 定点解决，不用大扫除。
#   2. **部署前后各量一次密钥不变量**（uid:gid:mode），漂了就大声说。
#   3. **回滚点在构建成功之后才定**，且按镜像 ID 定，不按标签——
#      中止的部署什么都没换掉，就不该动回滚点。
#   4. **验收打的是要鉴权的路由，不是 /health。** 上面那 10 分钟就是被
#      /health 的 200 骗过去的。
#   5. **验收还要打一次下载路由**：磁盘上有那个包，和下载页下发那个包，
#      是两件不同的事，而 Owner 拿到的是后者。
#   6. **主机 venv 必须指向仓里的 src/**。容器重建了、主机 venv 没人管——
#      实测它落后了两个版本，而四个耐久性 timer 全跑在它上面。
#
# ## 跑到一半被打断了怎么办
#
# 2026-08-06 实测过一次：调用方（我这边的工具）10 分钟超时，SIGTERM 打断在
# 第 5 步 `docker compose up` 中间。结果是**镜像已经构建好、api 和 cli-tools
# 起来了，而 core-worker 卡在 Created 没启动**——后台任务全部积压，
# 而 /health 是好的（它由 api 提供），**从外面看不出来**。
#
# 恢复只要一条命令，compose up 是幂等的：
#
#     ssh <host> 'cd /opt/social-archive && sudo docker compose up -d core-api core-worker cli-tools'
#
# 然后**一定要跑一次完整回读**（scripts/verify_production_deployment.py 与
# scripts/check_production_matches_the_repo.py）——被打断的部署最容易留下
# 「一半新一半旧」，而那正是三份一致性检查存在的理由。
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
ROLLBACK_CANDIDATE="social-archive/core:rollback-candidate"
# 磁盘门槛。**做成可配的，唯一的理由是它必须能被验。**
#
# 「空间不够 → 自动回收 → 重新量 → 还不够就中止」这一串，写死 5G 的话
# 只能等生产真的快满了才跑得到——而那是最不该拿来做第一次验证的时刻。
# 生产上不要设它，用默认值。
MIN_FREE_GB="${SOCIAL_ARCHIVE_DEPLOY_MIN_FREE_GB:-5}"

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
# **报告写到别处。** 发布门会把结果写进 evidence/final-verification.json，
# 而那份报告里有生成时间，每跑一次都不同——于是**这一次部署会把下一次挡在
# 上面那道「工作树干净」的门外**。2026-08-05 实测：第二次部署当场就被自己
# 上一次挡住了。一个自己会把自己挡住的门，用不了几次就会有人绕过去，
# 那时它连真的脏改动也挡不住。
.venv/bin/python scripts/final_verify.py --report "$(mktemp -t sa-gate)" >/dev/null \
  || fail '发布门未通过。'
.venv/bin/python scripts/build_extension_package.py >/dev/null || fail '扩展包没打出来——用户下载到的会是旧版本。'
# **打完就在真 Chrome 里装一次这个包。**
#
# 仓里十一个真 Chrome 演练，在这之前**一个都没有调用方**——全靠人记得去跑。
# 而且它们全都加载源码目录，并且在加载前把可选权限提成必给权限；
# 他真正下载的那一份、在权限未授予的状态下会怎样，从来没被走过。
# 2026-08-06 第一次跑就抓到：读取失败时报的是「读不出当前页面的域名」，
# 把他指向错的方向。
#
# 这一条放在这里而不是发布门里：它要起一个真 Chrome，约一分钟，
# 每次提交都跑太贵；而**发布前必须跑**——发出去的就是这个包。
# **十四个真 Chrome 演练全跑一遍**（约 5 分钟）。
#
# 原来这里只跑两个，其余归在 DRILLS.md 的「改到那条路时」——那一档靠人判断
# 「我这次碰到哪条链了」，而判断错的代价是那条链这一版整个没有证据。
# 零参数化做完之后（每个演练自己起 Chrome、自己打包），判断不再需要：
# 一条命令 4 分 42 秒，发布前全跑。
#
# 跳过的方式留着，但**跳过就等于这一版没有端到端证据**。
if [ -z "${SA_SKIP_DRILLS:-}" ]; then
  .venv/bin/python scripts/run_all_drills.py \
    || fail '真 Chrome 演练没全过——上面那张表里打 ✗ 的就是没通的链。设 SA_SKIP_DRILLS=1 可跳过（跳过就等于这一版没有端到端证据）。'
else
  printf '  ⚠️  跳过了真 Chrome 演练（SA_SKIP_DRILLS）——这一版没有端到端证据。\n'
fi
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

step "2.5) 主机 venv 装的是不是仓里这一份"
# **容器重建了，主机的 venv 没人管。**
#
# 2026-08-05 实测：容器里的 Core 报 0.0.0.7，而主机 venv 里装着的
# social_archive 是 **0.0.0.5** —— 整整落后两个版本，site-packages 里放的是
# 一份**拷贝**（不是 install.sh 写的 `pip install -e`），21 个文件与仓里不同，
# account_sync / auth / credentials / platform_payloads 等六个模块**根本不存在**。
#
# 而备份、复制、私有库同步、状态发布**四个 timer 全都跑在主机 venv 上**。
# 它们 import 的 config / db / utils 三个都在这 21 个里面——其中 utils.redact()
# 这一版之前会把 "Bearer" 藏掉却把 JWT 原样留下。
#
# 症状是完全静默的：systemctl 报 success，备份 PASS，而发布出来的状态页
# 少了一个这一版才有的字段——**只有去对字段才看得出来**。
#
# 这一步会自己修（editable 安装是幂等的，--no-deps 不碰任何依赖），修完再验一遍。
VENV_SRC="$(ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && sudo .venv/bin/python -c 'import social_archive; print(social_archive.__file__)' 2>/dev/null || true")"
case "$VENV_SRC" in
  "$REMOTE_DIR"/src/*)
    printf '  主机 venv 指向仓里的 src/，没有漂。\n' ;;
  *)
    printf '  **主机 venv 装的是一份拷贝**（%s）——正在按 install.sh 的原样改回 editable…\n' "${VENV_SRC:-读不出来}"
    ssh -o ConnectTimeout=60 "$HOST" "cd '$REMOTE_DIR' && sudo .venv/bin/python -m pip install -e . --no-deps" >/dev/null 2>&1 \
      || fail '主机 venv 改 editable 失败。四个 timer 会继续跑旧代码。'
    VENV_SRC="$(ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && sudo .venv/bin/python -c 'import social_archive; print(social_archive.__file__)'")"
    case "$VENV_SRC" in
      "$REMOTE_DIR"/src/*) printf '  已改好，现在指向 %s\n' "$VENV_SRC" ;;
      *) fail "主机 venv 还是没指向仓里的 src/（${VENV_SRC}）。" ;;
    esac ;;
esac
VENV_VERSION="$(ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && sudo .venv/bin/python -c 'import social_archive; print(social_archive.__version__)'")"
[[ "$VENV_VERSION" == "$VERSION" ]] \
  || fail "主机 venv 报的版本是 ${VENV_VERSION}，仓里是 ${VERSION}——四个 timer 跑的不是这一版。"
printf '  主机 venv 版本 %s，与仓里一致。\n\n' "$VENV_VERSION"

step "3) 记下正在跑的镜像（回滚点）"
# **只记，不打标。** 打标要等构建真的成了再打。
#
# 2026-08-05 实测：一次部署在第 4 步（磁盘不足）中止，而第 3 步已经把
# :rollback 挪到了当时正在跑的那个镜像上——于是 :rollback 和 :0.0.0.7
# 指向同一个镜像，**回滚点没了**，而结尾那行「回滚一行命令」还照印不误。
# 中止的部署不该动回滚点：它什么都没换掉。
IMAGE_BEFORE="$(ssh -o ConnectTimeout=20 "$HOST" "docker image inspect -f '{{.Id}}' '$IMAGE' 2>/dev/null || true")"
if [[ -n "$IMAGE_BEFORE" ]]; then
  printf '  正在跑：%s\n' "${IMAGE_BEFORE#sha256:}" | cut -c1-28
  # **先用一个临时标签把它钉住。**
  #
  # 只记 ID、等构建完再打标是不行的：2026-08-05 实测，构建会把同名旧镜像
  # 收走，等到要打标时 `docker tag <旧ID>` 报 **No such image**。
  # 而那一行当时写成 `docker tag … && printf …`，失败被 && 短路吞掉，
  # **一声不吭**——于是今天十几次部署，:rollback 一直停在很多版之前的
  # b2d060c5 上，而每次结尾还照印那行「回滚一行命令」。
  #
  # 打一个临时标签是幂等的、不占额外空间（同一批层），而且**中止的部署
  # 不会动 :rollback**——那个临时标签自己无害。
else
  printf '  （没有同名旧镜像，首次部署）\n'
fi

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

step "3.7) 这次到底要不要重建镜像"
# 2026-08-07：我连着两次改的只有文档、判据和演练（容器从来不跑它们），
# 而部署照旧走到第 4 步「构建前先看磁盘」，被 4.38G < 5G 拦下中止——
# **一次根本不需要构建的部署，卡在了「构建前」的门上。**
# 于是那些对生产零风险的改动全都推不上去。
#
# 镜像的输入是可以穷举的（就写在 Dockerfile 的 COPY 里），所以这件事有精确答案：
# 逐字节比「仓里的 COPY 输入」和「镜像里 /app 那一份」。
# **一切不确定（ssh 不通、读不出清单、一个文件都没数到）都算「要重建」**——
# 白构建一次只是慢，漏构建一次是他打开界面发现改的东西没上去而部署报了成功。
#
# **开关只能往「多构建」那一侧拨。** 没有反向的开关（能强制跳过构建的开关，
# 迟早会有人在真该重建的时候拨它）。它有两个用处：
#   · 判断万一错了，有一条不用改代码的退路；
#   · **让「磁盘不够 → 中止」那条路走得到**——不然它只在盘真的快满时才跑得到，
#     而那是最不该拿来做第一次验证的时刻。这和门槛做成可配是同一个理由。
NEEDS_REBUILD=1
if [[ -n "${SOCIAL_ARCHIVE_DEPLOY_FORCE_REBUILD:-}" ]]; then
  printf '  SOCIAL_ARCHIVE_DEPLOY_FORCE_REBUILD 已设：**强制重建**，不问判断。\n'
elif REBUILD_JSON="$(.venv/bin/python scripts/does_this_deploy_need_a_rebuild.py \
      --host "$HOST" 2>&1)"; then
  NEEDS_REBUILD=0
fi
if [[ -n "${SOCIAL_ARCHIVE_DEPLOY_FORCE_REBUILD:-}" ]]; then
  REBUILD_JSON='{"why_zh": "强制重建（SOCIAL_ARCHIVE_DEPLOY_FORCE_REBUILD）"}'
fi
printf '  %s\n' "$(printf '%s' "$REBUILD_JSON" | .venv/bin/python -c '
import json, sys
try:
    payload = json.loads(sys.stdin.read())
except Exception as exc:                       # 读不懂它说什么 → 上面已按「要重建」
    print(f"判断输出读不懂（按「要重建」处理）：{exc}")
else:
    print(payload.get("why_zh", "（没给理由）"))
    for name in payload.get("runtime_differs", []) + payload.get("missing_from_image", []):
        print(f"    要重建，因为：{name}")
')"
if (( NEEDS_REBUILD == 0 )); then
  printf '  **跳过构建与上线。** 服务在跑的那一份已经是仓里这一份，重建出来会一模一样。\n'
  printf '  （源码已经 rsync 到主机；下面的验收照跑，不因为跳过构建而少一道。）\n'
fi

step "4) 构建前先看磁盘"
# **这两个函数和门槛定义在 if 外面。**
#
# 2026-08-07 实测：我把整段磁盘检查包进 `if (( NEEDS_REBUILD == 1 ))` 时，
# 把函数**定义**也一起包了进去。于是跳过构建的那条路上第 10 步一跑就是
# `free_kb: command not found`——**部署到最后一步才炸，而前面九步全绿**。
# 定义要放在分支外，分支只管要不要「用」它们。
free_kb() { ssh -o ConnectTimeout=20 "$HOST" "df -k --output=avail / | tail -1 | tr -dc '0-9'"; }
show_gb() { awk -v kb="$1" 'BEGIN{printf "%.2f", kb/1048576}'; }
MIN_FREE_KB=$(( MIN_FREE_GB * 1048576 ))
if (( NEEDS_REBUILD == 0 )); then
  printf '  跳过：这次不构建，不会新增镜像。\n'
fi
if (( NEEDS_REBUILD == 1 )); then
# **每次部署都会造一个 1GB 的镜像，旧的那个变成孤儿。** 我一天里部署了十几次，
# 生产盘从 8.3G 可用掉到 3.0G（93%）。紧接着 /v1/accounts 报过一次
# `sqlite3.OperationalError: unable to open database file`——SQLite 建不出
# -wal/-shm 时就是这句话。复现不了（清完盘之后连打三次全 200），
# 所以「磁盘」只是最合理的怀疑，不是已证实的根因。
#
# 但门槛该有：**盘紧的时候不许再往上叠一个 1GB 的镜像。**
# **用 KB 量，不要用向上取整的块单位。**
# 2026-08-05 实测：真实可用 4.84G，`df -BG` 报 5G，于是这道「至少 5G」的门
# 当场放行。最坏情况虚报接近 1G（4.01G 也会报成 5G），而它拦的正是
# 「盘紧的时候别再往上叠一个 1GB 的镜像」——虚报的方向恰好是不安全那一侧。
FREE_KB="$(free_kb)"
printf '  根分区可用 %sG（门槛 %sG）\n' "$(show_gb "$FREE_KB")" "$MIN_FREE_GB"
if [[ -n "$FREE_KB" && "$FREE_KB" -lt "$MIN_FREE_KB" ]]; then
  # **自己收拾自己的。** 这道门今天拦了两次，两次都是我手工去回收——
  # 而「能你做的就别让我做」。但这台机器还跑着别人的项目，所以**只回收
  # 带我们自己标签的悬空镜像**（Dockerfile 里的 com.socialarchive.project），
  # 绝不 `docker system prune`，也不动没有这个标签的悬空镜像。
  #
  # 盖标签之前造出来的旧镜像没有这个戳，收不掉——那是对的，宁可收不掉，
  # 不可误删别人的。收不够就照旧中止，把那行手工命令留给人。
  printf '  空间不够，先回收**我们自己的**悬空镜像（带 com.socialarchive.project 标签的）：\n'
  ssh -o ConnectTimeout=60 "$HOST" '
    ids=$(sudo docker images -f "dangling=true" -f "label=com.socialarchive.project=social-archive" -q)
    if [ -z "$ids" ]; then echo "    没有带我们标签的悬空镜像可收。"; else
      for id in $ids; do
        printf "    回收 %s\n" "$(sudo docker images --format "{{.ID}} {{.Size}}" -f "dangling=true" | grep "^$id" || echo "$id")"
        sudo docker rmi "$id" >/dev/null 2>&1 || true
      done
    fi' || true
  FREE_KB="$(free_kb)"
  printf '  回收后可用 %sG\n' "$(show_gb "$FREE_KB")"
fi
if [[ -n "$FREE_KB" && "$FREE_KB" -lt "$MIN_FREE_KB" ]]; then
  # **还不够就收掉自己上一个版本的镜像。**
  #
  # 2026-08-07 实测：盘上躺着 social-archive/core:0.0.0.21（451MB）和
  # cli-tools:0.0.0.21（995MB），**没有任何容器在用**，也不是回滚点
  # （回滚点是另一个 tag、另一个镜像 ID，当天核过：rollback=304ada…、
  # 0.0.0.21=365be6…，是两个东西）。一共 1.4G，正好是这道门差的那一截。
  #
  # 我原本把它列成「要 Owner 裁定」。**核过之后这个判断不成立**：
  # 它们是我们自己每次部署留下的，铁律 3 写着谁开的谁收，而第 10 步早就在
  # 自动回收我们自己的悬空镜像了——只是这两个还挂着 tag 所以不算悬空。
  # 同一类东西，不该因为多一个 tag 就变成他的事。
  #
  # **四道自锁写在 scripts/reclaim_our_superseded_images.sh 里，那里有判据打反例。**
  # 删镜像不可逆，不能只靠读一遍就上——判据用假 docker 证过它不碰别的项目、
  # 不碰当前版本、不碰回滚点、不碰任何被容器引用的 ID，同时**真的会收**那个
  # 该收的（只验反例是红的不够，一个什么都不删的脚本也能让四条反例全过）。
  printf '  还不够，再收掉**我们自己上一个版本**的镜像（不碰别的项目、不碰回滚点）：\n'
  ssh -o ConnectTimeout=60 "$HOST" "bash -s -- '$VERSION'" \
    < scripts/reclaim_our_superseded_images.sh || true
  FREE_KB="$(free_kb)"
  printf '  回收后可用 %sG\n' "$(show_gb "$FREE_KB")"
fi
if [[ -n "$FREE_KB" && "$FREE_KB" -lt "$MIN_FREE_KB" ]]; then
  # **第三段：收掉没被引用的构建缓存。**
  #
  # 2026-08-07 我手工做过一次：那天可用掉到 3.23G——**就是当初 SQLite
  # 建不出 -wal 那次事故的水位**——`docker builder prune -f` 收回 913.7MB，
  # 回到 7.60G，默认门槛照常过。
  #
  # **不加 -a。** 不加就只收「没有任何东西引用」的那部分：不动镜像、
  # 不动容器、不动卷。加了 -a 会把同机每个项目的下一次构建都拖慢，
  # 那才是要人裁定的事。
  #
  # 为什么做成自动的：Owner 说过「我已经给你至少十次了，你再不断重复
  # 这个步骤流程环节」。**能我做的就别拿去问他**——这一步的代价是
  # 「下次构建慢一点」，不是任何不可逆的东西。
  #
  # 收到 0 也很正常（刚收过、或者缓存全被现有镜像引用着）：
  # 那不是失败，下面还会重新量一次再决定要不要中止。
  printf '  还不够，再收掉**没被引用的构建缓存**（不加 -a：不动镜像/容器/卷）：\n'
  ssh -o ConnectTimeout=180 "$HOST" 'sudo docker builder prune -f 2>&1 | tail -1' \
    | sed 's/^/    /' || true
  FREE_KB="$(free_kb)"
  printf '  回收后可用 %sG\n' "$(show_gb "$FREE_KB")"
fi
if [[ -n "$FREE_KB" && "$FREE_KB" -lt "$MIN_FREE_KB" ]]; then
  # **建议要指向真正占地方的东西。**
  #
  # 2026-08-05 实测：门在 4G 上拦下部署，而**悬空镜像是 0 个**——
  # 它却还在叫人「回收悬空镜像」。那是又一次「下一步指向一个帮不上忙的东西」，
  # 和我今天在连接器文案上修的是同一种病，只不过这次在我自己的门里。
  # 所以先把真实占用摆出来，让人看着数字决定。
  printf '  仍然不够。**先看清什么在占地方**（悬空镜像可能一个都没有）：\n'
  DF_TABLE="$(ssh -o ConnectTimeout=20 "$HOST" 'sudo docker system df 2>/dev/null' || true)"
  printf '%s\n' "$DF_TABLE" | sed 's/^/    /'
  printf '    我们自己的镜像：\n'
  ssh -o ConnectTimeout=20 "$HOST" 'sudo docker images --format "      {{.Repository}}:{{.Tag}}  {{.Size}}" | grep social-archive' || true
  printf '    悬空镜像（含别的项目的，**不自动删**）：\n'
  DANGLING="$(ssh -o ConnectTimeout=20 "$HOST" 'sudo docker images -f "dangling=true" --format "      {{.ID}}  {{.Size}}  {{.CreatedSince}}"' || true)"
  printf '%s\n' "$DANGLING"
  # **建议要读那张表，不许猜。**
  #
  # 2026-08-07 实测：这段原来写着「一个都没有就多半是 Build Cache 占着，
  # 跑 docker builder prune」。而当时那张表上 **Build Cache 的 RECLAIMABLE 是 0B**
  # ——照着做会白等一场，什么都收不回来。
  # 这正是我今天一整天在修的那种病，只不过这次在我自己的报错里：
  # **指错原因的告警，比不告警更费人。**
  # 所以现在从表里现取 RECLAIMABLE，收不回来就直说收不回来。
  CACHE_RECLAIMABLE="$(printf '%s\n' "$DF_TABLE" | awk '/^Build Cache/ {print $NF}')"
  case "${CACHE_RECLAIMABLE:-0B}" in
    0B|0|"") CACHE_ADVICE="· 构建缓存**上面已经自动收过了**，现在没有无引用的可收
    （不加 -a，所以不碰别的项目正在复用的层）。这条路这次帮不上忙。" ;;
    *) CACHE_ADVICE="· 上面自动收过一轮之后，构建缓存里还剩 ${CACHE_RECLAIMABLE} 标着可回收。
    要再往下收只能 \`docker builder prune -a\`，那会把同机每个项目的下一次构建
    都拖慢，**由人决定**。" ;;
  esac
  if [[ -z "$(printf '%s' "$DANGLING" | tr -d '[:space:]')" ]]; then
    DANGLING_ADVICE="· **悬空镜像一个都没有**——这条路这次帮不上忙。"
  else
    DANGLING_ADVICE="· 上面那张悬空镜像表里可能有别的项目的——**它对他们可能正是回滚点**。
    确认某一个确实该删，再单独 \`sudo docker rmi <ID>\`。
    **一个一个来；不要用整张列表一锅端**——那会把别人的一起删掉。
    （这里故意不写出那条一锅端的命令：**报错信息里的命令是会被照抄的**。）"
  fi
  # 谁在涨——把最大的那个可写层摆出来，人一眼就知道该找谁。
  printf '    可写层最大的容器（**涨的多半是它，不一定是我们的**）：\n'
  ssh -o ConnectTimeout=30 "$HOST" \
    'sudo docker ps -as --format "{{.Names}}\t{{.Size}}" 2>/dev/null | sort -t"	" -k2 -hr | head -3 | sed "s/^/      /"' || true
  fail "可用空间不足 ${MIN_FREE_GB}G，拒绝构建。

  **我们自己的已经收过了**：悬空镜像 + 上一个版本的镜像，两轮都跑过了。
  还不够的话，占地方的不是我们的。按上面那几张表挑：

  ${DANGLING_ADVICE}
  ${CACHE_ADVICE}
  · 上面「可写层最大的容器」那一行如果不是 social-archive 开头，
    **那是别的项目在涨**，找它的主人，不要在这里删。
  · **任何情况下都不要用 docker system prune**（这台机器还跑着
    memory-atlas / gatus / coolify 等别人的项目）。"
fi
fi   # NEEDS_REBUILD == 1（不构建就不看磁盘：不会新增镜像）

step "5) 构建并上线"
if (( NEEDS_REBUILD == 0 )); then
  printf '  跳过：镜像里那份已经和仓一致，重建出来会一模一样。\n'
  printf '  **回滚点不动**——没造新镜像，就没有"上一个"需要退回去。\n'
else
# **钉住当前镜像放在这里，不放在第 3 步。**
#
# 2026-08-05 实测：原来第 3 步就打 :rollback-candidate，而部署可能在第 4 步
# （磁盘不够）中止——那个标签就留下来，**死死钉住一个 1.06GB 的镜像**，
# 它因此永远不会变成悬空、永远收不掉。于是「磁盘不够 → 中止 → 又多钉一个」
# 自己喂自己。挪到磁盘门之后、构建之前，中止的部署就不会留下它。
if [[ -n "$IMAGE_BEFORE" ]]; then
  ssh -o ConnectTimeout=20 "$HOST" "docker tag '${IMAGE_BEFORE}' '${ROLLBACK_CANDIDATE}'" \
    || fail '钉不住当前镜像，无法保证回滚点——先查 docker 再部署。'
  printf '  已用 %s 钉住部署前那个镜像，构建不会把它收走。\n' "$ROLLBACK_CANDIDATE"
fi
ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && docker compose build core-api 2>&1 | tail -3" || fail '构建失败，什么都没换，回滚点原样保留。'
# 构建成了，这才把回滚点从临时标签转正——**在 up 之前**，那一刻跑的还是旧的。
# 用临时标签而不是 ID：ID 可能已经被这次构建收走了（见第 3 步那段注释）。
if [[ -n "$IMAGE_BEFORE" ]]; then
  ssh -o ConnectTimeout=20 "$HOST" \
    "docker tag '${ROLLBACK_CANDIDATE}' social-archive/core:rollback && docker rmi '${ROLLBACK_CANDIDATE}' >/dev/null 2>&1 || true" \
    || fail '回滚点没定成。这次上线会没有可回的地方，先查清楚再继续。'
  ROLLBACK_ID="$(ssh -o ConnectTimeout=20 "$HOST" "docker image inspect -f '{{.Id}}' social-archive/core:rollback")"
  [[ "$ROLLBACK_ID" == "$IMAGE_BEFORE" ]] \
    || fail "回滚点指向的不是部署前那个镜像（回滚点 ${ROLLBACK_ID}，部署前 ${IMAGE_BEFORE}）。"
  printf '  回滚点已定在部署前那个镜像 %s 上（已核对）。\n' "${IMAGE_BEFORE#sha256:}" | cut -c1-56
fi
ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && docker compose up -d core-api core-worker 2>&1 | tail -4"
fi   # NEEDS_REBUILD

step "5.5) 另一个容器（cli-tools）是不是也跟上了这一版"
# **部署只重建 core-api。** cli-tools 是另一个镜像，构建上下文是
# sidecars/cli-tools/（Dockerfile + server.py）——改了它而不重建，
# 跑着的就一直是旧的，**而 compose 会照常报 Healthy**。
# 这与「主机 venv 落后两个版本」是同一族，只是换了个地方藏。
#
# 为什么不干脆每次都重建它：实测缓存命中也要 **130 秒**，而且会产出一个
# 新镜像（有一层没命中缓存）。生产盘已经因为镜像堆积紧过一次。
# 所以**先比对，不同才重建**——比对是一次 sha256，几乎不要钱。
#
# 比的是容器里的 /worker/server.py。这个路径是量出来的，不是猜的：
# 容器里还有 /usr/local/lib/python3.12/{http,xmlrpc}/server.py 两个同名文件，
# 早先用 `find | head -1` 差点比错了对象（那次侥幸对了，因为 -maxdepth 4
# 把标准库那两个挡在外面）。**别再靠侥幸，写死量到的那个路径。**
# **两个文件都要比。** 只比 server.py 的话，「只改 Dockerfile」那种改动
# 一点都看不出来——Dockerfile 因此被复制进了镜像（/worker/Dockerfile.built）。
LOCAL_SIDECAR="$(cat sidecars/cli-tools/server.py sidecars/cli-tools/Dockerfile | shasum -a 256 | cut -d' ' -f1)"
REMOTE_SIDECAR="$(ssh -o ConnectTimeout=20 "$HOST" "sudo docker exec social-archive-cli-tools-1 sh -c 'cat /worker/server.py /worker/Dockerfile.built 2>/dev/null | sha256sum' 2>/dev/null | cut -d' ' -f1" || true)"
# 旧镜像里没有 Dockerfile.built，cat 只读到 server.py，哈希自然对不上——
# 那正是该重建的信号，不用特判。
if [[ -z "$REMOTE_SIDECAR" ]]; then
  printf '  cli-tools 容器没在跑或读不到 /worker/ 下那两个文件——**跳过了这一步，这不是通过**。\n'
elif [[ "$LOCAL_SIDECAR" == "$REMOTE_SIDECAR" ]]; then
  printf '  cli-tools 跑的就是仓里这一份。\n'
else
  printf '  **cli-tools 落后了**（容器 %s，仓里 %s）——重建并换上（约两分钟）…\n' \
    "${REMOTE_SIDECAR:0:12}" "${LOCAL_SIDECAR:0:12}"
  ssh -o ConnectTimeout=300 "$HOST" "cd '$REMOTE_DIR' && sudo docker compose build cli-tools && sudo docker compose up -d cli-tools" >/dev/null 2>&1 \
    || fail 'cli-tools 重建失败。'
  REMOTE_SIDECAR="$(ssh -o ConnectTimeout=20 "$HOST" "sudo docker exec social-archive-cli-tools-1 sh -c 'cat /worker/server.py /worker/Dockerfile.built | sha256sum'" | cut -d' ' -f1)"
  [[ "$LOCAL_SIDECAR" == "$REMOTE_SIDECAR" ]] \
    || fail "cli-tools 重建完还是对不上（容器 ${REMOTE_SIDECAR}，仓里 ${LOCAL_SIDECAR}）。"
  printf '  已换上，现在与仓里一致。\n'
fi

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

step "8.5) 验收：装上这个包的真 Chrome，够不够得着**刚部署的这台生产**"
# **十四个演练一个都没碰过真生产。** 它们全带着
#   --host-resolver-rules=MAP social-archive.linzezhang.com 127.0.0.1:<假端口>
# 把域名指到本机假服务器上。那对演练是对的（要可重复、要造边界情况），
# 但意味着「插件能不能连上他那台真服务器」**从来没被验过**——
# 而验收条件第 4 条写的正是「不拿本地结果冒充线上结果」。
#
# **放在第 8 步之后**：它验的是刚部署完的这一版。放前面验的是上一版。
#
# 2026-08-07 写这条时先栽了一次：探针把端点写死成资料库域名
# （social-archive.linzezhang.com，在 Cloudflare Access 后面），量出
# 「插件够不着生产」，我差点就那么报了。插件真正用的是 runtime-config.json 里的
# **api 域名**。现在端点一律取插件自己的配置，资料库域名留作**负对照**——
# 它必须是不通的，否则这条探针连「挡住了」都认不出来。
if [ -z "${SA_SKIP_DRILLS:-}" ]; then
  .venv/bin/python scripts/production_reachability_drill.py >/dev/null \
    || fail "装上发布包的真 Chrome 够不着生产。**这是 Owner 那边「点了没反应」的形状**——
  跑 scripts/production_reachability_drill.py 看它报的是哪一条。"
  printf '  真 Chrome + 发布包 + 真令牌，从生产读回了条目；负对照（Access 后的域名）确认不通。\n'
else
  printf '  ⚠️  跳过了（SA_SKIP_DRILLS）——**这一版没有「插件够得着生产」的证据**。\n'
fi

step "8.7) 读一眼：他那边自动同步的实际情况"
# **不是门，是播报。** 它取决于他浏览器里的登录态和授权，那不是部署的属性——
# 拿它当门只会得到一道我永远修不好、于是很快被绕过的红。
#
# 但每次发布看一眼是值的：2026-08-07 第一次读才知道，
# 8/3 那晚 bilibili 102→102、douyin 56→56 真的进过东西（验收条件第 1 条
# **早就在他的真数据上成立过**），而 8/4 之后每一次都是 0 条，
# 最后一次错误码 PLATFORM_PERMISSION_MISSING——正是这次修掉的那个缺陷。
# 我此前一直在证明「机制走得通」，**从没问过「他那边到底发生了没有」**。
.venv/bin/python scripts/read_production_sync_history.py --brief 2>/dev/null \
  || printf '  读不到同步历史（不影响部署）\n'

step "9) 验收：仓、主机、**镜像里那一份**，三份是不是同一份代码"
# 第 8 步只核了**扩展包**那一个文件。其余一百多个源文件，在这一步之前
# 从来没有任何东西核过——而 /opt/social-archive **不是 git 检出**，
# 那台机器上没有 `git status` 可问。
#
# **要比的是三份。** 2026-08-05 才弄清楚：容器里的 /app 是**烤进镜像的**，
# 不是主机目录的绑定挂载（只有 /run/secrets/* 是）。所以
#   rsync 同步到主机 ≠ 服务在跑它。
# 当天就撞上了：把修好的脚本放到主机、在容器里跑，跑的还是旧的。
# 上面那句「systemctl restart 不会重建镜像」说的是同一件事的另一面。
#
# 放在最后一步，是因为它要的正是「构建完、容器起来之后」的状态。
.venv/bin/python scripts/check_production_matches_the_repo.py \
    --host "$HOST" --remote-dir "$REMOTE_DIR" --explain-differences \
  || fail "仓／主机／镜像三份对不上。**别把这一步当噪音**：
  · only_on_production            —— 生产上有来路不明的代码正在跑
  · container_is_running_older_code —— 服务执行的不是你以为的那一版，要重建镜像
  两者的下一步完全不同，报告里已分开列。"
printf '  三份一致：仓 = 主机 = 镜像。\n'

step "10) 收掉自己上一次留下的那个镜像"
# **谁开的谁收。** 每成功部署一次，就有一个 1GB 的旧镜像变成悬空——
# 上一次的回滚点被这一次顶替掉了（:rollback 只留一层，那是设计）。
#
# 原来只有「磁盘不够」那条路才回收，于是它**一直攒到把门顶住为止**：
# 2026-08-05 实测 7.31G → 部署一次 → 5.19G，两次就顶到 5G 门槛。
# 那天为了腾地方，最后是让 Owner 去裁定删同机别的项目的缓存——
# **而真正该收的是我们自己每次留下的这一个。**
#
# 只收**带我们标签、且已经悬空**的（`com.socialarchive.project`）：
# 这台机器还跑着 memory-atlas / gatus / coolify 等别人的项目，
# 任何情况下都不 `docker system prune`，也不动没有这个标签的悬空镜像。
# 收不掉就只是少收一点，绝不因此让部署失败——它已经成功了。
RECLAIMED="$(ssh -o ConnectTimeout=60 "$HOST" '
  ids=$(sudo docker images -f "dangling=true" -f "label=com.socialarchive.project=social-archive" -q)
  n=0
  for id in $ids; do sudo docker rmi "$id" >/dev/null 2>&1 && n=$((n+1)); done
  echo "$n"' 2>/dev/null || echo 0)"
FREE_KB="$(free_kb)"
printf '  回收了 %s 个我们自己的悬空镜像；根分区可用 %sG\n' \
  "${RECLAIMED:-0}" "$(show_gb "$FREE_KB")"

# **先确认回滚点真的在，再把那条命令印出来。**
#
# 2026-08-07 实测：`social-archive/core:rollback` 已经不存在了，而这里照旧
# 印着一条用它的命令——照抄会得到 `No such image`。**那是在出事那一刻
# 才会被发现的假承诺**，正是这个仓一整天在修的那种「下一步指向一个不存在
# 的东西」。
#
# 它为什么会没：这台机器上跑着 Coolify，它自带的清理会 prune 掉**没有容器
# 在用的镜像**——回滚点按定义就是那一类，任何 tag 都保不住它
# （`docker image prune -a` 不看 tag）。所以这里不假定它在，**每次现查**。
printf '\n部署完成。\n'
if ssh -o ConnectTimeout=20 "$HOST" "docker image inspect social-archive/core:rollback >/dev/null 2>&1"; then
  printf '回滚一行命令：\n'
  printf '  ssh %s "cd %s && docker tag social-archive/core:rollback %s && docker compose up -d core-api core-worker"\n' "$HOST" "$REMOTE_DIR" "$IMAGE"
else
  printf '**这台机器上现在没有回滚点**（social-archive/core:rollback 不存在）。\n'
  printf '  同机 Coolify 的清理会 prune 掉没有容器在用的镜像，任何 tag 都挡不住。\n'
  printf '  真要回退，走仓：git checkout %s 之前那个提交，再跑一次这个脚本。\n' "$(git rev-parse --short HEAD)"
  printf '  （仓才是真源。镜像可以没，代码不会没。）\n'
fi
