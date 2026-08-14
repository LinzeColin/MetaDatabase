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

# **生产是哪台，只有一个真源**：deploy/PRODUCTION_HOST。
# 2026-08-10：这个名字曾写死在 16 个文件 21 处，换机器会漏掉几处、
# 而漏掉的那几处静默指向旧机器，没有任何东西会报错。
HOST="${SOCIAL_ARCHIVE_DEPLOY_HOST:-$(cat "$(dirname "$0")/../deploy/PRODUCTION_HOST" 2>/dev/null || echo "")}"
[[ -n "$HOST" ]] || { echo "读不到 deploy/PRODUCTION_HOST——生产是哪台没有真源了，不许猜。"; exit 2; }
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

# **本地 venv 要在开工前就确认，不能等某一步用到它才发现没有**（2026-08-10）。
#
# 这一天 `.venv` 在这棵工作树里**消失了两次**（树本身还在、git 干净、
# `dist/` 和 egg-info 也在，只有 `.venv` 没了；不是 `git clean`）。
# 两次都不是在开头炸的，因为脚本各处零散地写着相对路径 `.venv/bin/python`：
#
#   第一次  第 143 行（演练跑完之后的镜像输入清单）→ 中止，**生产没被动过**
#   第二次  第 618 行（第 8.2 步比包与 HEAD）→ **镜像已经建好上线了，
#           而验证那一步没跑成**。这是最坏的落点：生产变了，验证没做。
#
# 所以在这里一次性确认。**不许悄悄退回 `python3`**：系统那个是 3.9，
# 而这个项目要 >=3.12，退回去只会在更远的地方以更难懂的方式炸
# （这个仓在「没测过的兜底分支只在别人机器上发作」上栽过）。
[ -x "$ROOT/.venv/bin/python" ] || fail "本地 venv 不在（$ROOT/.venv/bin/python）。
  这棵树上 2026-08-10 见过它凭空消失两次。
  重建（**只用标准库，不需要额外装任何东西**——scripts/install.sh 用的也是这条路）：
      cd '$ROOT'
      python3.13 -m venv .venv || python3.12 -m venv .venv
      .venv/bin/python -m pip install --upgrade pip
      .venv/bin/pip install -e '.[test]'
  （装了 uv 的话这条更快，**但 uv 不是前置条件**：
      uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -e '.[test]'）"
"$ROOT/.venv/bin/python" -c 'import sys; assert sys.version_info >= (3, 12), sys.version' \
  || fail "本地 venv 的 Python 低于 3.12——发布门和判据都会以看不懂的方式失败。按上面那条命令重建。"

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
# **先确认这里真的是一个 git 工作树。**（2026-08-14）
#
# `git status --porcelain` 在**非仓目录**里把错误写到 stderr、stdout 是空的，
# 退出码 128。而下面那句只看 stdout —— 空字符串 → `-z` 成立 → **判「干净」并放行**。
# 实测过：`stdout=[] 长度=0 退出码=128`。
#
# 这不是假想。生产机上**也有一份这个脚本**（rsync 把整棵树同步过去了），
# 而 `/opt/social-archive` 是 rsync 的目标、**没有 .git**。
# 交接提示词让接手方「改代码之后必须跑 deploy_to_production.sh」，
# 他 ssh 进生产、看见脚本就在那儿、顺手一跑——这道本该拦住他的门会放行。
#
# 而这道门的意思是「部署的必须是**已入库的那一版**」：非仓里根本没有那一版，
# 所以正确答案是**大声失败**，不是安静通过。
[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] || fail "这里不是一个 git 工作树（${ROOT}）。
  这个脚本要在**开发机的仓里**跑。生产上的 ${REMOTE_DIR} 是 rsync 的目标、没有 .git，
  「部署的必须是已入库的那一版」在那里无从谈起。
  要改生产，请回到开发机的工作树里改完、提交，再在**那边**跑这个脚本。"
GIT_DIRTY="$(git status --porcelain 2>/dev/null)"; GIT_RC=$?
[ "${GIT_RC}" -eq 0 ] || fail "git status 跑不起来（退出码 ${GIT_RC}）。**不许把它的空输出当成「工作树干净」。**"
[[ -z "${GIT_DIRTY}" ]] || fail '本工作树有未提交改动。部署的必须是已入库的那一版，否则生产上跑的东西没有对应的提交。'
# **报告写到别处。** 发布门会把结果写进 evidence/final-verification.json，
# 而那份报告里有生成时间，每跑一次都不同——于是**这一次部署会把下一次挡在
# 上面那道「工作树干净」的门外**。2026-08-05 实测：第二次部署当场就被自己
# 上一次挡住了。一个自己会把自己挡住的门，用不了几次就会有人绕过去，
# 那时它连真的脏改动也挡不住。
# **`--full` 才会跑那 1300 条测试**（2026-08-10）。
#
# 不带 `--full` 时 `final_verify.py` 是 `suite_mode: structural`、
# `application_suite_rerun: false`——**只跑 32 道结构门，一条单元测试都不跑**。
# 那本来不要紧，因为 pre-commit 钩子每次提交都跑；
# 而今天机器侧的 `tools/install-guards.sh` 把 `.git/hooks/pre-commit`
# 换成了铁律 2 的主树守卫，**跑测试那个钩子没了**，于是那 1300 条测试
# 一度只剩「我记得跑」这一条保障——正是我今天一整天在别处拆掉的那种。
#
# 钩子是机器侧的东西，不该由我覆盖回去；**测试该待的地方本来就是通往生产的这条路**。
# 代价是每次部署多两分钟。
# **失败时必须说出是哪一道门**（2026-08-12）。
#
# 原来这里是 `>/dev/null || fail '发布门未通过（含全量测试）。'`：
# 35 道门跑完，报告写进一个 `mktemp` 出来的随机文件名，然后**整个吞掉**。
# 部署日志一共 5 行，最后一行是那句「发布门未通过」——
# 哪道门、为什么，一个字都没有。那次真的有两处不合格
# （一条新测试起 git 没洗环境；升版之后前端缓存戳没重打），
# 而日志读起来只像「不知道哪里坏了」。
#
# 报告落到固定路径，失败时把不合格那几项直接印出来。
GATE_REPORT="${TMPDIR:-/tmp}/sa-gate-report.json"
if ! .venv/bin/python scripts/final_verify.py --full --report "$GATE_REPORT" >/dev/null; then
  .venv/bin/python - "$GATE_REPORT" <<'PY' >&2 || true
import json, sys
try:
    results = json.load(open(sys.argv[1]))["results"]
except Exception as exc:
    print(f"（报告也读不出来：{exc}）"); raise SystemExit
bad = [r for r in results if r.get("exit_code")]
print(f"\n不合格 {len(bad)} 项 / 共 {len(results)} 项：")
# 尾巴 25 行会被 pytest 的 warnings summary 占满，**而 FAILED 那几行正好在它后面**——
# 第一版就是这样：印出来的全是弃用警告，真正红的那条一个字没有。
# 所以先把点名的行捞出来，再补尾巴。
LOUD = ("FAILED ", "ERROR ", "**不合格**", "AssertionError", "Error:")
for r in bad:
    print(f"\n  ▸ {' '.join(r['argv'][1:])}")
    lines = ((r.get("stdout") or "") + (r.get("stderr") or "")).splitlines()
    named = [l for l in lines if any(k in l for k in LOUD)]
    for line in named[:12]:
        print(f"      {line}")
    if not named:
        for line in lines[-20:]:
            print(f"      {line}")
PY
  fail "发布门未通过（含全量测试）。完整报告：$GATE_REPORT"
fi
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
# **再查一次工作树——这一次是在演练跑完之后。**
#
# 2026-08-07：上面那道「工作树干净」在最开头就过完了，而随后的演练要跑五分钟，
# **每个演练自己会重打一次包**。我在那五分钟里改了 manifest，于是坏的那份被
# 打出来、同步上去，生产上摆了四十分钟一个打不开连接面板的扩展。
#
# 范围不能是整棵树——演练自己会写 evidence/*.json，那不算脏。
# 正好是**进镜像的那些输入**，而那份清单由 Dockerfile 现算，不在这里抄第二份。
INPUTS="$(.venv/bin/python scripts/does_this_deploy_need_a_rebuild.py --list-inputs)" \
  || fail '读不出镜像输入清单——那就无法判断演练期间有没有人动过它们。'
[[ -n "$INPUTS" ]] || fail '镜像输入清单是空的——**这不是「没有改动」**，是没数到。'
# shellcheck disable=SC2086
DIRTY_AFTER_DRILLS="$(git status --porcelain -- $INPUTS)"
[[ -z "$DIRTY_AFTER_DRILLS" ]] || fail "演练跑完之后，进镜像的这些文件被改过：
$DIRTY_AFTER_DRILLS
**扩展包是在这期间重打的**，它对应不上任何一个提交。先把树弄干净再部署。"
printf '  工作树干净；发布门通过；扩展包已重打；演练跑完后镜像输入仍未被动过。\n'

