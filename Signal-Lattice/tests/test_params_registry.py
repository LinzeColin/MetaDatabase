"""每轮读 Registry 与各 Skill 的 params：版本与 hash、GitHub 原始地址带 ETag 拉取、schema 校验通过才生效，
坏参数/网络失败退回 Last-Known-Good，版本变化后新参数生效；只拉数据（JSON），不拉代码。"""

from __future__ import annotations

import copy
import io
import json
import shutil
import tempfile
import unittest
import urllib.error
from pathlib import Path

import signal_lattice
from signal_lattice import params_registry as PR
from signal_lattice.branches import bottleneck as B

ROOT = Path(signal_lattice.__file__).resolve().parents[2]
BN = "bottleneck-serenity-skill"
PARAMS_URL = "https://raw.githubusercontent.com/LinzeColin/MetaDatabase/%s/Signal-Lattice/Stock_Skill/bottleneck-serenity-skill/runtime/params.json"
REGISTRY_URL = "https://raw.githubusercontent.com/LinzeColin/MetaDatabase/%s/Signal-Lattice/Stock_Skill/REGISTRY.json"


def params_bytes(version="0.0.0.9", mutate=None) -> bytes:
    p = copy.deepcopy(B.DEFAULT_PARAMS)
    p["params_version"] = version
    if mutate:
        mutate(p)
    return (json.dumps(p, indent=2) + "\n").encode("utf-8")


