"""产业瓶颈证据卡：格式校验、读卡规则（过期 / 来源缺失 → NO_EVIDENCE）、接入瓶颈分支、门槛未被放宽、快照钉住、随包卡片自检。

不写「今天还没过期」这类断言：卡片到期是设计内的行为，随包卡片到期后这里不会变红，只是卡片不再生效。
"""

from __future__ import annotations

import copy
import dataclasses
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

import branch_fixtures as fx
import test_research_cycle as trc
from signal_lattice import research_cycle as RC
from signal_lattice.branches import bottleneck as B
from signal_lattice.branches.scoring_support import KIND_CARD, NO_EVIDENCE
from signal_lattice import evidence_snapshot as ES
from signal_lattice.evidence import cards as C
from signal_lattice.evidence_snapshot import load_snapshot

AS_OF = "2026-09-15"
EIA = "https://www.eia.gov/uranium/marketing/pdf/umar.pdf"
BASIS = "这是一条用于测试的依据说明，长度足够。"
FILING = "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000004/doc0004.htm"


def src(url=EIA, excerpt="The average price rose 11% in 2025.", publisher="U.S. Energy Information Administration",
        kind="government_statistics"):
    return {"url": url, "kind": kind, "publisher": publisher, "title": "Some official report", "excerpt": excerpt}


def make_card(**over):
    card = {
        "schema": C.CARD_SCHEMA, "id": "test-card", "bottleneck": "一个用来测试的瓶颈。",
        "retrieved": "2026-09-01", "valid_until": "2027-08-31",
        "factors": {
            "policy_resilience": {"rating": 3, "basis": BASIS, "sources": [src(excerpt="The waiver ends on January 1, 2028.")]},
            "substitution_difficulty": {"rating": 2, "basis": BASIS, "sources": [src(excerpt="Substitutes are less effective.")]},
            "funded_demand": {"rating": 1, "valid_until": "2027-02-28", "basis": BASIS,
                              "sources": [src(excerpt="Contracts cover part of requirements.")]},
        },
        "companies": [{"cik": fx.CIK, "symbol": "SYNS", "name": "Synthetic Strong Corp", "exposure": "铀矿开发商。",
                       "market_cap_usd": 1.0e9, "market_cap_as_of": "2026-08-31",
                       "source": src(FILING, "We are a uranium mining company.", "U.S. SEC (company filing)", "company_filing")}],
        "contradictions": [{"searched": "查了价格是否回落", "found": "没有", "effect": "无"}],
    }
    card.update(over)
    return card


def all_sources(card):
    for factor in card["factors"].values():
        yield from factor["sources"]
    for company in card["companies"]:
        yield company["source"]


def stamps_for(card, status=200, found=True, checked="2026-09-10", skip=()):
    out = {}
    for s in all_sources(card):
        if s["url"] in skip:
            continue
        out[C.stamp_key(s["url"], s["excerpt"])] = {"url": s["url"], "status": status, "excerpt_found": found, "checked": checked}
    return out


def book(card=None, stamps=None, cards=None):
    cards = cards if cards is not None else {"test-card": card or make_card()}
    if stamps is None:
        stamps = {}
        for c in cards.values():
            stamps.update(stamps_for(c))
    return C.CardBook.from_payload({"cards": cards, "stamps": stamps})


def to_yaml(value, indent=0):
    """测试用的最小 YAML 输出（只覆盖卡片用到的：映射、列表、字符串、数字）。"""
    pad = "  " * indent
    lines = []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                lines.append("%s%s:" % (pad, k))
                lines.append(to_yaml(v, indent + 1))
            else:
                lines.append("%s%s: %s" % (pad, k, json.dumps(v, ensure_ascii=False)))
    else:
        for item in value:
            if isinstance(item, dict):
                body = to_yaml(item, indent + 1).split("\n")
                lines.append("%s- %s" % (pad, body[0].strip()))
                lines.extend(body[1:])
            else:
                lines.append("%s- %s" % (pad, json.dumps(item, ensure_ascii=False)))
    return "\n".join(lines)


