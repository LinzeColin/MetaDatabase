"""诊断必须看得见「本项目真正出过事的那三件」（v0.0.0.7 / T18）。

2026-08-05 实测：`doctor.sh` 全绿、25 条 PASS、退出码 0——而它检查的是
版本、Docker、容器状态、密钥权限。下面这三件它一件都看不见：

  · 保命的 timer 有没有启用   08-04：三个全 disabled，journalctl 90 天 No entries
  · 异地副本跟没跟上         同上：549 个制品里 **530 个零异地副本**，
                             而界面照样显示「已归档」
  · 主机 venv 是不是这一版   08-05：落后两个版本，而四个 timer 全跑在它上面

**一个说「都好」而看不见这三件的诊断，和 /health 返回 200 而所有业务路由 500
是同一种谎。**
"""

from pathlib import Path

DOCTOR = (Path(__file__).resolve().parents[2] / "scripts/doctor.sh").read_text(encoding="utf-8")


def test_doctor_checks_the_durability_units() -> None:
    assert "check_durability_units.sh" in DOCTOR, (
        "诊断不看保命的 timer——08-04 三个全 disabled 时，doctor 会照样说都好"
    )


def test_doctor_counts_offsite_replicas_from_the_database() -> None:
    """数库，不问自述。

    08-04 那次最要命的地方不是「没备份」，是**没人看得出来没备份**。
    """
    assert "object_replica" in DOCTOR, "诊断不数异地副本"
    assert "一个异地副本都没有" in DOCTOR, "零副本的情况没有被明确报出来"
    assert "mode=ro" in DOCTOR, "读运行库没有用只读模式——诊断绝不该写生产库"


def test_doctor_checks_the_host_venv_version() -> None:
    assert "social_archive.__version__" in DOCTOR, "诊断不看主机 venv 的版本"
    assert "social_archive.__file__" in DOCTOR, "不看它装的是拷贝还是仓里的 src/"


def test_every_new_section_says_skip_is_not_pass() -> None:
    """条件不具备时必须明说是跳过。

    把跳过印成通过，是本项目一直在防的那种谎——而诊断是最容易这样骗人的地方，
    因为它的输出是给人看的、不是给判据看的。
    """
    assert DOCTOR.count("这不是通过") >= 3, (
        "有新加的检查在条件不具备时会静默略过，看起来像通过"
    )
