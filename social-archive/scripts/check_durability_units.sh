#!/usr/bin/env bash
# 复核「保命的那几个 unit 到底启用了没有」。**在宿主机上跑。**
#
# 为什么需要它：prepare_systemd_host.sh 按设计**不启用**任何 unit
# （装好 → Owner 验收 → 显式启用），这个取舍本身是对的。
# 但交接只说了一句「由 Owner 显式启用」，没说要启用哪几个，
# 也没有任何东西回头核一遍。
#
# 生产实测（2026-08-04）后果：
#   social-archive.service          enabled / active     ✓
#   social-archive-status.timer     enabled / active     ✓
#   social-archive-backup.timer     **disabled**         ✗ 从来没跑过
#   social-archive-replication.timer **disabled**        ✗ 从来没跑过
#   social-archive-private-database-sync.timer **disabled** ✗ 从来没跑过
#
#   → 549 个制品里 **530 个一个异地副本都没有**
#   → journalctl 90 天内三个 unit 全是 "No entries"
#
# 数据只存在一块盘上，而产品的卖点是「归档」。
set -uo pipefail

REQUIRED=(
  social-archive.service
  social-archive-backup.timer
  social-archive-replication.timer
  social-archive-private-database-sync.timer
  social-archive-status.timer
  social-archive-cloudflared.service
)

BAD=0
BAD_RUN=0
UNKNOWN_RUN=0
FAILING=()
UNCONFIRMED=()

# systemd 的墙钟时间串（`Thu 2026-08-13 08:51:06 UTC`）→ 秒。转不出来**回空**。
#
# 为什么不用 `date -d`：那是 GNU 专有的写法，在开发机（macOS）上直接失败，
# 于是这段判断在我自己机器上**永远不执行**——判据坏在只在别人机器上发作的分支里，
# 这个仓已经栽过。python3 两边都有（宿主机跑的就是 Python 应用）。
# 万一它也不在，上面那一支会把"比不出来"如实印出来，**不会掉进"看着像成功"**。
_epoch() {
  [ -n "${1:-}" ] && [ "${1}" != "n/a" ] || return 0
  python3 - "$1" <<'PY' 2>/dev/null || true
import datetime, sys
s = sys.argv[1].strip()
for fmt in ("%a %Y-%m-%d %H:%M:%S %Z", "%a %Y-%m-%d %H:%M:%S"):
    try:
        when = datetime.datetime.strptime(s, fmt)
    except ValueError:
        continue
    print(int(when.replace(tzinfo=datetime.timezone.utc).timestamp()))
    break
PY
}
printf '%-46s %-10s %-10s %s\n' UNIT 启用 运行 上次跑的结果
printf '%.0s-' {1..92}; printf '\n'
for unit in "${REQUIRED[@]}"; do
  enabled="$(systemctl is-enabled "${unit}" 2>&1 || true)"
  active="$(systemctl is-active "${unit}" 2>&1 || true)"

  # 第四列只对定时器有意义：常驻服务的"上次结果"就是它此刻 active 与否。
  outcome='—'
  case "${unit}" in
    *.timer)
      # 问 systemd 它到底触发哪个 unit，别假定同名（[Timer] 里可以写 Unit=）。
      svc="$(systemctl show "${unit}" -p Unit --value 2>/dev/null)"
      [ -n "${svc}" ] || svc="${unit%.timer}.service"
      started="$(systemctl show "${svc}" -p ExecMainStartTimestamp --value 2>/dev/null)"
      result="$(systemctl show "${svc}" -p Result --value 2>/dev/null)"
      code="$(systemctl show "${svc}" -p ExecMainStatus --value 2>/dev/null)"
      if [ -z "${started}" ]; then
        # **这一支不许读 Result。** 生产实测（2026-08-13，/run 里放一个从没启动过的
        # 探针 unit 问出来的）：没跑过的 unit，systemd 照样答 Result=success、
        # ExecMainStatus=0。照它判就会把"从来没跑过"报成"上次成功"——
        # 正是 2026-08-04 那次事故（三个 timer 全 disabled、90 天 No entries）。
        # 唯一诚实的字段是这个时间戳：没跑过就是空的。
        outcome="从没跑过（**不是成功**）"
        BAD_RUN=1; FAILING+=("${svc}")
      elif [ "${result}" != "success" ]; then
        outcome="✗ 上次失败 ${result}/${code}"
        BAD_RUN=1; FAILING+=("${svc}")
      else
        # **「这个服务上次跑成了」不等于「定时器叫起来的那次跑成了」。**
        #
        # 2026-08-13 生产实测，这两个是不同的时刻：
        #     timer   LastTriggerUSec        = 03:33:46   ← 定时触发，200/CHDIR **失败**
        #     service ExecMainStartTimestamp = 08:51:06   ← 我手工补跑，成功
        # 而这一列当时印的是「✓ 上次成功 08:51:06」——**把失败的那次自动运行整个盖住**。
        # 这道判据存在的全部理由就是抓这一种，它却报了绿。
        #
        # systemd 没有「上一次由定时器触发的那次跑成没有」这个字段。
        # 能诚实做到的是：两个时刻差得多，就**说清楚这个结果不是定时那次的**，
        # 并给出去哪儿看的确切命令。不阻断（手工跑过是正常操作，
        # 为此常红就变成狼来了），但不许再声称「定时那次成功了」。
        trig="$(systemctl show "${unit}" -p LastTriggerUSec --value 2>/dev/null)"
        t_s="$(_epoch "${trig}")"
        s_s="$(_epoch "${started}")"
        if [ -z "${t_s}" ] || [ -z "${s_s}" ]; then
          # **解不出来就说解不出来**，不许掉进"看着像成功"那一支。
          outcome="? 成功了，但比不出是不是定时那次（时间串解不出来）"
          UNKNOWN_RUN=1; UNCONFIRMED+=("${unit}|${svc}|${trig:-未知}")
        elif [ "$(( s_s - t_s ))" -gt 300 ]; then
          outcome="? 上次成功的是**手工**那次 ${started}"
          UNKNOWN_RUN=1; UNCONFIRMED+=("${unit}|${svc}|${trig}")
        else
          outcome="✓ 上次成功 ${started}"
        fi
      fi
      ;;
  esac

  printf '%-46s %-10s %-10s %s\n' "${unit}" "${enabled}" "${active}" "${outcome}"
  case "${enabled}" in
    enabled|enabled-runtime|static|indirect) ;;
    *) BAD=1 ;;
  esac
