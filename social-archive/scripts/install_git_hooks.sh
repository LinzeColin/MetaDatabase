#!/usr/bin/env bash
# 把这个仓的 pre-commit 门装上——**而且不许踩掉已经在那儿的守卫**。
#
# ## 为什么需要这个脚本
#
# `scripts/git-hooks/pre-commit` 早就写好了，它的文件头写着：
#
#     为什么存在：本会话我两次在门是红的状态下提交……
#     「下次注意」不是修复。这个 hook 是修复。
#
# **而它从来没有被装上过。** 2026-08-12 查出来的：`.git/hooks/pre-commit`
# 那个位置上装的是**另一个**守卫（`linze-maintree-guard`，铁律 2 的机器强制版，
# 由 Private-Database 的 `tools/install-guards.sh` 装的），而且它在 worktree 里
# 第一件事就是 `exit 0`。
#
# 于是：仓里有一个「提交前跑发布门」的 hook、没有任何东西装它、
# 没有任何判据验它装没装、AGENTS.md 和 README 一个字都没提它。
# **一个没被装上的守卫不是守卫**——这正是这个仓一路在拔的「建好了没接上」，
# 只不过这次断在 git 配置这一头。当天我七次在文档判据红着的情况下提交，
# 一次都没被拦住，就是它。
#
# ## 它怎么装
#
# **链，不是盖。** `.git/hooks` 是整个仓库共享的（本仓还有别的 worktree
# 在做别的项目），而那个 maintree 守卫是活的、且重要——铁律 2 说主树只读，
# 那个 hook 就是它的机器强制版。踩掉它等于把铁律 2 的机器保障拆了。
#
# 所以：把现有的那份原样搬到 `pre-commit.chained`，装我们这份上去，
# 而我们这份**第一件事就是调用它**——它说不行就不行。
#
#     bash scripts/install_git_hooks.sh          # 装
#     bash scripts/install_git_hooks.sh --check  # 只看装没装，不改任何东西
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${ROOT}/scripts/git-hooks/pre-commit"
HOOKS="$(git -C "${ROOT}" rev-parse --git-common-dir)/hooks"
TARGET="${HOOKS}/pre-commit"
CHAINED="${HOOKS}/pre-commit.chained"

if [ ! -f "${SOURCE}" ]; then
  printf '✗ 仓里没有 scripts/git-hooks/pre-commit\n' >&2
  exit 2
fi

installed_is_ours() {
  [ -f "${TARGET}" ] && grep -q 'social-archive-gate-hook' "${TARGET}" 2>/dev/null
}

if [ "${1:-}" = "--check" ]; then
  if installed_is_ours; then
    printf 'PASS：发布门 hook 已装（%s）\n' "${TARGET}"
    [ -f "${CHAINED}" ] && printf '      并且链着原来那个守卫（%s）\n' "${CHAINED}"
    exit 0
  fi
  printf 'FAIL：**发布门 hook 没装**——仓里有它，而 %s 上不是它。\n' "${TARGET}" >&2
  printf '      一个没被装上的守卫不是守卫。装它：bash scripts/install_git_hooks.sh\n' >&2
  exit 4
fi

mkdir -p "${HOOKS}"
if [ -f "${TARGET}" ] && ! installed_is_ours; then
  # **原来那份是活的，收下来，别删。** 撞见「已经在那儿的东西」时，
  # 先当它是别人按需要放的，链上去，而不是覆盖掉。
  cp "${TARGET}" "${CHAINED}"
  chmod +x "${CHAINED}"
  printf '已把原来那个守卫搬到 %s，我们这份会先调用它。\n' "${CHAINED}"
fi

cp "${SOURCE}" "${TARGET}"
chmod +x "${TARGET}"
printf '装好了：%s\n' "${TARGET}"
printf '再跑一次 `bash scripts/install_git_hooks.sh --check` 可以确认。\n'
