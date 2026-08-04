#!/usr/bin/env bash
# 把已经装好的一台机器更新到当前这份代码。
#
# ## 为什么要有这个脚本
#
# 更新的正确顺序里有一步很容易漏：**重建镜像**。
#
#   systemctl restart social-archive.service
#     → ExecStart 是 `docker compose up -d core-api core-worker`，**没有 --build**
#     → 容器用**旧镜像**重建，代码改动一个字都没进去
#
# 而它看起来完全正常：服务起来了、/health 200、日志没有异常。
# 你会以为新版本已经生效，然后发现"那个 bug 还在"——
# 比如 C-T00-01 的根因修复在 sidecars/cli-tools/Dockerfile 里，
# 不重建镜像的话，CLI Sidecar 依旧读不到自己的密钥，界面依旧永远「同步中」。
#
# `scripts/start.sh` 同样没有 --build（它只 --force-recreate）。
# 全仓只有 `install.sh` 会 build，而那是**首次安装**才跑的。
#
# ## 顺序
#
#   1. 工作树干净（避免把本地改动一起带上生产）
#   2. 重建镜像
#   3. 重建容器
#   4. 健康检查
#
# 迁移不在这里跑：`RuntimeStore.initialize()` 在服务启动时自己做。
# 但**升级前先取快照**——回滚唯一诚实的做法是恢复快照
# （见 scripts/rollback_0007.sh 的说明）。

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { printf '更新停止：%s\n' "$1" >&2; exit 2; }

[[ -x .venv/bin/python ]] || fail '这台机器还没装过，请先运行 bash scripts/install.sh'
[[ -f .env ]] || fail '缺少 .env，请先运行 bash scripts/install.sh'
command -v docker >/dev/null || fail '缺少 Docker'

# 生产上 Core 由 systemd 管着。这里只重建镜像与容器，不去碰 systemd 的启停，
# 免得和 social-archive.service 抢同一组容器。
if systemctl is-active --quiet social-archive.service 2>/dev/null; then
  ON_SYSTEMD=1
else
  ON_SYSTEMD=0
fi

# **生产上 /opt/social-archive 不是 git 检出**（实测 2026-08-04：
# `git rev-parse` 报 not a git repository）。第一版这里无条件要求工作树干净，
# 于是它在唯一真正需要用它的那台机器上直接拒绝运行——
# 判据全绿、脚本能跑，**只是跑不了生产**。
if git rev-parse --git-dir >/dev/null 2>&1; then
  if [[ -n "$(git status --porcelain)" ]]; then
    fail '工作树不干净。先提交或还原本地改动——否则这次更新带上去的东西你自己也说不清是什么。'
  fi
  printf '当前提交：%s\n' "$(git rev-parse --short HEAD)"
else
  printf '当前目录不是 git 检出（生产就是这样），跳过干净度检查。\n'
fi
printf '版本：%s\n\n' "$(cat VERSION 2>/dev/null || echo '未知')"

printf '== 1/3 重建镜像（这一步是 systemctl restart 不会做的）==\n'
docker compose build core-api core-worker cli-tools

printf '\n== 2/3 重建容器 ==\n'
if [[ "$ON_SYSTEMD" = "1" ]]; then
  printf '检测到 social-archive.service 在跑，交给 systemd 重启。\n'
  systemctl restart social-archive.service
else
  docker compose up -d --force-recreate core-api core-worker
fi

printf '\n== 3/3 健康检查 ==\n'
PORT="$(awk -F= '$1 == "SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT" {value=$2} END {print value}' .env | tr -d '[:space:]')"
PORT="${PORT:-18765}"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    printf '更新完成：http://127.0.0.1:%s\n' "$PORT"
    printf '镜像已重建 —— 代码改动已经真的生效了。\n'
    exit 0
  fi
  sleep 1
done
printf '更新后健康检查未通过。请运行：bash scripts/doctor.sh\n' >&2
exit 1