class SyntheticCardShapeTests(unittest.TestCase):
    def test_the_synthetic_card_used_below_is_itself_valid(self):
        card, problems = C.parse_card(make_card(), expected_id="test-card")
        self.assertEqual(problems, [])
        self.assertEqual(sorted(card.factors), ["funded_demand", "policy_resilience", "substitution_difficulty"])

    def problems(self, raw, expected_id="test-card"):
        card, problems = C.parse_card(raw, expected_id=expected_id)
        self.assertIsNone(card, "本该判为不合格：%r" % problems)
        return "\n".join(problems)

    def test_non_primary_source_domain_is_rejected(self):
        raw = make_card()
        raw["factors"]["policy_resilience"]["sources"] = [src("https://www.reuters.com/markets/some-news", "The waiver ends soon.")]
        self.assertTrue(self.problems(raw))

    def test_plain_http_and_unknown_kind_are_rejected(self):
        raw = make_card()
        raw["factors"]["policy_resilience"]["sources"] = [src("http://www.eia.gov/x.pdf")]
        self.assertTrue(self.problems(raw))
        raw = make_card()
        raw["factors"]["policy_resilience"]["sources"][0]["kind"] = "news"
        self.assertTrue(self.problems(raw))

    def test_excerpt_longer_than_two_sentences_is_rejected(self):
        raw = make_card()
        raw["factors"]["policy_resilience"]["sources"][0]["excerpt"] = "One fact. Two facts. Three facts."
        self.assertIn("2 句", self.problems(raw))

    def test_empty_excerpt_is_rejected(self):
        raw = make_card()
        raw["factors"]["policy_resilience"]["sources"][0]["excerpt"] = ""
        self.assertTrue(self.problems(raw))

    def test_rating_four_needs_a_number_in_an_excerpt(self):
        raw = make_card()
        raw["factors"]["policy_resilience"].update(rating=4, sources=[src(excerpt="Supply is very tight at present.")])
        self.assertTrue(self.problems(raw))
        raw["factors"]["policy_resilience"]["sources"] = [src(excerpt="Lead times reached 36 months.")]
        card, problems = C.parse_card(raw, expected_id="test-card")
        self.assertEqual(problems, [])

    def test_rating_five_needs_two_different_publishers(self):
        raw = make_card()
        raw["factors"]["policy_resilience"].update(rating=5, sources=[src(excerpt="Lead times reached 36 months."),
                                                                     src(excerpt="Lead times reached 40 months.")])
        self.assertTrue(self.problems(raw))
        raw["factors"]["policy_resilience"]["sources"][1] = src("https://www.energy.gov/x.pdf", "Lead times reached 40 months.",
                                                                "U.S. Department of Energy", "regulator")
        card, problems = C.parse_card(raw, expected_id="test-card")
        self.assertEqual(problems, [])

    def test_fast_factors_need_a_short_validity_and_cannot_outlive_the_card(self):
        raw = make_card()
        raw["factors"]["funded_demand"]["valid_until"] = "2027-08-31"          # 检索日 + 364 天 > 190 天
        self.assertTrue(self.problems(raw))
        raw = make_card()
        del raw["factors"]["funded_demand"]["valid_until"]
        self.assertTrue(self.problems(raw))
        raw = make_card(valid_until="2028-12-31")                                # 整张卡超过 366 天
        self.assertTrue(self.problems(raw))

    def test_missing_contradictions_are_rejected(self):
        self.assertTrue(self.problems(make_card(contradictions=[])))

    def test_company_outside_the_pool_cap_range_is_rejected(self):
        for cap in (2.0e8, 6.0e9):
            raw = make_card()
            raw["companies"][0]["market_cap_usd"] = cap
            self.assertTrue(self.problems(raw), cap)

    def test_company_source_must_be_its_own_sec_archive_filing(self):
        raw = make_card()
        raw["companies"][0]["source"] = src(EIA, "We are a uranium mining company.")
        self.assertTrue(self.problems(raw))

    def test_unknown_factor_and_id_mismatch_are_rejected(self):
        raw = make_card()
        raw["factors"]["magic_factor"] = {"rating": 3, "basis": BASIS, "sources": [src()]}
        self.assertTrue(self.problems(raw))
        self.assertTrue(self.problems(make_card(), expected_id="another-id"))

    def test_rating_out_of_range_is_rejected(self):
        raw = make_card()
        raw["factors"]["policy_resilience"]["rating"] = 6
        self.assertTrue(self.problems(raw))

    def test_factor_without_any_source_is_rejected(self):
        raw = make_card()
        raw["factors"]["policy_resilience"]["sources"] = []
        self.assertTrue(self.problems(raw))


