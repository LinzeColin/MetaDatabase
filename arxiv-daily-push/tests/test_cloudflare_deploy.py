"""adp-cloud 部署判据的反例。

每条都对着 2026-08-12 那次真实事故的形状写：
裸跑 wrangler deploy 把线上 8 个仓外 plain_text 变量清空、站点断 3 分钟。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adp.cloudflare_deploy import (  # noqa: E402
    assert_no_empty_carry, check_live_build, collect_plain_text_vars, compute_build_id,
    current_build_id, pick_current_deployment, redact, stamp_build, vars_to_carry,
)

WORKER_SRC = (
    "// header\n"
    "const BUILD = { build_id: 'oldoldoldold', source_sha256: 'old', "
    "schema_version: 'cn_v0_3', built_at: '2026-07-20' };\n"
    "function todayPage() { return 1; }\n"
)


class BuildIdTests(unittest.TestCase):
    def test_build_id_is_content_derived_and_stable(self):
        first, _ = compute_build_id(WORKER_SRC)
        second, _ = compute_build_id(WORKER_SRC)
        self.assertEqual(first, second, "同一份源码必须算出同一个 id")
        self.assertEqual(len(first), 12)

    def test_any_source_change_moves_the_id(self):
        before, _ = compute_build_id(WORKER_SRC)
        after, _ = compute_build_id(WORKER_SRC.replace("return 1", "return 2"))
        self.assertNotEqual(before, after, "改了源码而 id 不变 —— 这正是「改了却忘升版」")

    def test_stamping_is_idempotent(self):
        stamped, build_id = stamp_build(WORKER_SRC, "2026-08-12")
        self.assertIn(build_id, stamped)
        again, same_id = stamp_build(stamped, "2026-08-12")
        self.assertEqual(again, stamped, "戳过一次之后再戳不应再变")
        self.assertEqual(same_id, build_id)

    def test_same_code_new_day_is_not_a_change(self):
        """代码没变、只是换了一天，不该被判成「BUILD 与源码不一致」。

        第一版把 built_at 也一起重写，于是每天第一次部署必被自己拦下 ——
        一道每天早上必红一次的门等于没有门。真跑生产才发现。
        """
        stamped, build_id = stamp_build(WORKER_SRC, "2026-08-12")
        again, same_id = stamp_build(stamped, "2026-08-13")   # 第二天
        self.assertEqual(again, stamped, "只换日期不该改动源码")
        self.assertEqual(same_id, build_id)
        self.assertEqual(current_build_id(stamped), build_id)

    def test_missing_or_duplicated_build_line_is_refused(self):
        with self.assertRaises(ValueError):
            compute_build_id("没有 BUILD 行\n")
        with self.assertRaises(ValueError):
            compute_build_id(WORKER_SRC + WORKER_SRC)


class CarryVarsTests(unittest.TestCase):
    #: WeReadPort 那次事故的真实形状：线上有、配置里没有。
    LIVE = [
        {"type": "plain_text", "name": "OUT_OF_BAND_URL", "text": "https://例子"},
        {"type": "plain_text", "name": "DECLARED_IN_CONFIG", "text": "在配置里"},
        {"type": "secret_text", "name": "SOME_SECRET"},
        {"type": "d1", "name": "DB"},
    ]

    def test_only_carries_what_the_config_does_not_declare(self):
        live = collect_plain_text_vars(self.LIVE)
        carry = vars_to_carry(live, {"DECLARED_IN_CONFIG"})
        self.assertEqual([name for name, _ in carry], ["OUT_OF_BAND_URL"],
                         "配置里已声明的不用带；仓外的必须带")

    def test_secrets_are_never_carried(self):
        live = collect_plain_text_vars(self.LIVE)
        self.assertNotIn("SOME_SECRET", live, "secret 由 Cloudflare 自动保留，不许重传")

    def test_empty_value_refuses_deploy(self):
        with self.assertRaises(ValueError):
            assert_no_empty_carry([("OUT_OF_BAND_URL", "   ")])
        assert_no_empty_carry([("OUT_OF_BAND_URL", "有值")])   # 正对照：不该抛

    def test_adp_today_has_nothing_to_carry(self):
        """adp-cloud 今天线上就是 0 个 plain_text —— 守卫在，但不该无中生有。"""
        self.assertEqual(vars_to_carry(collect_plain_text_vars([{"type": "d1", "name": "DB"}]), set()), [])


class DeploymentOrderTests(unittest.TestCase):
    #: REST 返回降序（最新在前），`wrangler deployments list` 打印升序。
    DESC = [
        {"created_on": "2026-08-12T03:15:34Z", "versions": [{"version_id": "newest"}]},
        {"created_on": "2026-08-02T11:36:00Z", "versions": [{"version_id": "oldest"}]},
    ]

    def test_picks_newest_regardless_of_input_order(self):
        self.assertEqual(pick_current_deployment(self.DESC), "newest")
        self.assertEqual(pick_current_deployment(list(reversed(self.DESC))), "newest")

    def test_refuses_when_nothing_usable(self):
        with self.assertRaises(ValueError):
            pick_current_deployment([])
        with self.assertRaises(ValueError):
            pick_current_deployment([{"created_on": "2026-08-12T00:00:00Z"}])


class ReadbackTests(unittest.TestCase):
    def test_live_build_must_equal_what_we_just_built(self):
        self.assertEqual(check_live_build({"build_id": "abc123abc123"}, "abc123abc123"), [])
        self.assertEqual(len(check_live_build({"build_id": "旧的旧的旧的"}, "abc123abc123")), 1)
        self.assertEqual(len(check_live_build({}, "abc123abc123")), 1)
        self.assertEqual(len(check_live_build(None, "abc123abc123")), 1)


class RedactTests(unittest.TestCase):
    def test_values_never_reach_the_log(self):
        carried = [("OUT_OF_BAND_URL", "https://秘密地址.example")]
        safe = redact("wrangler 回显了 https://秘密地址.example", carried)
        self.assertNotIn("https://秘密地址.example", safe)
        self.assertIn("<OUT_OF_BAND_URL>", safe)


if __name__ == "__main__":
    unittest.main()