step "0.9) 硬闸：服务器上有没有国内平台的登录信息"
# 说明书里最重的那一句：「国内平台（B站、小红书、抖音、快手）的登录信息
# **永远不离开浏览器**，这一条是写死在代码里的」。
#
# 仓里为 INV-DOMESTIC-COOKIE-STAYS 立过好几道门——**全在扫代码**。
# 代码对不对，和**他那台服务器上此刻有没有**，是两个问题：一次误配、
# 一次手工导入、一个没删干净的旧版本，都能让第二个问题的答案变成「有」，
# 而所有扫代码的门照样全绿。
#
# **这一条是门不是播报**（其余三条生产侧检查都是播报）：那些答的是
# 「他那份数据长什么样」，而这一条答的是「最硬的那条承诺破了没有」。
# 破了就不该接着发别的东西——生产库的这个状态和本次部署无关，
# 所以查在最前面。
#
# 留一个绕行口，但**它必须被显式设置，而且会喊出来**：一个没法绕的硬闸
# 会逼人去改判据，那比绕行更坏。
if [ -z "${SA_ALLOW_DOMESTIC_CREDENTIAL_ON_SERVER:-}" ]; then
  .venv/bin/python scripts/check_no_domestic_cookie_reached_the_server.py --brief \
    || fail '服务器上存着国内平台的登录信息——这是对 Owner 最硬那条承诺的违反。先处理它再发布；确实要带着它发布请设 SA_ALLOW_DOMESTIC_CREDENTIAL_ON_SERVER=1（并说明为什么）。'
else
  printf '  ⚠️  跳过了「国内平台 Cookie 不出浏览器」这道硬闸（SA_ALLOW_DOMESTIC_CREDENTIAL_ON_SERVER）。\n'
fi

step "0.5) 前端资产的缓存戳，和内容对得上吗"
# **源站设 Cache-Control 治不了这件事**（同日实测）：
#   源站 127.0.0.1:18765  →  一个 cache-control 都没有
#   公网（经 Cloudflare） →  cache-control: max-age=14400
# 那 4 小时是 Cloudflare 的 Browser Cache TTL 加的，源站的头会被它盖掉。
# 所以换缓存键是唯一可靠的手段，而键必须永远等于内容的哈希——
# 改完 apps/pwa/ 忘了重新打戳，这一版就到不了他浏览器（最长 4 小时）。
if ! .venv/bin/python scripts/stamp_pwa_assets.py --check > /tmp/sa_stamp.$$ 2>&1; then
  python3 -c "
import json
try:
    d=json.load(open('/tmp/sa_stamp.$$'))
except Exception:
    print(open('/tmp/sa_stamp.$$').read()[-600:]); raise SystemExit
for p in d.get('problems', []): print('  ✗', p)"
  rm -f /tmp/sa_stamp.$$
  fail '前端资产的戳和内容对不上——先跑一次 scripts/stamp_pwa_assets.py 再部署。'