class ParserTests(unittest.TestCase):
    def test_subset_parser_reads_the_documented_shapes(self):
        doc = 'a: 1\nb: "x: y"\nc:\n  - 1\n  - "z"\nd:\n  - k: 2\n    m: true\ne: []\nf: {}\n'
        self.assertEqual(C.parse_simple_yaml(doc), {"a": 1, "b": "x: y", "c": [1, "z"], "d": [{"k": 2, "m": True}], "e": [], "f": {}})

    def test_unsupported_syntax_is_an_error_not_a_guess(self):
        for bad in ("a: 'single'\n", "a: &anchor 1\n", "a: |\n  text\n", "a:\n\tb: 1\n", "a: x: y\n"):
            with self.assertRaises(C.CardParseError, msg=bad):
                C.parse_simple_yaml(bad)

    def test_shipped_cards_parse_the_same_as_pyyaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("没有安装 PyYAML，跳过对拍")
        files = sorted(C.CARDS_DIR.glob("*.yaml"))
        for path in files:
            text = path.read_text("utf-8")
            self.assertEqual(C.parse_simple_yaml(text), yaml.safe_load(text), path.name)


class ReadingRuleTests(unittest.TestCase):
    def active(self, b, as_of=AS_OF, cik=fx.CIK):
        return b.for_company(cik, as_of)

    def test_valid_card_and_verified_sources_fill_the_factors(self):
        active, rejected = self.active(book())
        self.assertEqual(sorted(active), ["funded_demand", "policy_resilience", "substitution_difficulty"])
        self.assertEqual(active["policy_resilience"].rating, 3)
        self.assertEqual(rejected, [])

    def test_company_not_on_any_card_gets_nothing(self):
        active, rejected = self.active(book(), cik=999)
        self.assertEqual((active, rejected), ({}, []))

    def test_factor_expires_after_its_valid_until(self):
        active, rejected = self.active(book(), as_of="2027-03-01")          # funded_demand 到 2027-02-28
        self.assertNotIn("funded_demand", active)
        self.assertIn("policy_resilience", active)
        self.assertIn(("funded_demand", "CARD_EXPIRED"), [(r["factor"], r["reason"]) for r in rejected])

    def test_whole_card_expires_after_its_valid_until(self):
        active, rejected = self.active(book(), as_of="2027-09-01")
        self.assertEqual(active, {})
        self.assertEqual({r["reason"] for r in rejected}, {"CARD_EXPIRED"})

    def test_card_is_not_visible_before_its_retrieval_date(self):
        active, rejected = self.active(book(), as_of="2026-08-31")
        self.assertEqual(active, {})
        self.assertEqual(rejected[0]["reason"], "CARD_NOT_YET_RETRIEVED")

    def test_missing_stamp_fails_the_factor_not_the_others(self):
        card = make_card()
        skip = card["factors"]["policy_resilience"]["sources"][0]["url"]
        stamps = stamps_for(card)
        del stamps[C.stamp_key(skip, card["factors"]["policy_resilience"]["sources"][0]["excerpt"])]
        active, rejected = self.active(book(card, stamps))
        self.assertNotIn("policy_resilience", active)
        self.assertIn("substitution_difficulty", active)
        self.assertIn(("policy_resilience", "SOURCE_UNVERIFIED"), [(r["factor"], r["reason"]) for r in rejected])

    def test_non_200_status_excerpt_not_found_or_late_check_all_fail_verification(self):
        card = make_card()
        for kwargs in ({"status": 404}, {"found": False}, {"checked": "2026-09-16"}):
            active, rejected = self.active(book(card, stamps_for(card, **kwargs)))
            self.assertEqual(active, {}, kwargs)
            self.assertTrue(rejected, kwargs)

    def test_editing_an_excerpt_after_verification_invalidates_the_stamp(self):
        card = make_card()
        stamps = stamps_for(card)
        card["factors"]["policy_resilience"]["sources"][0]["excerpt"] = "The waiver ends on January 1, 2030."
        active, _ = self.active(book(card, stamps))
        self.assertNotIn("policy_resilience", active)

    def test_unverified_company_exposure_source_voids_the_company_entry(self):
        card = make_card()
        stamps = stamps_for(card)
        del stamps[C.stamp_key(card["companies"][0]["source"]["url"], card["companies"][0]["source"]["excerpt"])]
        active, rejected = self.active(book(card, stamps))
        self.assertEqual(active, {})
        self.assertEqual(rejected[0]["reason"], "COMPANY_EXPOSURE_UNVERIFIED")

    def test_structurally_invalid_card_is_void_and_reported(self):
        raw = make_card()
        raw["contradictions"] = []
        active, rejected = self.active(book(cards={"test-card": raw}, stamps={}))
        self.assertEqual(active, {})
        self.assertEqual(rejected[0]["reason"], "CARD_INVALID")

    def test_rating_four_loses_support_when_its_numeric_source_fails_verification(self):
        raw = make_card()
        numeric = src(excerpt="Lead times reached 36 months.")
        plain = src("https://www.energy.gov/x.pdf", "Lead times are long.", "U.S. Department of Energy", "regulator")
        raw["factors"]["policy_resilience"].update(rating=4, sources=[numeric, plain])
        stamps = stamps_for(raw)
        stamps[C.stamp_key(numeric["url"], numeric["excerpt"])]["status"] = 500
        active, rejected = self.active(book(raw, stamps))
        self.assertNotIn("policy_resilience", active)
        self.assertIn("SUPPORT_TOO_THIN", [r["reason"] for r in rejected])

    def test_two_cards_on_one_factor_take_the_lower_rating(self):
        a, b = make_card(), make_card(id="other-card")
        b["factors"]["policy_resilience"]["rating"] = 1
        active, _ = self.active(book(cards={"test-card": a, "other-card": b}))
        self.assertEqual(active["policy_resilience"].rating, 1)
        self.assertEqual(active["policy_resilience"].card_ids, ("other-card", "test-card"))


class BottleneckIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = fx.build_store()

    def score(self, cards=None):
        return B.score_bottleneck(self.store, fx.market(), AS_OF, B.DEFAULT_PARAMS, [], None, None, cards=cards)

    def constraint(self, receipt):
        return receipt.detail["factors"]["constraint"]

    def test_without_cards_the_card_factors_stay_no_evidence(self):
        con = self.constraint(self.score())
        for name in ("policy_resilience", "substitution_difficulty", "architectural_necessity"):
            self.assertEqual(con[name]["rating"], NO_EVIDENCE, name)
            self.assertEqual(con[name]["status"], "NO_EVIDENCE", name)

    def test_valid_card_fills_only_the_factors_it_covers_as_proxy_with_a_card_ref(self):
        r = self.score(book())
        con = self.constraint(r)
        self.assertEqual((con["policy_resilience"]["rating"], con["policy_resilience"]["status"]), (3.0, "PROXY"))
        self.assertEqual(con["substitution_difficulty"]["rating"], 2.0)
        self.assertEqual({ref["kind"] for ref in con["policy_resilience"]["refs"]}, {KIND_CARD})
        self.assertEqual(con["policy_resilience"]["refs"][0]["url"], EIA)
        self.assertEqual(con["architectural_necessity"]["rating"], NO_EVIDENCE)           # 卡片没写的因子不动
        used = {u["factor"] for u in r.detail["evidence_cards"]["used"]}
        self.assertEqual(used, {"policy_resilience", "substitution_difficulty"})

    def test_company_own_evidence_is_never_overwritten_by_a_card(self):
        base = self.constraint(self.score())["funded_demand"]
        self.assertEqual(base["status"], "OBSERVED")
        r = self.score(book())
        self.assertEqual(self.constraint(r)["funded_demand"], base)
        kept = r.detail["evidence_cards"]["kept_company_evidence"]
        self.assertEqual([k["factor"] for k in kept], ["funded_demand"])
        self.assertTrue(kept[0]["conflict"])                                   # 公司 5 分 vs 卡片 1 分，分歧 ≥2 要标出来

    def test_expired_or_unverified_card_leaves_factors_at_no_evidence_not_zero_not_median(self):
        for b, why in ((book(), "expired"), (book(stamps={}), "unverified")):
            cards = b
            r = B.score_bottleneck(self.store, fx.market(as_of="2027-09-15"), "2027-09-15", B.DEFAULT_PARAMS, [], None, None, cards=cards) \
                if why == "expired" else self.score(cards)
            con = self.constraint(r)
            for name in ("policy_resilience", "substitution_difficulty"):
                self.assertEqual(con[name]["rating"], NO_EVIDENCE, (why, name))
                self.assertNotEqual(con[name]["rating"], 0, (why, name))
            self.assertEqual(r.detail["evidence_cards"]["used"], [], why)
            self.assertTrue(r.detail["evidence_cards"]["rejected"], why)

    def test_card_does_not_add_a_sec_link_and_does_not_change_the_other_dimensions(self):
        plain, carded = self.score(), self.score(book())
        for dim in ("capture", "mispricing", "evidence", "investability"):
            self.assertEqual(plain.detail["dimensions"][dim], carded.detail["dimensions"][dim], dim)
        self.assertEqual(plain.detail["factors"]["evidence"], carded.detail["factors"]["evidence"])
        self.assertEqual(plain.detail["gates"].keys(), carded.detail["gates"].keys())

    def test_card_adds_observed_factors_to_the_constraint_dimension_without_touching_the_params(self):
        before = copy.deepcopy(B.DEFAULT_PARAMS)
        plain, carded = self.score(), self.score(book())
        self.assertEqual(B.DEFAULT_PARAMS, before)
        self.assertGreater(len(carded.detail["dimensions"]["constraint"]["observed_factors"]),
                           len(plain.detail["dimensions"]["constraint"]["observed_factors"]))


