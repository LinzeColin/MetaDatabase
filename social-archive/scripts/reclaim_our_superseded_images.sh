#!/usr/bin/env bash
# 收掉**我们自己上一个版本**的镜像。在生产主机上跑（部署脚本 ssh 过去喂给 bash -s）。
#
#   bash scripts/reclaim_our_superseded_images.sh <当前版本号>
#
# 2026-08-07 实测：盘上躺着 social-archive/core:0.0.0.21（451MB）和
# cli-tools:0.0.0.21（995MB），**没有任何容器在用**，也不是回滚点——
# 回滚点是另一个 tag、另一个镜像 ID（当天核过：rollback=304ada…、
# 0.0.0.21=365be6…，是两个东西）。一共 1.4G，正好是磁盘门差的那一截。
#
# 我原本把它列成「要 Owner 裁定」。**核过之后这个判断不成立**：它们是我们
# 自己每次部署留下的，铁律 3 写着谁开的谁收，而部署第 10 步早就在自动回收
# 我们自己的悬空镜像了——这两个只是还挂着 tag 所以不算悬空。同一类东西，
# 不该因为多一个 tag 就变成他的事。
#
# **这台机器还跑着别人的项目**（memory-atlas / gatus / coolify）。所以：
#
#   四道自锁，缺一不删
#   ① 只动 social-archive/ 开头的仓库名——别的项目一概不碰
#   ② 跳过当前版本
#   ③ 跳过 rollback / rollback-candidate
#   ④ 跳过任何被容器引用的镜像 ID（**含已停止的容器**）
#
# 删的是 tag。镜像 ID 若被别的 tag 共用，`docker rmi <ref>` 只是解绑，
# 不会真删掉底下那个镜像。
#
# 收不掉就跳过，**绝不因此让部署失败**——磁盘门在后面会重新量，不够自然会拦。
#
# 任何情况下都不用 `docker system prune`，也不碰没有我们标签的悬空镜像。
set -u

current="${1:?要当前版本号}"

# ④ 被容器引用的镜像 ID（含已停止的），以及回滚点指向的 ID。
keep="$(sudo docker ps -aq | xargs -r sudo docker inspect -f '{{.Image}}' 2>/dev/null || true)
$(sudo docker image inspect -f '{{.Id}}' social-archive/core:rollback 2>/dev/null || true)
$(sudo docker image inspect -f '{{.Id}}' social-archive/core:rollback-candidate 2>/dev/null || true)"

# ① 只列我们自己的。
sudo docker images --format '{{.Repository}}:{{.Tag}}' \
  | grep '^social-archive/' | while read -r ref; do
    tag="${ref##*:}"
    # ②③
    case "$tag" in
      "$current"|rollback|rollback-candidate|'<none>') continue ;;
    esac
    id="$(sudo docker image inspect -f '{{.Id}}' "$ref" 2>/dev/null || true)"
    [ -n "$id" ] || continue
    case "$keep" in
      *"$id"*) printf '    留着 %s（有容器或回滚点在引用）\n' "$ref"; continue ;;
    esac
    printf '    回收 %s\n' "$ref"
    sudo docker rmi "$ref" >/dev/null 2>&1 \
      || printf '    收不掉 %s（跳过，不因此失败）\n' "$ref"
  done