fi
python3 -c "
import json
d=json.load(open('/tmp/sa_stamp.$$'))
print(f\"  戳 {d['stamp_from_content']}（{len(d['hashed_files'])} 个资产的内容哈希），三处文件都对得上。\")"
rm -f /tmp/sa_stamp.$$

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
# **从 HEAD 的快照同步，不是从工作树**（2026-08-12）。
#
# 第 0 步查完「工作树干净」之后，还要跑 1767 条测试（约 2.5 分钟）
# ＋ 14 个演练（约 5 分钟）才走到这里——**每次部署都有 7–8 分钟的可写窗口**。
# 2026-08-12 我在这个窗口里改了两次工作树（两次都是 `.md`），
# 两次都是自己赶在 rsync 之前发现并挪走的：**靠的是记性，不是机制**。
#
# 早上给第 9 步加的「仓侧读 HEAD」挡不住这一类：它的 COMPARED 只看
# scripts/src/apps 下的 .py .sh .js .css .html .json，**`.md` 不在里面**。
# 一道防线挡不住立它的人当天犯的同一个错，就是没挡住。
#
# 从快照同步之后，「部署途中不许动工作树」就不再是一条要人记得的规矩，
# 而是一件做不到的事。
DEPLOY_SNAPSHOT="$(mktemp -d -t sa-deploy-snapshot)"

# **rsync 会把远端目录改成 700，而复原是后面一条顺序执行的命令。**（2026-08-14）
#
# 中间只要出一次错——rsync 部分成功后 `|| fail`、网络断、有人 Ctrl-C——
# 脚本就退出了，而 `/opt/social-archive` 停在 700。
# 后果不在这台机器上：备份和复制都以 `socialarchive` 用户跑，
# 700 之后连工作目录都进不去，**每次触发都是 200/CHDIR，直到下一次部署成功**。
#
# 这正是 2026-08-11（连着失败 108 次、28 小时）和 8/12～13（备份连着两天没做出快照）
# 那两次事故的机制。文档里一直写着「有人把 /opt/social-archive 改回 700」——
# **那个「有人」就是这个脚本。**
#
# 所以复原不能只放在正常路径上，要挂在 EXIT 上：无论怎么退出都跑一次。
# 幂等（chgrp/chmod 重复执行无副作用），所以正常路径那次照旧保留。
REMOTE_PERMS_TOUCHED=0
_restore_remote_perms() {
  [ "${REMOTE_PERMS_TOUCHED}" = "1" ] || return 0
  ssh -o ConnectTimeout=20 "$HOST" "sudo chgrp socialarchive '$REMOTE_DIR' &&
    sudo chmod 750 '$REMOTE_DIR'" >/dev/null 2>&1 \
    && printf '  （退出兜底）%s 的属组/权限已复原\n' "$REMOTE_DIR" \
    || printf '  ⚠ （退出兜底）复原 %s 的属组/权限失败——备份服务会进不去那个目录，请手工执行：\n    ssh %s "sudo chgrp socialarchive %s && sudo chmod 750 %s"\n' \
         "$REMOTE_DIR" "$HOST" "$REMOTE_DIR" "$REMOTE_DIR"
}
trap 'rm -rf "$DEPLOY_SNAPSHOT"; _restore_remote_perms' EXIT
# **必须从仓根跑，且子目录前缀要让 git 自己给。**
#
# 在 social-archive/ 里直接 `git archive HEAD:social-archive` 会报
# `fatal: current working directory is untracked`（实测 exit=128、0 字节）；
# 从仓根跑同一条命令取到 1118 个文件。今天第三次栽在「git 的路径有的按 cwd 算、
# 有的按仓根算」上（前两次是 `ls-tree` 相对 cwd、`log -- <path>` 相对 cwd），
# 所以这里两个都不写死。
DEPLOY_REPO_ROOT="$(git rev-parse --show-toplevel)" || fail '不在 git 仓里。'
DEPLOY_PREFIX="$(git rev-parse --show-prefix)"       # 形如 social-archive/
git -C "$DEPLOY_REPO_ROOT" archive "HEAD:${DEPLOY_PREFIX%/}" | tar -x -C "$DEPLOY_SNAPSHOT" \
  || fail '取 HEAD 快照失败。'
# `dist/` 被 gitignore，`git archive` 不会带它——而这一步末尾正好要比对
# 那个 zip 的 sha256。漏了它部署会当场红（红得对，但要先想到）。
mkdir -p "$DEPLOY_SNAPSHOT/dist"
cp dist/social-archive-extension.zip "$DEPLOY_SNAPSHOT/dist/" \
  || fail '快照里放不进扩展包。'
# 演练在第 0 步会**合法地**重写 evidence/**，那份要用工作树里的最新结果。
rsync -a --omit-dir-times evidence/ "$DEPLOY_SNAPSHOT/evidence/" 2>/dev/null || true
# **在 rsync 之前立标志，不是之后**：部分传输一样会把权限改掉，
# 而 `|| fail` 那一支根本走不到后面。
REMOTE_PERMS_TOUCHED=1
rsync -az --omit-dir-times \
  --exclude '.git' --exclude '.venv' --exclude 'node_modules' \
  --exclude 'runtime/' --exclude '.env' --exclude '__pycache__' \
  --exclude '.pytest_cache' --exclude '*.pyc' --exclude '.DS_Store' \
  "$DEPLOY_SNAPSHOT/" "$HOST:$REMOTE_DIR/" || fail 'rsync 失败。'

# **上面这一行每跑一次，就把他的备份复制打断一次。**（2026-08-13 查明）
#
# `DEPLOY_SNAPSHOT` 是 `mktemp -d` 建的——**权限 700**。而 `rsync -a` 含 `-p`
# （保留权限），`--omit-dir-times` **只省时间戳、不省权限**。于是 rsync 把
# 快照根目录那个 700 **盖到了 `/opt/social-archive` 上**。
#
# 后果不在这台机器上，在那台：`social-archive-replication.service` 以
# `socialarchive` 用户跑，700 之后它连工作目录都进不去，每次触发都是
# `200/CHDIR`。**实测代价：2026-08-11 23:53 起连着失败 108 次、28 小时，
# 而当时界面上一个字都没有**（那一格看的是"以前成功过没有"，不是"现在还在不在跑"）。
# 我当天上午手工修好，**当天下午又被自己的下一次部署改回去了**——
# 靠手工修一个每次部署都会重来的东西，是修不完的。
#
# 所以在这里把不变量放回去：属主不动，只让服务用户进得去（组内 r-x）。
# `runtime/secrets` 自己是 700 且属主是容器 uid，**不会因为这一步被放开**。
ssh -o ConnectTimeout=20 "$HOST" "
  sudo chgrp socialarchive '$REMOTE_DIR' &&
  sudo chmod 750 '$REMOTE_DIR'" \
  || fail "复原 ${REMOTE_DIR} 的属组/权限失败——备份服务会进不去那个目录。"

# **回读**：以那个用户真的进得去为准，不以「我发过那两条命令」为准。
ssh -o ConnectTimeout=20 "$HOST" "sudo -u socialarchive test -x '$REMOTE_DIR'" \
  || fail "备份服务那个用户仍然进不去 ${REMOTE_DIR}——复制/备份会每次都失败。"
printf '  %s 属组权限已复原（备份服务进得去；rsync -a 每次都会把它改回 700）\n' "$REMOTE_DIR"
# **改了名字的文件，上一版那个名字会一直赖在生产上。** rsync 只覆盖，不删除。
#
# 2026-08-12 实测：`git mv` 把两个修复脚本改了名，同步之后生产上新旧两份都在，
# 第 9 步「only_on_production —— 没人知道从哪来的代码正在生产上跑」当场打红。
# 打得对：从那一步看过去，它和「有人手工 scp 上去一个脚本」长得一模一样。
#
# **只对纯代码那三个目录开 --delete**。整个 $REMOTE_DIR 开 --delete 会连
# runtime/、密钥、他的数据一起抹掉——那三样本来就只在生产上有。
# 这三个目录恰好就是第 9 步比对的范围，所以「同步完还剩多余文件」这件事
# 从此不会再发生。开之前先 `--dry-run` 看过要删什么（只有那两个改名的）。
for code_dir in scripts src apps; do
  [[ -d "$DEPLOY_SNAPSHOT/$code_dir" ]] || continue
  rsync -az --omit-dir-times --delete \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
    "$DEPLOY_SNAPSHOT/$code_dir/" "$HOST:$REMOTE_DIR/$code_dir/" \
    || fail "清理 $code_dir 下的残留文件失败。"
done
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
# **drop-in 也要比**（2026-08-10）。
#
# 这一步原来只 glob `*.service` 和 `*.timer`，而 systemd 还认
# `<unit>.d/*.conf`——**drop-in 能改 ExecStart**，也就是能改这个服务到底跑什么。
#
# 今天在他生产上撞见的就是这个：
#     /etc/systemd/system/social-archive-backup.service.d/20-prune-r2-replicas.conf
# 一个**任何仓里都没有**的文件，往备份服务里挂了一条
# `prune_r2_backup_replicas.py --apply`——**对他 R2 备份做真删除**，
# 三天里跑过 6 次。而这一步照报「所有 systemd 单元与仓里一致」。
#
# 那个删除本身是对的（Owner 2026-08-10 定的 R2 只留 3 天，脚本先核 OCI 同 key
# 同大小才删、最新一批永不删、不碰 primary-objects）。**问题不是它做了什么，
# 是它从版本控制之外做的**：主机一旦重建，这条就无声消失。
# 现在 .conf 已收进 deploy/systemd/<unit>.d/，并且这里会盯着它。
DRIFT=""
UNREACHED=""
ABSENT=""
for unit in deploy/systemd/*.service deploy/systemd/*.timer deploy/systemd/*.d/*.conf; do
  [[ -e "$unit" ]] || continue
  case "$unit" in
    # drop-in 的目标路径要连它的 .d 目录一起，basename 不够。
    # **第一版这里写成 `*/deploy/systemd/*.d/*`，配不上**——`$unit` 是相对路径
    # （`deploy/systemd/…`），开头那个 `*/` 让它整条不匹配，于是掉进 basename，
    # 目标算成了 `/etc/systemd/system/20-prune-r2-replicas.conf`。
    # 把 glob 打印出来看一眼就露了；不看就是一道永远比对不存在文件的门。
    deploy/systemd/*.d/*) name="$(basename "$(dirname "$unit")")/$(basename "$unit")" ;;
    *) name="$(basename "$unit")" ;;
  esac
  # **`ssh` 非零有两种完全不同的含义，第一版把它们并成了一支。**（2026-08-13）
  #
  # 那天部署到这一步撞上两次 `ssh_dispatch_run_fatal: Operation timed out`，
  # 于是这里报「这两个 unit 与仓里不一致」并**中止了部署**——而它俩逐字节一致
  # （当场 `sudo cat` 下来 diff 过）。两次超时，正好两个"漂移"，一一对应。
  # 更坏的是它给出的处置：那行 `sudo cp …` 会去"修"一个不存在的问题。
  #
  # `ssh` 回的是**远端命令的退出码**，除非 ssh 自己失败——那时它回 255：
  #   0    两份一样
  #   1    远端 diff 说不一样   ← 真漂移
  #   2    diff 打不开文件      ← unit 压根没装（要说，但不是同一件事）
  #   255  ssh 没连上           ← **不知道**，不许记成漂移
  #
  # （那台机器上还有别的项目在定时 ssh，抢连接是常态，不是一次性意外。）
  ssh -o ConnectTimeout=20 "$HOST" \
    "sudo diff -q /etc/systemd/system/${name} ${REMOTE_DIR}/${unit} >/dev/null 2>&1"
  case "$?" in
    0)   ;;
    1)   DRIFT="${DRIFT}  ${name}\n" ;;
    255) UNREACHED="${UNREACHED}  ${name}\n" ;;
    *)   ABSENT="${ABSENT}  ${name}\n" ;;
  esac
done
if [[ -n "$UNREACHED" ]]; then
  # **「没查成」和「查了没问题」必须分开说**——这一步原来只会说后者。
  printf '  **这几个 unit 这次没比成**（ssh 连不上；既不是「不一致」，也不是「一致」）：\n'
  printf "$UNREACHED"
  fail 'systemd 单元这一步没查成——网络不通时不许把「不知道」当成「漂移」，也不许当成「一致」。等网络稳了重跑。'
fi
if [[ -n "$ABSENT" ]]; then
  printf '  **这几个 unit 在生产上根本没装**（不是内容不一致）：\n'
  printf "$ABSENT"
  printf '  装它们（unit 以 root 跑，所以由你来敲）：\n'
  printf "    ssh %s 'sudo cp %s/deploy/systemd/{%s} /etc/systemd/system/ && sudo systemctl daemon-reload'\n" \
    "$HOST" "$REMOTE_DIR" "$(printf "$ABSENT" | tr -d ' ' | paste -sd, -)"
  fail 'systemd 单元缺失。仓里有、生产上没有——那条链根本没在跑。'
fi
if [[ -n "$DRIFT" ]]; then
  printf '  **这些 systemd 单元与仓里的不一致**（装着的是旧的）：\n'
  printf "$DRIFT"
  printf '  同步它们（unit 以 root 跑，所以由你来敲）：\n'
  printf "    ssh %s 'sudo cp %s/deploy/systemd/{%s} /etc/systemd/system/ && sudo systemctl daemon-reload'\n" \
    "$HOST" "$REMOTE_DIR" "$(printf "$DRIFT" | tr -d ' ' | paste -sd, -)"
  fail 'systemd 单元有漂移。改了 unit 而不装上去，跑的还是旧的——而 systemctl 照样报 success。'
fi
printf '  所有 systemd 单元与仓里一致。\n'

step "3.6) 我要部署的这台，是不是他打得到的那台"
# **2026-08-10 之前没有这一步，代价是一天三次部署一次都没到他手上。**
#
#     从 Owner 的 Mac 打公开域名 → 0.0.0.25，disk.total 95.82G
#     ssh 到这里打回环           → 0.0.0.27，disk.total 38.00G
#
# 同一个域名两台机器。而第 7 / 8 / 8.5 步那些「验收生产」**全站在这台机器上**，
# 打的是它自己的回环——对「域名指到别处」结构上就是瞎的。
#
# 这一步必须在**本机**跑（不是 ssh 过去跑）：它要的就是「他所在的位置」那个视角。
# 排在构建之前——建完一个镜像才发现部署错机器，那一趟全白跑。
if ! .venv/bin/python scripts/check_i_am_deploying_to_the_machine_he_reaches.py \
      --host "$HOST" > /tmp/sa_same_machine.$$ 2>&1; then
  cat /tmp/sa_same_machine.$$ | sed 's/^/  /'
  rm -f /tmp/sa_same_machine.$$
  fail '部署目标和他真正连到的那台对不上（或判不了）——先把这件事弄清楚再部署。'
fi
sed -n 's/.*"message_zh": "\(.*\)".*/  \1/p' /tmp/sa_same_machine.$$ | head -1
rm -f /tmp/sa_same_machine.$$

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
if (( NEEDS_REBUILD == 1 )) && [[ -n "${SOCIAL_ARCHIVE_DEPLOY_BUILD_LOCALLY:-}" ]]; then
  # **本机构建这条路不在主机上产生构建缓存**，主机只多出一个镜像。
  # 所以这里不用那道「至少 5G」的门——它量的是「主机构建」的开销
  # （实测一次部署吃掉 2.12G：层 + 构建缓存）。
  # **门没有拆，是挪到了知道确切数字的地方**：第 5 步 docker save 出来之后
  # 按 tar 的实际大小算 `可用 > 镜像 × 3 + 512M`，再决定放不放行。
  printf '  本机构建：主机不构建、不产生构建缓存，只多一个镜像。\n'
  printf '  磁盘门挪到第 5 步（按 docker save 出来的实际大小算，那时才有确切数字）。\n'
  printf '  当前可用 %sG。\n' "$(show_gb "$(free_kb)")"
elif (( NEEDS_REBUILD == 1 )); then
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
  # **`df` 那个 RECLAIMABLE 会骗人。**（2026-08-10）
  #
  # 它把「没有容器在用」的镜像全算进去，**包括还带着 tag 的**；
  # 而 `docker image prune -f` 只删**没有 tag** 的那些。
  # 那天实测：df 报 RECLAIMABLE 4.314GB，真正悬空的只有 2 个共 148MB，
  # 剩下 4.1G 全在一个带 tag 的镜像上（`jobhuntbot-online-acceptance:0.3.0` 3.97GB，
  # 没有任何容器在用）。
  #
  # **我照着那个 4.3GB 连着三次向 Owner 推荐 `docker image prune -f`——它收不到那些。**
  # 指错方向的建议比不给建议更费人：他照做、没效果、再回来问。
  # 所以这里把「大而闲」的镜像点名列出来，并给出可以直接跑的那条命令。
  printf '    没有容器在用、但还带着 tag 的大镜像（**prune -f 收不到它们**，要点名删）：\n'
  ssh -o ConnectTimeout=25 "$HOST" 'sudo docker images --format "{{.Repository}}:{{.Tag}}|{{.ID}}|{{.Size}}" 2>/dev/null \
     | sort -t"|" -k3 -rh | head -8 \
     | while IFS="|" read -r name id size; do
         users=$(sudo docker ps -a --filter "ancestor=$id" --format "{{.Names}}" 2>/dev/null | tr "\n" " ")
         if [ -z "$users" ] && [ "${name#social-archive/}" = "$name" ]; then
           printf "      %-46s %-8s  sudo docker rmi %s\n" "$name" "$size" "$name"
         fi
       done' 2>/dev/null || true
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
if [[ -n "${SOCIAL_ARCHIVE_DEPLOY_BUILD_LOCALLY:-}" ]]; then
  # **在本机构建，把镜像整个送过去。**（2026-08-10）
  #
  # 为什么要有这条路：主机 38G 的盘 97% 满，剩下的大头是**别的项目**的镜像
  # （jobhuntbot-online-acceptance:0.3.0，3.97GB，没有容器在用）。
  # 我不动别人的东西，而我自己全部占用加起来才 437M——**清干净也到不了 5G**。
  # 于是所有服务端修复（包括「20 次同步 0 次 completed」那个根因）全推不上去。
  #
  # 本机构建对主机的开销只有「多一个镜像」：没有构建上下文、没有中间层、
  # 没有构建缓存。代价是本机得跨架构（本机 arm64 / 主机 amd64），走模拟。
  LOCAL_ARCH="$(docker version --format '{{.Server.Arch}}' 2>/dev/null || echo unknown)"
  HOST_ARCH="$(ssh -o ConnectTimeout=20 "$HOST" "docker version --format '{{.Server.Arch}}'" || echo unknown)"
  printf '  本机 %s，主机 %s；按 linux/%s 构建。\n' "$LOCAL_ARCH" "$HOST_ARCH" "$HOST_ARCH"
  [[ "$HOST_ARCH" == "unknown" ]] && fail '读不出主机架构——构建出来的镜像可能跑不了，不赌。'
  # **成败不接管道。**（这个仓栽过两次：`| tail` 之后 `||` 看的是 tail 的退出码，
  # 一次让我提交了一个红的判据，一次让通知报 exit 0 而部署已中止。）
  BUILD_LOG="$(mktemp -t sa-build).log"
  if ! docker buildx build --platform "linux/${HOST_ARCH}" -t "$IMAGE" --load . >"$BUILD_LOG" 2>&1; then
    tail -12 "$BUILD_LOG" | sed 's/^/    /'
    rm -f "$BUILD_LOG"
    fail '本机构建失败，什么都没换，回滚点原样保留。'
  fi
  tail -2 "$BUILD_LOG" | sed 's/^/    /'
  rm -f "$BUILD_LOG"
  # **先在本机起一次，起不来就别送。**（2026-08-10 抓到过一次 import 就死的）
  BOOT="sa-preflight-$$"
  docker rm -f "$BOOT" >/dev/null 2>&1 || true
  docker run -d --name "$BOOT" --platform "linux/${HOST_ARCH}" \
    -e SOCIAL_ARCHIVE_DATA_ROOT=/tmp/sadata -e SOCIAL_ARCHIVE_API_TOKEN=preflight \
    "$IMAGE" social-archive-api >/dev/null 2>&1 || fail '新镜像连容器都起不来，不送。'
  BOOT_OK=""
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if docker exec "$BOOT" curl -fsS http://127.0.0.1:8765/health >/dev/null 2>&1; then BOOT_OK=1; break; fi
    sleep 3
  done
  if [[ -z "$BOOT_OK" ]]; then
    printf '  新镜像起不来，日志尾：\n'; docker logs "$BOOT" 2>&1 | tail -6 | sed 's/^/    /'
    docker rm -f "$BOOT" >/dev/null 2>&1 || true
    fail '新镜像在本机就起不来（/health 不通）——绝不送上生产。'
  fi
  docker rm -f "$BOOT" >/dev/null 2>&1 || true
  printf '  本机预检：容器起得来、/health 通。\n'
  # 送之前按**实际大小**核磁盘——第 4 步那道门就是挪到这里的
  IMAGE_TAR="$(mktemp -t sa-image).tar"
  docker save --platform "linux/${HOST_ARCH}" "$IMAGE" -o "$IMAGE_TAR" || fail '导出镜像失败。'
  TAR_KB=$(( $(wc -c < "$IMAGE_TAR") / 1024 ))
  FREE_KB="$(free_kb)"
  # **门槛用同一个名字（MIN_FREE_KB），演练才抬得动它。**
  # 这条路的门槛是**量出来的**（镜像实际多大就要多大 + 余量），不是写死的 5G
  # ——5G 量的是「主机构建」的开销（层 + 构建缓存，实测一次 2.12G），
  # 而本机构建在主机上只多一个镜像。但如果有人显式设了更高的门槛
  # （SOCIAL_ARCHIVE_DEPLOY_MIN_FREE_GB，演练就是靠它把「磁盘不够 → 中止」
  # 那条路真的走一遍），取高的那个——**开关只能往更严那一侧拨。**
  DERIVED_KB=$(( TAR_KB * 3 + 524288 ))
  # **只认「显式设过」的那个门槛，不认默认值。**（2026-08-10 当场栽了一次）
  # 上一版写的是 `if (( MIN_FREE_KB > DERIVED_KB ))`——而 MIN_FREE_GB 默认就是 5，
  # 于是「取高的那个」永远取到 5G，按镜像算出来的 0.82G 一次都用不上：
  # **这条本机构建的路从第一次跑起就是恒中止的**，而它存在的全部理由
  # 就是绕开那个 5G。这就是「阈值高过天花板 → 恒红」，这个仓记过一次。
  if [[ -n "${SOCIAL_ARCHIVE_DEPLOY_MIN_FREE_GB:-}" ]] && (( MIN_FREE_KB > DERIVED_KB )); then
    printf '  门槛按人为设定的 %sG 算（比按镜像算出来的 %sG 高）。\n' \
      "$MIN_FREE_GB" "$(show_gb "$DERIVED_KB")"
  else
    MIN_FREE_KB=$DERIVED_KB
  fi
  printf '  镜像 %sG，主机可用 %sG，门槛 %sG（镜像×3 + 512M 余量）\n' \
    "$(show_gb "$TAR_KB")" "$(show_gb "$FREE_KB")" "$(show_gb "$MIN_FREE_KB")"
  if [[ -n "$FREE_KB" && "$FREE_KB" -lt "$MIN_FREE_KB" ]]; then
    rm -f "$IMAGE_TAR"
    fail "主机放不下这个镜像（可用 $(show_gb "$FREE_KB")G < 门槛 $(show_gb "$MIN_FREE_KB")G）。什么都没换。"
  fi
  printf '  送过去并 load…\n'
  # 同上：**不接管道判成败**。gzip/ssh 的状态用 PIPESTATUS 单独看（这是 bash）。
  LOAD_LOG="$(mktemp -t sa-load).log"
  gzip -1 -c "$IMAGE_TAR" | ssh -o ConnectTimeout=60 "$HOST" 'gunzip | sudo docker load' >"$LOAD_LOG" 2>&1
  LOAD_STATUS=("${PIPESTATUS[@]}")
  if [[ "${LOAD_STATUS[0]}" != "0" || "${LOAD_STATUS[1]}" != "0" ]]; then
    tail -8 "$LOAD_LOG" | sed 's/^/    /'
    rm -f "$IMAGE_TAR" "$LOAD_LOG"
    fail "送过去 load 失败（gzip=${LOAD_STATUS[0]} ssh=${LOAD_STATUS[1]}），什么都没换，回滚点原样保留。"
  fi
  tail -2 "$LOAD_LOG" | sed 's/^/    /'
  rm -f "$LOAD_LOG"
  rm -f "$IMAGE_TAR"
  # **回读：主机上那份必须和本机这份装着同样的东西。**
  #
  # 第一版比的是 `docker image inspect -f '{{.Id}}'`——**那个不能跨镜像库比**。
  # 本机 Docker Desktop 用 containerd 镜像库、主机用经典 daemon，
  # 同一份内容 load 完两边报的摘要就是不一样的：
  #
  #     本机 sha256:3e44f2cd…  主机 sha256:bc751892…
  #
  # 于是部署在「镜像已经送到、Loaded image 打出来了」之后被自己的判据拦下。
  # **不是内容不对，是我拿两把不同的尺子在比。**
  #
  # 改成比内容：两边各在镜像里算一次 /app 的哈希。
  # `-print0`/`sort -z`/`xargs -0` 是必须的——`scripts/同步到 Obsidian.command`
  # 文件名里有空格，用普通 xargs 会把它拆成两段、两边一起静默跳过，
  # **比出来仍然相等，但那是巧合式的相等**（第一次手工核对就撞上了这个）。
  APP_DIGEST_CMD='find /app -type f -not -path "*/__pycache__/*" -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d" " -f1'
  LOCAL_APP="$(docker run --rm --platform "linux/${HOST_ARCH}" "$IMAGE" sh -c "$APP_DIGEST_CMD")"
  REMOTE_APP="$(ssh -o ConnectTimeout=60 "$HOST" "sudo docker run --rm '$IMAGE' sh -c '$APP_DIGEST_CMD'")"
  [[ -n "$LOCAL_APP" && "$LOCAL_APP" == "$REMOTE_APP" ]] \
    || fail "主机上那个镜像装的东西和本机这份不一样（本机 ${LOCAL_APP}，主机 ${REMOTE_APP}）。"
  printf '  已核对：主机镜像里的 /app 与本机构建的逐字节相同（%s）。\n' "${LOCAL_APP:0:16}"
  # **cli-tools 那个镜像不重造，但 compose 里的 tag 跟着版本号变了。**
  #
  # core-worker `depends_on: cli-tools`，所以 `up -d core-api core-worker`
  # 会把 cli-tools 一起带上；compose 看到 image 从 :0.0.0.25 变成 :0.0.0.26
  # 就要去建——那正是这条路要绕开的（主机盘不够，而它是个 994MB 的镜像）。
  #
  # 内容没变的话，给**同一个镜像**加一个新标签就够了：零字节、零构建，
  # 而且不是糊弄——第 5.5 步比的就是内容哈希，它照跑。
  # **哈希不同就当场停**：那种情况必须真重建，这条路覆盖不了，
  # 不许悄悄用旧内容顶着一个新版本号。
  SIDE_LOCAL="$(cat sidecars/cli-tools/server.py sidecars/cli-tools/Dockerfile | shasum -a 256 | cut -d' ' -f1)"
  SIDE_REMOTE="$(ssh -o ConnectTimeout=20 "$HOST" "sudo docker exec social-archive-cli-tools-1 sh -c 'cat /worker/server.py /worker/Dockerfile.built 2>/dev/null | sha256sum' 2>/dev/null | cut -d' ' -f1" || true)"
  SIDE_IMAGE="social-archive/cli-tools:${VERSION}"
  if ssh -o ConnectTimeout=20 "$HOST" "docker image inspect '$SIDE_IMAGE' >/dev/null 2>&1"; then
    printf '  %s 已经在主机上。\n' "$SIDE_IMAGE"
  elif [[ -n "$SIDE_REMOTE" && "$SIDE_LOCAL" == "$SIDE_REMOTE" ]]; then
    RUNNING_SIDE="$(ssh -o ConnectTimeout=20 "$HOST" "docker inspect social-archive-cli-tools-1 --format '{{.Image}}'")"
    ssh -o ConnectTimeout=20 "$HOST" "docker tag '$RUNNING_SIDE' '$SIDE_IMAGE'" \
      || fail "给 cli-tools 打新版本标签失败。"
    printf '  cli-tools 内容与仓一致（%s），给在跑的那个镜像加上 %s 标签（零字节，不重建）。\n' \
      "${SIDE_LOCAL:0:12}" "$SIDE_IMAGE"
  else
    fail "cli-tools 的内容和仓里不一样（容器 ${SIDE_REMOTE:0:12}，仓里 ${SIDE_LOCAL:0:12}），而本机构建这条路只送 core。它得真重建（约 994MB），主机盘现在放不下。要么先腾出空间走主机构建，要么单独把 cli-tools 也在本机构建后送过去。"
  fi
else
# **管道写在 ssh 的引号里，ssh 的退出码就是 `tail` 的。**（2026-08-10 修）
# 也就是说主机构建失败时这一行照样 exit 0，`|| fail` 永不触发，
# 部署接着往下走、用**旧镜像** `up -d`，最后报「成功」。
# 这个仓已经栽过两次同形状的（提交了一个红判据；通知报 exit 0 而部署已中止）。
HOST_BUILD_LOG="$(mktemp -t sa-hostbuild).log"
if ! ssh -o ConnectTimeout=20 "$HOST" "cd '$REMOTE_DIR' && docker compose build core-api" \
     >"$HOST_BUILD_LOG" 2>&1; then
  tail -12 "$HOST_BUILD_LOG" | sed 's/^/    /'
  rm -f "$HOST_BUILD_LOG"
  fail '构建失败，什么都没换，回滚点原样保留。'
fi
tail -3 "$HOST_BUILD_LOG" | sed 's/^/    /'
rm -f "$HOST_BUILD_LOG"
fi
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

step "8.2) 验收：他下载到的那个包，是不是 HEAD 里那份代码"
# **上面那一步比的是「服务器上的 zip」对「我这台机器上的 zip」——
# 两个一样坏的东西比起来是一致的。**
#
# 2026-08-07 真的发生了：生产上摆了约四十分钟一个 `host_permissions` 缺了
# 后端域名的包，插件够不着 API，连接面板显示「读不到可连接的来源」，
# 一颗按钮都没有——正是 Owner 说的「点了没反应」。来路是部署在后台跑时
# 工作树被改了：第 0 步的「工作树干净」闸在最开头就过完了，而随后
# `run_all_drills` 跑五分钟，**每个演练自己会重打一次包**。
#
# 第 8 步照样报「逐字节一致」，因为两边都是那份坏的。要比的必须是一个
# **它证不了自己**的东西：git 里那个提交。
.venv/bin/python scripts/check_the_shipped_package_is_the_committed_code.py --brief \
  || fail "他能下载到的包和 HEAD 不是同一份。生产上摆着一份没有对应提交的代码——这一步不能放过。"

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
  # **别把诊断丢进 /dev/null。**
  #
  # 2026-08-07 这一步红了一次，而部署只说得出「够不着生产」——因为我把演练的
  # 输出重定向掉了。**说不出原因的告警和指错原因的告警一样费人**，
  # 而这正是我一整天在修的那种病，又出在我自己新加的步骤里。
  #
  # 重试一次，但**重试要说出来**：静默重试等于把不稳定藏起来。
  # 那一次重跑就过了（api 1032ms），所以它是瞬时的——可瞬时不等于不存在。
  DRILL_OUT="$(mktemp -t sa-reach)"
  if ! .venv/bin/python scripts/production_reachability_drill.py > "$DRILL_OUT" 2>&1; then
    printf '  第一次没过，10 秒后重试一次（**这次重试本身就是要报告的事**）…\n'
    .venv/bin/python -c 'import time; time.sleep(10)'
    if ! .venv/bin/python scripts/production_reachability_drill.py > "$DRILL_OUT" 2>&1; then
      printf '  演练报的问题：\n'
      .venv/bin/python -c '
import json, sys
try:
    payload = json.load(open(sys.argv[1]))
except Exception:
    print("    （输出不是 JSON，原样贴前 400 字）")
    print("   ", open(sys.argv[1]).read()[:400].replace("\n", " "))
else:
    for item in payload.get("problems") or ["（它没说出是哪一条——那本身是缺陷）"]:
        print(f"    · {item}")
' "$DRILL_OUT"
      fail "装上发布包的真 Chrome 够不着生产。**这是 Owner 那边「点了没反应」的形状**。"
    fi
    printf '  **重试后过了**——这一版有瞬时的够不着，记下来，别当没发生。\n'
  fi
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

step "8.8) 读一眼：产品对他那份数据说的话对不对"
# 2026-08-07 这一天在他的生产数据上查出十处缺陷，**没有一处被那 1190 条测试和
# 31 道发布门抓到**——它们全在问「机制对不对」，而这十处问的是
# **「产品对他这份数据说的话对不对」**（三个账号断开了却说"还没有连接"、
# 33 条视频被挡却标"完整"、状态页把内部码印给他看…）。
#
# **是播报不是门**：他那份数据长什么样不是部署的属性。
.venv/bin/python scripts/audit_production_against_the_product.py --brief 2>/dev/null \
  || printf '  读不到审计结果（不影响部署）\n'

step "8.87) 读一眼：自动聚合还在跑吗（不是「能不能跑」，是「还在不在跑」）"
# 他要的第一件事是「多平台聚合真的发生」。而这个仓验它的方式一直是**演练**：
# 在真 Chrome 里点一遍、看见条目进来、判据变绿——那证的是**按钮按得动**。
#
# 这两件事分开过一次：8/3 那晚真进了 260 条，8/4 起就停了，而 31 道门
# 一处都没抓到，因为门全在验机制，没有一个去问「后来还在跑吗」。
# 2026-08-13 这一步建起来之前，仓里**没有任何东西读
# `user_relation.last_sync_run_id`**——「哪些条目是自动抓进来的」谁都没问过。
#
# **是播报不是门**：他没连账号、或者主动断开了，都是正常状态，不该让部署红。
# 要当门用给 `--require-recent-success DAYS`（必须自己给天数，没有默认值）。
aggregation_rc=0
.venv/bin/python scripts/did_aggregation_actually_happen.py \
  --host "$HOST" --brief 2>/dev/null || aggregation_rc=$?
if [[ $aggregation_rc -ne 0 ]]; then
  printf '  读不到同步台账（不影响部署）\n'
fi

step "8.86) 读一眼：他按过那颗诊断按钮没有"
# 说明书请他做一件事：在抖音收藏页按一次诊断按钮。按下去之后地址和字段骨架都落在
# 他自己的服务器上——**而在这一步之前，没有任何东西会告诉我他按过了**，
# 我得记得自己去翻。「机制建好了、没人去看」这次断在我这一头：
# 他做完了他那一份，而我不知道。
#
# **是播报不是门**：他还没按是完全正常的状态，不该让部署红。
diagnosis_rc=0
.venv/bin/python scripts/read_what_his_diagnosis_left_behind.py \
  --host "$HOST" --brief 2>/dev/null || diagnosis_rc=$?
if [[ $diagnosis_rc -ne 0 ]]; then
  printf '  读不到诊断台账（不影响部署）\n'
fi

step "8.85) 读一眼：有没有哪一类收藏，取回来的整类都缺作者"
# 2026-08-12：他库里抖音 54 条缺作者。**整体口径看不见问题**——31 条有、54 条没有，
# 同一条取数路，看起来像"有时取得到"。按 `平台 × 关系` 拆开，形状立刻变了：
#
#     douyin  favorite   16 条，**0 条有作者**
#     douyin  like       69 条，31 条有作者
#
# 收藏夹那一类是**整类为零**，不是概率。而抖音**只同步 favorite 这一类**——
# 他连上抖音之后新进来的每一条，作者栏都会是空的。**比例掩盖了分类。**
#
# **是播报不是门**（和 8.8 同理）：他那份数据长什么样不是部署的属性，
# 而且这条在他重连、或取数侧拿到一份真实响应之前变不绿——
# 一个永远变不绿的红不是信号。
# **退出码 4 是「量到了，而且有问题」**，不是「没量到」。
# 第一版写的是 `|| printf '读不到分组结果'`——于是它先把问题原原本本印出来，
# 紧接着又说自己读不到，**同一屏里两句话互相矛盾，后一句是假的**。
# 这正是这个项目一路在拔的那种东西，别在新加的一步上又种一个。
# **`|| 赋值` 不能省。** 这个脚本开着 `set -e`：把命令单独一行写、下一行再读 `$?`，
# 那一行非零时脚本当场就退了。第一次这样写，8.85 直接把部署掐断在这里，
# 后面 8.9 / 8.55 / 8.6 / 8.66 / 8.68 / 第 9 步验收**一个都没跑**——
# 一个「播报」步骤杀掉了整场部署，比它原来那句假话严重得多。
relation_author_rc=0
.venv/bin/python scripts/check_a_relation_never_loses_the_author.py \
  --host "$HOST" --brief 2>/dev/null || relation_author_rc=$?
# 退出码 4 是「量到了，而且有问题」，不是「没量到」——两者要分开说。
if [[ $relation_author_rc -ne 0 && $relation_author_rc -ne 4 ]]; then
  printf '  读不到分组结果（不影响部署）\n'
fi

step "8.9) 读一眼：「加密存三份」今天真的确认了几份"
# 说明书对他说「数据存在哪？你自己的服务器上，**加密存三份**」。
# 而库里那三行 `verified` 是**写入当时**的记录，不是今天的事实。
#
# 2026-08-07 第一次真问：r2 在、oci 在、**github 读不到**——
# 而 GitHub 正是 2026-08-04 迁移之后当主备份的那一份。
#
# **是播报不是门**：一份备份存储暂时够不着，不该卡住一个界面修复的上线；
# 做成门只会逼人绕过去。但它必须每次都说出来，不能再是隐形的假设。
.venv/bin/python scripts/check_the_three_copies_are_really_there.py --sample 2 --brief 2>/dev/null \
  || printf '  ↳ 上面这行不是绿的：目标是三份，今天没确认满。**先别当成能力问题**——2026-08-11 那次「差的是能力」查下来是判据自己测错了（拿错令牌＋比错快照）。先看 evidence/G5/THREE_COPIES_TODAY.json 里每一家的 error_code。说明书写的是**实测数**\n     （发布门那条规则逼两边相等），所以他读到的不假——差的是能力本身。\n'

step "8.55) 一个**真平台**的收藏，真的进到档案馆里吗"
# Owner 那句话的第一条是「至少一个真实平台的收藏能自动读进档案馆」。
# 在这一步之前，仓里两个演练**各证一半、从来没接起来过**：
#   bilibili_acquisition_drill  打 B 站真接口证明「读得到」——全文 0 次 POST
#   from_zero_drill             整条链走通证明「进得去」——而它连的是自己写的假站
# 两个都绿，合起来仍然答不了那句话。
#
# 这一步走完整条：B 站公开收藏夹（**不带登录态、不粘 Cookie**）→ 插件自己的
# readFolder → POST /v1/captures/batch → 从库里**按标题**读回来。
# 档案馆起在一次性容器的 tmpfs 上，**他那份库一个字节都不动**（跑完实测过 193 条没变）。
# 按铁律 7：B 站是公开 REST、无签名、零费用；档案馆那头全在容器内，**月操作量 0**。
if ! .venv/bin/python scripts/real_platform_into_archive_drill.py --version "$VERSION" \
      > evidence/G1/REAL_PLATFORM_INTO_ARCHIVE.json 2>&1; then
  python3 -c "
import json
try:
    d=json.load(open('evidence/G1/REAL_PLATFORM_INTO_ARCHIVE.json'))
except Exception:
    print(open('evidence/G1/REAL_PLATFORM_INTO_ARCHIVE.json').read()[-600:]); raise SystemExit
for s in d.get('steps', []):
    if not s['ok']: print('  ✗', s['step'], '→', str(s['measured'])[:160])
for p in d.get('problems', []): print('  ✗', p[:200])"
  if grep -q NO_LIVE_ITEMS evidence/G1/REAL_PLATFORM_INTO_ARCHIVE.json 2>/dev/null; then
    fail 'B 站那头没读到东西——先看这台机器到不到得了 api.bilibili.com，再怀疑产品。'
  fi
  fail '真平台的收藏进不了档案馆——**这正是他要的第一条**，比任何界面问题都要紧。'
fi
python3 -c "
import json
d=json.load(open('evidence/G1/REAL_PLATFORM_INTO_ARCHIVE.json'))
print(f\"  从 B 站公开收藏夹「{d['folder_title']}」真读到 {d['items_read_from_the_real_platform']} 条，\"
      f\"全部进了档案馆并按标题读回来了（不带登录态、他的库没动）。\")
print('  边界：只证明 bilibili 一个平台——别的平台要登录态，只能发生在他自己的浏览器里。')"

step "8.6) 从他所在的位置回读：公开域名跑的是不是刚部署的这一版"
# **在这之前，所有「回读生产」都是 ssh 到目标机器上打它自己的回环。**
# 那证明不了他打开产品时看到的是新版——2026-08-10 的代价是三次部署零次到达
# （同一个域名背后两台机器，他连的是另一台）。
#
# 这一步在**本机**跑，打的是他会打的那个地址，要的就是他那个视角。
if ! .venv/bin/python scripts/check_i_am_deploying_to_the_machine_he_reaches.py \
      --host "$HOST" --expect-version "$VERSION" > /tmp/sa_public_ver.$$ 2>&1; then
  cat /tmp/sa_public_ver.$$ | sed 's/^/  /'
  rm -f /tmp/sa_public_ver.$$
  fail '公开域名上跑的不是刚部署的这一版——在他那边这次部署等于没发生。'
fi
sed -n 's/.*"message_zh": "\(.*\)".*/  \1/p' /tmp/sa_public_ver.$$ | head -1
rm -f /tmp/sa_public_ver.$$

step "8.56) 说明书第一步让他打开的那个地址，会不会先弹一屏它没提过的验证"
# 另一道门（check_the_guide_matches_the_product.py）查的是**正方向**：
# 说明里写的东西真的存在。它查不到反方向——**真实存在、而说明里没有**。
# 两个方向漏一个，说明书就可以靠「少说」永远绿。
#
# 2026-08-12 实测就漏在第一步：说明让他打开 social-archive.linzezhang.com，
# 而没有会话时它先 302 到 Cloudflare Access 的登录页，说明书一个字没提。
# 他自己的浏览器有会话看不见，换台机器第一步就卡在一个没写过的页面上。
if ! .venv/bin/python scripts/check_the_guide_warns_about_the_access_gate.py \
      > evidence/G4/GUIDE_WARNS_ABOUT_THE_GATE.json 2>&1; then
  python3 -c "
import json
try:
    d=json.load(open('evidence/G4/GUIDE_WARNS_ABOUT_THE_GATE.json'))
except Exception:
    print(open('evidence/G4/GUIDE_WARNS_ABOUT_THE_GATE.json').read()[-400:]); raise SystemExit
for p in d.get('problems', []): print('  ✗', p[:220])"
  fail '说明书第一步和他真会撞到的那一屏对不上——**少说也是说错**。'
fi
python3 -c "
import json
d=json.load(open('evidence/G4/GUIDE_WARNS_ABOUT_THE_GATE.json'))
print(f\"  说明书第一步那个地址：{d['guide_first_url']}；\"
      + ('挡在 Access 后面，说明书也确实提了那一屏。' if d['guide_mentions_the_gate']
         else '没挡，说明书也没写多余的提醒。'))"

step "8.65) 他打得到的那份前端，真 Chrome 里画不画得出这次发的东西"
# **第 8.6 步只核了 /health 报的版本号。** 那是后端。
# 前端是另一条路，而它有自己的一层缓存：
#
#   2026-08-11 实测——0.0.0.29 明明部署成功、/health 也报 0.0.0.29，
#   而从这台 Mac 上按普通方式取 /assets/app.js 拿到的是 137559 字节的旧文件
#   （容器里 140335、cf-cache-status: HIT、age: 3794、max-age=14400）。
#   那份旧文件里**一颗「删除并清空」都没有**。他刷新四小时都看不到这次的改动。
#
# 所以这一步：按浏览器的走法从公开域名取前端（先首页、再按首页里那几个 ?v= 键
# 逐个取），喂给真 Chrome，把 DOM 读回来。**验的是他真会拿到的那些字节。**
# 接口是假的——这里不证明服务端对，只证明界面到得了他手上、按得下去。
if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
  if ! .venv/bin/python scripts/forget_button_render_drill.py > evidence/G3/FRONT_END_REACHES_HIM.json 2>&1; then
    python3 -c "
import json,sys
try:
    d=json.load(open('evidence/G3/FRONT_END_REACHES_HIM.json'))
except Exception:
    print(open('evidence/G3/FRONT_END_REACHES_HIM.json').read()[-600:]); raise SystemExit
for p in d.get('problems') or [d.get('error_code','')]: print('  ✗', p)"
      fail '公开域名下发的前端，在真 Chrome 里跑不出这次发的界面——他那边等于没发。'
  fi
  python3 -c "
import json
d=json.load(open('evidence/G3/FRONT_END_REACHES_HIM.json'))
a=[x for x in d['supply_from_production']['assets'] if 'app.js' in x['url']][0]
b=d['measured']['rendered']['forgetButtons']
print(f\"  公网那份 app.js {a['bytes']} 字节（{a['url']}）；真 Chrome 画出 {len(b)} 颗「删除并清空」，点了会发 POST …/forget。\")"
else
  printf '  跳过：这台机器上没有 Chrome（前端是否真到得了他手上，本轮没验）。\n'
fi

step "8.64) 他桌面上那两个双击文件，还在不在、跟不跟得上这台生产"
# 《使用说明》第二节写着「双击桌面上的『同步到 Obsidian.command』」——
# 那是他把内容拿进 Obsidian 的主路。而 2026-08-11 一看：**桌面上一个都没有**。
# 说明书指着一个不存在的东西，而没有任何一步会发现。
#
# 那个文件必须自包含（`_scratch/` 里的工作树随时会被回收），代价是主机名写死在
# 里面——换机器时它不会自动跟上，**而且什么都不会报错**。
#
# 先刷新（只在不一致时落盘），再 `--check`。**不接管道**：接了管道
# 退出码会被管道尾巴吃掉，这个仓为这件事记过教训，而我今天量它时又犯了一次。
.venv/bin/python scripts/refresh_desktop_launcher.py > /tmp/sa_launcher.$$ 2>&1 \
  || { cat /tmp/sa_launcher.$$; rm -f /tmp/sa_launcher.$$; fail '刷新桌面那两个双击文件失败。'; }
if ! .venv/bin/python scripts/refresh_desktop_launcher.py --check > /tmp/sa_launcher.$$ 2>&1; then
  cat /tmp/sa_launcher.$$
  rm -f /tmp/sa_launcher.$$
  fail '他桌面上那两个双击文件和仓里对不上——说明书让他双击的东西不在或过期了。'
fi
sed -n '1s/^ */  /p' /tmp/sa_launcher.$$
rm -f /tmp/sa_launcher.$$

step "8.66) 他点「下载全部 Markdown」，拿到的那个 zip 是好的吗"
# 《使用说明》第二节两条取法，第一步都是这颗按钮。而在补这一步之前
# **没有任何一步在生产上验过它**：单元判据跑在本机 TestClient 上，
# 部署脚本里一次都没出现过 markdown.zip。上一次真去点它是 0.0.0.29。
#
# 在容器里用它自己的令牌打自己的回环口——**令牌不出容器，正文一个字都不出来**，
# 只回条目数/文件数和几个缺陷计数。
if ! .venv/bin/python scripts/check_his_markdown_export_still_works.py --host "$HOST" \
      > evidence/G3/HIS_MARKDOWN_EXPORT.json 2>&1; then
  python3 -c "
import json
try:
    d=json.load(open('evidence/G3/HIS_MARKDOWN_EXPORT.json'))
except Exception:
    print(open('evidence/G3/HIS_MARKDOWN_EXPORT.json').read()[-500:]); raise SystemExit
for p in d.get('problems', []): print('  ✗', p)"
  fail '他点「下载全部 Markdown」拿到的那个 zip 有问题——那是他把东西拿进 Obsidian 的第一步。'
fi
python3 -c "
import json
d=json.load(open('evidence/G3/HIS_MARKDOWN_EXPORT.json'))['measured']
print(f\"  库里 {d['items_in_library']} 条 → zip 里 {d['files_in_zip']} 个文件；\"
      f\"空标题 {d['empty_heading']}、重复文案标题 {d['title_is_a_doubled_caption']}、\"
      f\"作者是点赞数 {d['author_is_a_like_count']}、读不出来的 {d['unreadable_files']}。\")"

step "8.63) 生产上有没有第二个同名的运行库"
# 2026-08-11 撞见的：`/var/lib/social-archive/social-archive.sqlite3` **0 字节**，
# 而真库在 `…/runtime/social-archive.sqlite3`（4.7 MB / 193 条）。**同名，差一层目录。**
# 我第一次查就猜了上面那个，拿到 `no such table: content`，差点当成「生产的库坏了」。
#
# 那个空壳是我自己用错路径 `sqlite3.connect()` 留下的（它会顺手把文件建出来）。
# 已经收掉。这一步是不让它再长出来：**同名的空库躺在最好猜的位置上，
# 谁指过去都会读到「0 条」——一个看起来完全合理的错答案。**
if ! .venv/bin/python scripts/check_no_decoy_runtime_db_on_production.py --host "$HOST" \
      > evidence/G3/NO_DECOY_RUNTIME_DB.json 2>&1; then
  python3 -c "
import json
d=json.load(open('evidence/G3/NO_DECOY_RUNTIME_DB.json'))
for p in d.get('problems', []): print('  ✗', p)"
  fail '生产上出现了第二个同名运行库——先查清它是不是活的，再决定怎么处置。'
fi
python3 -c "
import json
m=json.load(open('evidence/G3/NO_DECOY_RUNTIME_DB.json'))['measured']
print(f\"  只有一个运行库：{m['real']}（{m['real_bytes']:,} 字节）。\")"

step "8.67) 东西真的在他 Obsidian 库里，而且是干净的"
# 整条产品线的终点：他把内容读到眼睛里的地方是 Obsidian。
# 前面每一段都有人验（库里几条、zip 几个、桌面那两个文件），
# **而他库里那几篇一直没有任何一步管**——
# 偏偏这一段在这次会话里被弄乱过两次（193→198、198→246：
# 我在服务器上改了文件名，rsync 把新名字带进来，库里出现两份）。
#
# 条数从上一步那份证据里取（不手写，`self-reported-numbers-must-be-computed`）。
EXPECT_ITEMS="$(python3 -c "
import json
try:
    print(json.load(open('evidence/G3/HIS_MARKDOWN_EXPORT.json'))['measured']['items_in_library'])
except Exception:
    print('')
")"
if [ -n "$EXPECT_ITEMS" ]; then
  set -- --expect-items "$EXPECT_ITEMS"
else
  set --
fi
if ! .venv/bin/python scripts/check_his_obsidian_vault_is_intact.py "$@" \
      > evidence/G3/HIS_OBSIDIAN_VAULT.json 2>&1; then
  python3 -c "
import json
d=json.load(open('evidence/G3/HIS_OBSIDIAN_VAULT.json'))
for p in d.get('problems', []): print('  ✗', p)"
  fail '他 Obsidian 库里那一份和档案馆对不上——那是整条线的终点。'
fi
python3 -c "
import json
d=json.load(open('evidence/G3/HIS_OBSIDIAN_VAULT.json'))
if d['status'] == 'SKIPPED':
    print('  跳过：这台机器上没有那个 Obsidian 库（**是跳过，不是通过**）。')
else:
    m=d['measured']
    print(f\"  他库里 {m['notes']} 篇，按 {len(m['platforms'])} 个平台分好；\"
          f\"空标题 {m['empty_heading']}、重复文案标题 {m['title_is_a_doubled_caption']}、\"
          f\"作者是点赞数 {m['author_is_a_like_count']}、同一条两份 {m['same_item_twice']}。\")
    # **播报也要真的播出来。** 2026-08-12：那 56 篇播放进度标题写进了证据文件，
    # 而这里没印——等于记下来了、没人看见。判据没有调用方不算判据，
    # 播报没人读也一样。
    for line in d.get('notes_to_read_zh', []):
        print(f\"  ⚠️  {line}\")"

step "8.68) 从零到能用，在**刚部署的这个镜像**上真走一遍"
# 上一步验的是界面到不到得了他手上。这一步验的是**按下去之后那条链**：
# 空库 → 连账号 → 同步 → 看得见（标题/作者都对）→ 删除并清空 → 又空了
# → 重连 → 再同步 → 内容回来了。
#
# **碰不到他的数据**：起一个一次性容器，数据根是容器内的 tmpfs，跑完就删。
# 他那份 /opt/social-archive/runtime/data 一个字节都不动。
if ! .venv/bin/python scripts/from_zero_drill.py --host "$HOST" --version "$VERSION" \
      > evidence/G3/FROM_ZERO.json 2>&1; then
  python3 -c "
import json
try:
    d=json.load(open('evidence/G3/FROM_ZERO.json'))
except Exception:
    print(open('evidence/G3/FROM_ZERO.json').read()[-800:]); raise SystemExit
for s in d.get('steps', []):
    if not s['ok']: print('  ✗', s['step'], '→', str(s['measured'])[:160])
if d.get('detail'): print('  ✗', d['detail'][:400])"
  if grep -q SSH_TRANSPORT_FAILED evidence/G3/FROM_ZERO.json 2>/dev/null; then
    fail 'ssh 到生产机断了（不是产品缺陷，演练已自动重连过一次）——重跑一次部署即可。'
  fi
  fail '刚部署的这个镜像上，「从零到能用」这条链走不通。'
fi
python3 -c "
import json
d=json.load(open('evidence/G3/FROM_ZERO.json'))
print(f\"  {len(d['steps'])} 步全过：从空库连账号、同步、看得见、删除并清空、重连再同步。\")"

step "8.69) 出事的时候，他的东西真的拿得回来吗"
# 前面每一步验的都是**功能对不对**。这一步验的是**东西还在不在、拿不拿得回来**——
# 到今天为止这一格是空的：三个恢复演练在 docs/DRILLS.md 里写着「定期」，
# 而「定期」没有闹钟（部署脚本里那三个脚本名出现 0 次）。
#
# 现在每次部署都对**最新那批快照**真跑一遍：下载 → 解密 → 解压 → 打开 →
# 数表 → 判它是不是他的数据。实测 12 秒；按铁律 7 算过，量级上看不见。
#
# 第三份（GitHub）**也在这里试**。它此前一直报「取不回、只有 Owner 能授权」，
# 2026-08-11 查清是两个自己的毛病：比的是一批没有它收据的快照（三份写齐只在每天
# 03:28 那次备份里，而这里取的是 15 分钟一份的最新那批），用的是一把看不见那个仓的
# 令牌（`.env` 指的是容器内路径，回退按文件名落到了另一把）。**都跟权限无关。**
if ! .venv/bin/python scripts/check_the_backup_can_actually_be_restored.py \
      > evidence/G3/RESTORE_FROM_BACKUP.json 2>&1; then
  python3 -c "
import json
try:
    d=json.load(open('evidence/G3/RESTORE_FROM_BACKUP.json'))
except Exception:
    print(open('evidence/G3/RESTORE_FROM_BACKUP.json').read()[-600:]); raise SystemExit
for p in d.get('problems', []): print('  ✗', p)"
  fail '备份取不回来——**这条红的意思是出事的时候东西回不来**，比任何功能缺陷都要紧。'
fi
python3 -c "
import json
d=json.load(open('evidence/G3/RESTORE_FROM_BACKUP.json'))
# **播报块自己不许把部署带红。** 上面每一道验收都过了才走到这里，
# 而 sorted() 撞上一个 None 就抛 TypeError——那会变成一次\"检查全绿却失败\"的部署。
# 这个形状是跑出来的，不是读出来的：拿一份缺 snapshot_batch 的结果喂它，当场 TypeError。
for t in d['targets']:
    rows = t.get('content_rows_per_copy') or {}
    detail = '、'.join(f'{k} {v} 条' for k, v in rows.items())
    print(f\"  {t['key']}：{t['restorable_copies']}/{t['required']} 份真取回来了\"
          + (f\"（{detail}）\" if detail else '') + f\"——{t['zh']}\")
    if t.get('coverage_zh'):
        print(f\"    {t['coverage_zh']}\")
batch=[a.get('snapshot_batch') for t in d['targets'] for a in t['attempts'] if a.get('snapshot_batch')]
print(f\"  用的是 {sorted(batch)[-1]} 那批快照。\" if batch else \"  （这次没记下是哪批快照）\")
print('  三份都是真取回来的（下载→解密→打开→判），不是读登记表。')"

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
    > evidence/G3/PRODUCTION_MATCHES_REPO.json \
  || { cat evidence/G3/PRODUCTION_MATCHES_REPO.json; fail "仓／主机／镜像三份对不上。**别把这一步当噪音**：
  · only_on_production            —— 生产上有来路不明的代码正在跑
  · container_is_running_older_code —— 服务执行的不是你以为的那一版，要重建镜像
  两者的下一步完全不同，报告里已分开列。"; }
# **这句话要照报告说，不能照心情说。**（2026-08-11）
#
# 报告里的 `dev_only_differs`（判据/演练与仓不一致，容器不跑它们）不算失败——
# 那个分类是对的。但那时仍印一句「三份一致」就是假话：
# 我在一次部署跑到一半时修了个演练，这一步照样印「三份一致」，
# 而 JSON 里明明白白列着那个文件。**JSON 对、印给人看的那句错**
# —— `gates-cover-json-not-the-prose-users-read` 的同一个形状。
python3 -c "
import json
d = json.load(open('evidence/G3/PRODUCTION_MATCHES_REPO.json'))
dev = d.get('dev_only_differs') or []
if dev:
    print(f'  服务那一份三份一致（仓 = 主机 = 镜像）。'
          f'另有 {len(dev)} 个判据/演练文件**镜像里那份是旧的**——'
          f'第 3.7 步认定改它们不改变镜像的行为，于是跳过了重建；'
          f'主机上那份已经是仓里这一份。下次真重建时会一起带上：{dev[:3]}')
else:
    print('  三份一致：仓 = 主机 = 镜像。')
"

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
