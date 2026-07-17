"""ALPHA-LIVE-060:烤机 harness 加速预检自测(轻量 500 周期,保证 harness 不退化)。"""

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
