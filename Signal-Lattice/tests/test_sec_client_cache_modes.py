"""SEC 客户端新增的三种取数方式：压缩缓存、不落盘、不可变文件命中缓存后不再发请求。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_evidence_sec_client import FakeClock, FakeResponse, ScriptedOpener

from signal_lattice.evidence import RateLimiter, SecClient


def make(script, cache_dir=None, compress=False):
    clock = FakeClock()
    opener = ScriptedOpener(script)
    client = SecClient(cache_dir, limiter=RateLimiter(clock=clock, sleep=clock.sleep), opener=opener,
                       sleep=clock.sleep, compress_cache=compress)
    return client, opener


class CacheModeTests(unittest.TestCase):
    def test_compressed_cache_round_trips_and_is_smaller_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = b"abc " * 5000
            client, opener = make([FakeResponse(body, {"ETag": "x"})], Path(tmp), compress=True)
            self.assertEqual(client.get_bytes("https://sec/x"), body)
            stored = [p for p in Path(tmp).rglob("*.body.gz")]
            self.assertEqual(len(stored), 1)
            self.assertLess(stored[0].stat().st_size, len(body) // 5)
            fresh, opener2 = make([FakeResponse(b"", {})], Path(tmp), compress=True)
            fresh._opener = lambda request, timeout: (_ for _ in ()).throw(AssertionError("immutable 文件不该再发请求"))
            self.assertEqual(fresh.get_bytes("https://sec/x", immutable=True), body)

    def test_cache_false_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = make([FakeResponse(b"hello", {})], Path(tmp))
            self.assertEqual(client.get_bytes("https://sec/y", cache=False), b"hello")
            self.assertEqual(list(Path(tmp).rglob("*.body*")), [])

    def test_default_behaviour_is_unchanged(self):
        client, opener = make([FakeResponse(b"{}", {"ETag": "abc"})])
        client.get_bytes("https://sec/z")
        self.assertEqual(len(opener.requests), 1)


if __name__ == "__main__":
    unittest.main()
