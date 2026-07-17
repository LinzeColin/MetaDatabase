"""ALPHA-LIVE-060:烤机 harness 加速预检自测(轻量 500 周期,保证 harness 不退化)。"""

from pathlib import Path

from scripts.run_soak import run


def test_accelerated_presoak_engineering_ok(tmp_path):
    report = run(cycles=500, hours=0.0, out_dir=str(tmp_path))
    assert report["kind"] == "本机加速预检"
    assert report["heartbeat_gaps"] == 0            # 心跳无空洞
    assert report["outbox_backlog_end"] == 0        # 通知不积压(退避重试全排空)
    assert report["notify_retries_recovered"] > 0   # 发信抖动确有发生且全恢复
    assert report["mem_peak_growth_kb"] < 5000       # 无明显内存泄漏
    assert report["kill_switch_engaged"] is False    # 正常运行不触发杀开关
    assert report["verdict_engineering_ok"] is True


def test_soak_db_isolated_under_out_dir(tmp_path):
    """回归:烤机库必须落在 out_dir 内,绝不碰共享 runtime/soak.sqlite。

    历史事故:硬编码 runtime/soak.sqlite 相对 CWD,并发 pytest 的本测试会 unlink 掉
    正在真跑的 72h 烤机的库文件 -> SQLite readonly 崩溃。库随 out_dir 隔离后杜绝。
    """
    run(cycles=50, hours=0.0, out_dir=str(tmp_path))
    assert (tmp_path / "soak.sqlite").exists()       # 库确在自己的 out_dir 内
    # 不得在 CWD 下的 runtime/ 里留下烤机库(若存在也不是本次 run 写的)
    assert not (tmp_path / "runtime" / "soak.sqlite").exists()