class FakeGitHub:
    """按 URL 返回内容并支持 ETag；calls 记录每次请求的 (url, if_none_match)。"""

    def __init__(self):
        self.bodies = {}
        self.etags = {}
        self.calls = []
        self.down = False

    def set(self, url, body, etag):
        self.bodies[url], self.etags[url] = body, etag

    def __call__(self, url, etag):
        self.calls.append((url, etag))
        if self.down:
            raise PR.FetchError("URLError for " + url)
        if url not in self.bodies:
            raise PR.FetchError("HTTP 404 for " + url)
        if etag and etag == self.etags[url]:
            return PR.FetchResult(304, None, etag)
        return PR.FetchResult(200, self.bodies[url], self.etags[url])


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sl-params-test-"))
        self.gh = FakeGitHub()
        self.specs = {k: v for k, v in PR.default_specs().items()}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def resolver(self, fetcher="gh", ref="main", root=ROOT):
        return PR.ParamsResolver(root, self.tmp / "state", ref=ref, fetcher=self.gh if fetcher == "gh" else fetcher, specs=self.specs)

    def local_bytes(self) -> bytes:
        return (ROOT / "Stock_Skill" / BN / "runtime" / "params.json").read_bytes()

    def test_offline_first_run_adopts_local_file_as_lkg_and_reports_version_and_hash(self):
        resolution = self.resolver(fetcher=None).resolve()
        skill = resolution.skills[BN]
        self.assertEqual((skill.source, skill.params_version), (PR.SOURCE_LOCAL, B.DEFAULT_PARAMS["params_version"]))
        self.assertEqual(skill.params_sha256, PR.sha256_hex(self.local_bytes()))
        self.assertEqual(Path(skill.active_path).read_bytes(), self.local_bytes())
        self.assertTrue((self.tmp / "state" / "lkg" / (BN + ".json")).is_file())
        self.assertEqual(skill.findings, [])
        self.assertEqual(resolution.registry_source, PR.SOURCE_LOCAL)
        self.assertEqual(skill.registry_version, "0.0.0.1")
        self.assertIn(BN, resolution.active_skills())
        self.assertEqual(len(resolution.active_skills()), 5)          # 五个 Skill 都是 Active、都有对应分支

    def test_new_remote_version_takes_effect_and_becomes_the_new_lkg(self):
        self.gh.set(PARAMS_URL % "main", params_bytes("0.0.0.9"), '"v9"')
        skill = self.resolver().resolve().skills[BN]
        self.assertEqual((skill.source, skill.params_version), (PR.SOURCE_REMOTE, "0.0.0.9"))
        self.assertEqual(json.loads(Path(skill.active_path).read_text("utf-8"))["params_version"], "0.0.0.9")
        self.assertIn("PARAMS_UPDATED", [f["code"] for f in skill.findings])
        # 之后远端不可用：仍是刚采纳的新版本（LKG 已更新），而不是回到旧版本
        self.gh.down = True
        again = self.resolver().resolve().skills[BN]
        self.assertEqual((again.source, again.params_version), (PR.SOURCE_LKG, "0.0.0.9"))
        self.assertIn("REMOTE_PARAMS_UNAVAILABLE", [f["code"] for f in again.findings])

    def test_bad_remote_params_keep_the_last_known_good_and_record_a_finding(self):
        self.resolver(fetcher=None).resolve()                                   # 先有一个 LKG（本地版本）
        cases = {
            "not json": b"import os; os.system('rm -rf /')",
            "missing keys": json.dumps({"schema": "signal-lattice-branch-params/1", "skill": BN, "params_version": "9.9.9.9"}).encode(),
            "gates out of range": params_bytes("0.0.0.9", lambda p: p["gates"].update(constraint_min=500)),
            "weights do not sum": params_bytes("0.0.0.9", lambda p: p["dimension_weights"]["constraint"].update(funded_demand=99)),
            "not an object": b"[1,2,3]",
        }
        for label, body in cases.items():
            self.gh.set(PARAMS_URL % "main", body, '"bad-%s"' % label)
            skill = self.resolver().resolve().skills[BN]
            self.assertEqual((skill.source, skill.params_version), (PR.SOURCE_LKG, B.DEFAULT_PARAMS["params_version"]), label)
            self.assertIn("REMOTE_PARAMS_INVALID", [f["code"] for f in skill.findings], label)
            self.assertEqual(Path(skill.active_path).read_bytes(), self.local_bytes(), label)      # 生效的仍是校验过的旧字节

    def test_network_failure_uses_lkg_with_a_finding(self):
        self.resolver(fetcher=None).resolve()
        self.gh.down = True
        resolution = self.resolver().resolve()
        skill = resolution.skills[BN]
        self.assertEqual(skill.source, PR.SOURCE_LKG)
        self.assertIn("REMOTE_PARAMS_UNAVAILABLE", [f["code"] for f in skill.findings])
        self.assertIn("REMOTE_REGISTRY_UNAVAILABLE", [f["code"] for f in resolution.findings])
        self.assertEqual(resolution.registry_source, PR.SOURCE_LOCAL)

    def test_etag_is_sent_and_304_reuses_the_cached_body(self):
        self.gh.set(PARAMS_URL % "main", params_bytes("0.0.0.9"), '"v9"')
        self.resolver().resolve()
        self.gh.calls.clear()
        skill = self.resolver().resolve().skills[BN]
        sent = dict(self.gh.calls)
        self.assertEqual(sent[PARAMS_URL % "main"], '"v9"')                      # 第二次带 If-None-Match
        self.assertEqual((skill.source, skill.params_version), (PR.SOURCE_REMOTE, "0.0.0.9"))
        self.assertEqual(skill.findings, [])                                     # 内容没变：不重复记「已更新」

    def test_ref_is_configurable_and_only_data_files_are_requested(self):
        self.gh.set(PARAMS_URL % "release-x", params_bytes("0.0.0.11"), '"r"')
        skill = self.resolver(ref="release-x").resolve().skills[BN]
        self.assertEqual(skill.params_version, "0.0.0.11")
        urls = {url for url, _ in self.gh.calls}
        self.assertIn(REGISTRY_URL % "release-x", urls)
        for url in urls:
            self.assertTrue(url.startswith("https://raw.githubusercontent.com/LinzeColin/MetaDatabase/release-x/Signal-Lattice/Stock_Skill/"), url)
            self.assertTrue(url.endswith("REGISTRY.json") or url.endswith("/runtime/params.json"), url)   # 只拉数据，不拉代码
        self.assertFalse([u for u in urls if u.endswith((".py", ".zip", ".sh"))])

    def test_local_release_newer_than_lkg_is_adopted_when_remote_is_unavailable(self):
        old = self.resolver(fetcher=None)
        (self.tmp / "state" / "lkg").mkdir(parents=True)
        (self.tmp / "state" / "lkg" / (BN + ".json")).write_bytes(params_bytes("0.0.0.0"))   # 一份更老的 LKG
        skill = old.resolve().skills[BN]
        self.assertEqual((skill.source, skill.params_version), (PR.SOURCE_LOCAL, B.DEFAULT_PARAMS["params_version"]))
        self.assertIn("PARAMS_UPDATED", [f["code"] for f in skill.findings])

    def test_content_change_without_version_bump_is_flagged(self):
        self.resolver(fetcher=None).resolve()
        self.gh.set(PARAMS_URL % "main", params_bytes(B.DEFAULT_PARAMS["params_version"], lambda p: p["gates"].update(constraint_min=61)), '"c"')
        skill = self.resolver().resolve().skills[BN]
        self.assertEqual(skill.source, PR.SOURCE_REMOTE)
        self.assertIn("PARAMS_CONTENT_CHANGED_WITHOUT_VERSION_BUMP", [f["code"] for f in skill.findings])

    def test_invalid_remote_registry_falls_back_to_local_and_no_registry_blocks(self):
        self.gh.set(REGISTRY_URL % "main", b'{"skills": []}', '"r"')
        resolution = self.resolver().resolve()
        self.assertEqual(resolution.registry_source, PR.SOURCE_LOCAL)
        self.assertIn("REMOTE_REGISTRY_INVALID", [f["code"] for f in resolution.findings])
        empty = self.tmp / "empty-root"
        empty.mkdir()
        with self.assertRaises(PR.RegistryError):
            PR.ParamsResolver(empty, self.tmp / "state2", fetcher=None, specs=self.specs).resolve()

    def test_remote_registry_can_deactivate_a_skill_and_unknown_skills_are_not_dispatched(self):
        registry = json.loads((ROOT / "Stock_Skill" / "REGISTRY.json").read_text("utf-8"))
        for skill in registry["skills"]:
            if skill["id"] == "equity-event-atlas":
                skill["current"] = False
        registry["skills"].append({**registry["skills"][0], "id": "brand-new-skill", "canonical_project_path": "Signal-Lattice/Stock_Skill/brand-new-skill"})
        self.gh.set(REGISTRY_URL % "main", json.dumps(registry).encode(), '"r2"')
        resolution = self.resolver().resolve()
        self.assertNotIn("equity-event-atlas", resolution.active_skills())
        self.assertNotIn("brand-new-skill", resolution.active_skills())
        self.assertIn("SKILL_NOT_IMPLEMENTED_IN_RUNTIME", [f["code"] for f in resolution.skills["brand-new-skill"].findings])
        self.assertIn("REGISTRY_REMOTE_DIFFERS_FROM_LOCAL", [f["code"] for f in resolution.findings])

    def test_skill_without_external_params_reports_registry_version_only(self):
        skill = self.resolver(fetcher=None).resolve().skills["global-equity-lead-lag-atlas"]
        self.assertEqual((skill.params_version, skill.active_path, skill.registry_current), (None, None, True))

    def test_to_dict_is_json_serializable_and_carries_versions_and_hashes(self):
        payload = json.loads(json.dumps(self.resolver(fetcher=None).resolve().to_dict()))
        self.assertEqual(len(payload["registry_sha256"]), 64)
        self.assertTrue(all("registry_version" in s for s in payload["skills"].values()))