class ThresholdsNotLoosenedTests(unittest.TestCase):
    """卡片机制不许动门槛：这里把 main 上的数字逐项钉死，任何放宽都会红。"""

    def test_gates_are_exactly_the_documented_values(self):
        self.assertEqual(B.DEFAULT_PARAMS["gates"], {"constraint_min": 60, "capture_min": 55, "evidence_min": 60, "investability_min": 50,
                                                      "mispricing_min": 45, "candidate_min_final": 62, "priority_min_final": 75})

    def test_coverage_requirements_are_exactly_the_documented_values(self):
        self.assertEqual(B.DEFAULT_PARAMS["coverage"], {
            "min_by_dimension": {"constraint": 0.4, "capture": 0.5, "mispricing": 0.4, "evidence": 0.5, "investability": 0.5},
            "required_factors": {"constraint": ["funded_demand", "current_tightness"], "capture": ["pricing_power", "unit_economics", "dilution_discipline"],
                                 "mispricing": ["valuation_asymmetry"], "evidence": ["primary_source_coverage"],
                                 "investability": ["liquidity", "balance_sheet_survival"]}})

    def test_param_floors_key_was_not_added_or_loosened(self):
        self.assertNotIn("param_floors", B.DEFAULT_PARAMS)        # 运行期参数文件同构检查（check_shape）不允许悄悄加键
        loaded, findings = B.load_bottleneck_params()
        self.assertEqual(findings, [])
        self.assertEqual(loaded, B.DEFAULT_PARAMS)

    def test_card_validation_limits_are_code_constants_not_scoring_gates(self):
        self.assertEqual((C.MAX_CARD_DAYS, C.MAX_FAST_FACTOR_DAYS), (366, 190))
        self.assertEqual((C.POOL_MIN_CAP_USD, C.POOL_MAX_CAP_USD), (3.0e8, 5.0e9))