done

if [ "${BAD_RUN}" = "1" ]; then
  printf '\n✗ 定时器装着，但**它触发的那件事没做成**。\n'
  printf '  这两件事是分开的：`enabled`/`active` 说的是定时器本身还在不在，\n'
  printf '  跟它每次叫起来的那个服务跑没跑成**毫无关系**。\n'
  printf '\n  生产实测过两次，两次这张表都是全绿的：\n'
  printf '    2026-08-11~12  replication 连着失败 108 次、28 小时（200/CHDIR）\n'
  printf '    2026-08-12~13  backup 连着两天同一个错——而事故当时只查了 replication\n'
  printf '  两次都是「有人把 /opt/social-archive 改回 700，服务连工作目录都进不去」。\n'
  printf '\n  失败的是：\n'
  for svc in "${FAILING[@]}"; do printf '    %s\n' "${svc}"; done
  printf '\n  看它为什么失败：\n'
  for svc in "${FAILING[@]}"; do printf '    sudo journalctl -u %s -n 30 --no-pager\n' "${svc}"; done
  printf '\n  修好之后**别等下一次定时**，当场按原路跑一遍复核：\n'
  for svc in "${FAILING[@]}"; do printf '    sudo systemctl start %s\n' "${svc}"; done
  printf '\n  常见那一种的修法（工作目录进不去）：\n'
  printf '    sudo chgrp socialarchive /opt/social-archive && sudo chmod 750 /opt/social-archive\n'
fi

if [ "${BAD}" = "1" ]; then
  printf '\n✗ 有 unit 没有启用。**这不是「少个功能」**：\n'
  printf '  备份没启用 = 没有任何定时备份\n'
  printf '  复制没启用 = 制品只存在于本机这一块盘上\n'
  printf '  两者都静默 —— 界面照样显示「已归档」。\n'
  # **带 sudo**：2026-08-13 生产实测，非 root 跑 `systemctl enable` 会得到
  # `Interactive authentication required`。提示里给一条会被拒的命令，
  # 等于把人送去撞墙——这个仓今天已经因为同一件事修过运维手册四条命令。
  printf '\n启用命令（由 Owner 执行，本脚本只读不改）：\n'
  for unit in "${REQUIRED[@]}"; do
    printf '  sudo systemctl enable --now %s\n' "${unit}"
  done
  printf '\n启用后重跑本脚本复核；再看 /v1/status 的 storage.completion。\n'
  exit 1
fi
[ "${BAD_RUN}" = "1" ] && exit 1

if [ "${UNKNOWN_RUN}" = "1" ]; then
  printf '\n? 有定时器**它自己那次跑成没跑成，这几个字段答不了**。\n'
  printf '  这几个的最近一次运行是**手工触发**的（时刻比定时触发晚很多），\n'
  printf '  而 systemd 只保留"最近一次运行"的结果，不分是谁叫起来的。\n'
  printf '\n  为什么要专门说：2026-08-13 生产上就是这样——\n'
  printf '    03:33:46  定时触发 → 200/CHDIR **失败**\n'
  printf '    08:51:06  手工补跑 → 成功\n'
  printf '  而这张表当时印的是「✓ 上次成功 08:51:06」，**把失败的那次自动运行整个盖住**。\n'
  printf '  「手工能跑通」和「没人管它也会跑」是两件事，后者才是这个产品的卖点。\n'
  printf '\n  去看那次定时到底成没成（时间窗就是它触发的那一刻）：\n'
  for row in "${UNCONFIRMED[@]}"; do
    u="${row%%|*}"; rest="${row#*|}"; s="${rest%%|*}"; when="${rest#*|}"
    printf '    # %s 触发于 %s\n' "${u}" "${when}"
    printf '    sudo journalctl -u %s --since "%s" -n 30 --no-pager\n' "${s}" "${when}"
  done
  printf '\n  确认那次是好的之后，等下一次自动触发跑完再看这张表，它会变回 ✓。\n'
fi

if [ "${UNKNOWN_RUN}" = "1" ]; then
  printf '\n✓ 保命的 unit 都已启用；**但上面那几个"定时那次成没成"还没确认**。\n'
else
  printf '\n✓ 保命的 unit 都已启用，**而且每个定时器上次真的跑成了**。\n'
fi
printf '  它没有证明的：这一轮备份的内容对不对、副本能不能解开——\n'
printf '  那要看 `/v1/status` 的 replicas；\n  要真的验"取得回来"，在开发机上跑 scripts/check_the_backup_can_actually_be_restored.py\n  （生产上直接敲 restore.sh 会回 BLOCKED_ENVIRONMENT：解密身份在 unit 的 EnvironmentFile 里）。\n'