class HttpFetcherTests(unittest.TestCase):
    def test_refuses_urls_outside_raw_githubusercontent(self):
        with self.assertRaises(PR.FetchError):
            PR.http_fetcher("https://example.com/x.json", None)

    def test_maps_304_and_other_http_errors(self):
        def opener_304(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", {}, io.BytesIO(b""))

        def opener_500(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 500, "boom", {}, io.BytesIO(b""))

        url = REGISTRY_URL % "main"
        self.assertEqual(PR.http_fetcher(url, '"e"', opener=opener_304), PR.FetchResult(304, None, '"e"'))
        with self.assertRaises(PR.FetchError):
            PR.http_fetcher(url, None, opener=opener_500)

    def test_sends_if_none_match_and_rejects_oversize_bodies(self):
        seen = {}

        class Response:
            headers = {"ETag": '"z"'}

            def __init__(self, body):
                self.body = body

            def read(self, n):
                return self.body[:n]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(request, timeout):
            seen["inm"] = request.get_header("If-none-match")
            return Response(b"x" * (PR.MAX_BODY_BYTES + 10))

        with self.assertRaises(PR.FetchError):
            PR.http_fetcher(REGISTRY_URL % "main", '"old"', opener=opener)
        self.assertEqual(seen["inm"], '"old"')


if __name__ == "__main__":
    unittest.main()