class SnapshotPinningTests(unittest.TestCase):
    def test_payload_hash_changes_with_card_content_and_is_stable_otherwise(self):
        tmp = Path(tempfile.mkdtemp(prefix="sl-cards-"))
        try:
            card = make_card()
            (tmp / "test-card.yaml").write_text(to_yaml(card) + "\n", "utf-8")
            (tmp / C.VERIFICATION_FILE).write_text(json.dumps({"schema": C.VERIFICATION_SCHEMA, "entries": stamps_for(card)}), "utf-8")
            first = C.load_payload(tmp)
            self.assertEqual(first["unreadable"], {})
            self.assertEqual(first, C.load_payload(tmp))
            card["factors"]["policy_resilience"]["rating"] = 2
            (tmp / "test-card.yaml").write_text(to_yaml(card) + "\n", "utf-8")
            self.assertNotEqual(first["content_sha256"], C.load_payload(tmp)["content_sha256"])
            # 载荷读回来后规则结果与直接读目录一致
            active, _ = C.CardBook.from_payload(json.loads(json.dumps(C.load_payload(tmp)))).for_company(fx.CIK, AS_OF)
            self.assertEqual(active["policy_resilience"].rating, 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unreadable_card_file_is_reported_not_raised(self):
        tmp = Path(tempfile.mkdtemp(prefix="sl-cards-"))
        try:
            (tmp / "broken.yaml").write_text("a: 'single quoted'\n", "utf-8")
            payload = C.load_payload(tmp)
            self.assertIn("broken", payload["unreadable"])
            active, rejected = C.CardBook.from_payload(payload).for_company(fx.CIK, AS_OF)
            self.assertEqual(active, {})
            self.assertEqual(rejected[0]["reason"], "CARD_INVALID")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_directory_means_no_cards_not_an_error(self):
        payload = C.load_payload(Path(tempfile.gettempdir()) / "sl-cards-does-not-exist")
        self.assertEqual(payload["cards"], {})
        self.assertEqual(C.CardBook.from_payload(payload).for_company(fx.CIK, AS_OF), ({}, []))

    def test_old_snapshot_without_cards_behaves_as_no_cards(self):
        self.assertEqual(C.CardBook.from_payload(None).for_company(fx.CIK, AS_OF), ({}, []))


class ShippedCardsTests(unittest.TestCase):
    """随包的真实卡片：结构合格、每条来源（含公司申报）都有 200 + 摘录找到的印章。不断言「今天没过期」。"""

    @classmethod
    def setUpClass(cls):
        cls.payload = C.load_payload(C.CARDS_DIR)
        cls.book = C.CardBook.from_payload(cls.payload)

    def test_there_are_at_least_five_cards_covering_at_least_fifteen_distinct_supplier_companies(self):
        # 2026-10-01 主线裁定：证据卡只登记瓶颈的供给方（去掉 NNE、IMSR 两家反应堆开发商与 MYRG、CTRI、PRIM 三家施工承包商），
        # 第一批由 21 家变为 16 家；原「≥20 家」来自任务书，随裁定改为「≥15 家供给方」，补足到 20 家另开任务。
        self.assertGreaterEqual(len(self.book.cards), 5)
        self.assertEqual(self.book.invalid, {})
        self.assertEqual(self.payload["unreadable"], {})
        ciks = {c.cik for card in self.book.cards for c in card.companies}
        self.assertGreaterEqual(len(ciks), 15)
        self.assertFalse({"NNE", "IMSR", "MYRG", "CTRI", "PRIM"} & {c.symbol for card in self.book.cards for c in card.companies})

    def test_every_source_has_a_passing_stamp(self):
        for card in self.book.cards:
            sources = [s for f in card.factors.values() for s in f.sources] + [c.source for c in card.companies]
            for s in sources:
                stamp = self.book.stamps.get(s.key)
                self.assertIsNotNone(stamp, "%s 缺印章：%s" % (card.id, s.url))
                self.assertEqual((stamp["status"], stamp["excerpt_found"]), (200, True), "%s：%s" % (card.id, s.url))

    def test_every_factor_rating_is_backed_by_at_least_one_primary_source_and_a_basis(self):
        for card in self.book.cards:
            self.assertTrue(card.contradictions, card.id)
            for f in card.factors.values():
                self.assertTrue(f.basis.strip(), (card.id, f.name))
                self.assertTrue(f.sources, (card.id, f.name))
                for s in f.sources:
                    self.assertTrue(C.primary_host(s.url), s.url)

    def test_companies_are_inside_the_pool_cap_range(self):
        for card in self.book.cards:
            for c in card.companies:
                self.assertGreaterEqual(c.market_cap_usd, C.POOL_MIN_CAP_USD, (card.id, c.symbol))
                self.assertLessEqual(c.market_cap_usd, C.POOL_MAX_CAP_USD, (card.id, c.symbol))

    def test_shipped_cards_fill_factors_for_a_listed_company_on_the_day_after_verification(self):
        card = self.book.cards[0]
        stamp_day = max(s["checked"] for s in self.book.stamps.values())
        active, _ = self.book.for_company(card.companies[0].cik, stamp_day)
        self.assertTrue(active)


class CycleEndToEndTests(unittest.TestCase):
    """合成世界里跑完整研究周期，传入证据卡目录：瓶颈分支收据里必须出现 evidence_cards.used。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="sl-cards-cycle-"))
        cls.facts, cls.events, cls.bars, cls.universe = trc.build_world(cls.tmp)
        cls.cards_dir = cls.tmp / "cards"
        cls.cards_dir.mkdir()
        card = make_card()
        card["companies"][0]["cik"] = trc.fx.CIK + 1
        card["companies"][0]["source"]["url"] = "https://www.sec.gov/Archives/edgar/data/1234568/000123456726000004/doc0004.htm"
        (cls.cards_dir / "test-card.yaml").write_text(to_yaml(card) + "\n", "utf-8")
        (cls.cards_dir / C.VERIFICATION_FILE).write_text(json.dumps({"schema": C.VERIFICATION_SCHEMA, "entries": stamps_for(card)}), "utf-8")
        cls.hooks = trc.FakeHooks(cls.universe)
        base = RC.CycleConfig(project_root=trc.ROOT, work_dir=cls.tmp / "work", out_dir=cls.tmp / "out", facts_db=cls.facts,
                              events_db=cls.events, bars_dir=cls.bars, text_cache_dir=cls.tmp / "tc", structure_cache_dir=cls.tmp / "sc",
                              sec_cache_dir=cls.tmp / "sec", offline=True, python=sys.executable, universe_min_count=10,
                              evidence_cards_dir=cls.cards_dir)
        cls.summary = RC.run_cycle(base, cls.hooks, log=lambda m: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def verdicts(self):
        receipt = {r["branch_id"]: r for r in self.summary["receipts"]}["bottleneck-serenity-skill"]
        return {v["symbol"]: v for v in json.loads(Path(receipt["verdicts_file"]).read_text("utf-8"))["verdicts"]}

    def test_company_on_the_card_gets_factors_and_others_do_not(self):
        v = self.verdicts()
        used = {u["factor"] for u in v["T01"]["evidence"]["evidence_cards"]["used"]}
        self.assertIn("policy_resilience", used)
        self.assertEqual(v["T00"]["evidence"]["evidence_cards"]["used"], [])

    def test_snapshot_pins_the_card_payload(self):
        files = sorted((self.tmp / "work" / "snapshots").glob("evidence-*.json"))
        self.assertEqual(len(files), 1)
        snap = load_snapshot(files[0])
        payload = snap.evidence_cards()
        self.assertIsNotNone(payload)
        self.assertIn("test-card", payload["cards"])
        active, _ = C.CardBook.from_payload(payload).for_company(fx.CIK + 1, AS_OF)
        self.assertIn("policy_resilience", active)

    def test_snapshot_without_cards_returns_none(self):
        doc = {"as_of_date": AS_OF}
        self.assertIsNone(ES.EvidenceSnapshot.__dict__["evidence_cards"](types.SimpleNamespace(document=doc)))


if __name__ == "__main__":
    unittest.main()
