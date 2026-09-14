# Signal Lattice v2 回滚手册

生产机：`ubuntu@15.235.141.201`（OVH VPS-3）
密钥：`_protected/alpha_deploy_private/linze_ovh_production_ed25519`

## 现状（2026-09-14 切换后）

| 单元 | 状态 | 说明 |
|---|---|---|
| `signal-lattice-v2-api` | active | 监听 `127.0.0.1:8787`，Cloudflare 隧道指向它 |
| `signal-lattice-v2-loop.timer` | active | 每 60 秒调度一次有界 `once` 采集 |
| `signal-lattice-v2-loop` | inactive between runs | 由 timer 启动；每次完成或触发预算/退避门后退出 |
| `signal-lattice-tunnel` | active | cloudflared，**不再绑定任何 v19 单元** |
| `signal-lattice-v19-*` | inactive/disabled | 安装保留在 `/opt/signal-lattice-v19/`，仅作回滚 |

## 一个必须记住的坑

旧的 `signal-lattice-v19-cloudflared.service` 写着 `Requires=signal-lattice-v19-api.service`。
**停 v19-api 会把隧道一起带停，公网立刻 530。** 2026-09-14 切换时实际发生过。
新的 `signal-lattice-tunnel.service` 改用 `Wants=signal-lattice-v2-api.service`，
隧道不再随任何应用单元停机。回滚时不要退回旧的 cloudflared 单元。

## 回滚到 v19

```bash
sudo systemctl stop signal-lattice-v2-api signal-lattice-v2-loop.timer signal-lattice-v2-loop
sudo systemctl disable signal-lattice-v2-api signal-lattice-v2-loop.timer
sudo systemctl enable --now signal-lattice-v19-api signal-lattice-v19-loop
# 隧道不用动：signal-lattice-tunnel 仍指向 8787，v19 也监听 8787
curl -s -o /dev/null -w '%{http_code}\n' https://signal-lattice.linzezhang.com/
```

回滚后注意：v19 读的是 `/opt/signal-lattice-v19/releases/0.0.0.1.43/fixtures/` 下
2026-08-14 冻结的静态行情，**它给出的"结论"不是实时的**，只应作为临时止血。

## 端口

- `8787`：Signal Lattice（隧道固定指向，ingress 由 Cloudflare 面板托管，本地改配置无效）
- `8788`：**weread-port 占用，不要碰**
- `8790/8791/8792`：空闲，灰度用

## 回滚到上一个 v2 版本（优先于回滚到 v19）

`install_release.sh` 会把上一版留在 `/opt/signal-lattice-v2/previous`。
2026-09-14 切到 `0.0.0.3.3` 时，previous 指向 `0.0.0.2.3-r6`。

```bash
sudo ln -sfn "$(readlink -f /opt/signal-lattice-v2/previous)" /opt/signal-lattice-v2/current.new
sudo mv -T /opt/signal-lattice-v2/current.new /opt/signal-lattice-v2/current
sudo systemctl restart signal-lattice-v2-api
curl -s -o /dev/null -w '%{http_code}\n' https://signal-lattice.linzezhang.com/health/ready
```

## 采集单元形态（2026-09-14 改过）

切换前生产跑的是 `ExecStart=… signal-lattice loop`，靠 systemd 自动重启制造节拍，
`signal-lattice-v2-loop.timer` 从未安装——而 `deploy/V2_RELEASE_CONTRACT.json`
一直声明着这个 timer。已改为仓库设计的形态：`Type=oneshot` + `ExecStart=… once`，
由 timer 以 `OnUnitInactiveSec=60` 调度。

原单元备份在目标机 `/etc/systemd/system/signal-lattice-v2-loop.service.bak-restart-driven`。
要退回重启驱动形态：

```bash
sudo systemctl disable --now signal-lattice-v2-loop.timer
sudo cp /etc/systemd/system/signal-lattice-v2-loop.service.bak-restart-driven \
        /etc/systemd/system/signal-lattice-v2-loop.service
sudo systemctl daemon-reload && sudo systemctl enable --now signal-lattice-v2-loop.service
```

注意 `signal-lattice loop --max-runs` 默认为 1，两种形态都只跑一轮就退出，
不存在无终点后台循环；差别只在节拍由 timer 还是由 Restart 提供。
