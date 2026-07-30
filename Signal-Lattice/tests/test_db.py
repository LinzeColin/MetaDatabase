import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_lattice.action import decide
from signal_lattice.clock import FakeClock
from signal_lattice.db import RuntimeDB


class T(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.schema = Path(__file__).resolve().parents[1] / "db/schema.sql"
        self.t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.db = RuntimeDB(self.root / "runtime.db", self.schema, FakeClock(self.t0))

    def tearDown(self):
        self.temp.cleanup()

    def test_idempotency(self):
        first, created = self.db.enqueue({"symbol": "AAA", "market": "US"}, "same-key")
        second, created_again = self.db.enqueue({"symbol": "AAA", "market": "US"}, "same-key")
        self.assertEqual(first, second)
        self.assertTrue(created)
        self.assertFalse(created_again)

    def test_fencing_and_atomic_action_outbox(self):
        job, _ = self.db.enqueue({"symbol": "AAA", "market": "US"}, "atomic")
        item = self.db.claim("worker")
        packet = decide(item["request"], {}, self.db.clock.now())
        self.db.complete(job, "worker", item["fencing_token"], packet)
        with self.db.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM actions").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM runtime_journal").fetchone()[0], 1)
            attempt = conn.execute("SELECT state,ended_at FROM attempts").fetchone()
            self.assertEqual(attempt["state"], "COMPLETED")
            self.assertIsNotNone(attempt["ended_at"])

    def test_stale_owner_rejected(self):
        job, _ = self.db.enqueue({"symbol": "AAA", "market": "US"}, "stale-owner")
        item = self.db.claim("worker")
        with self.assertRaisesRegex(RuntimeError, "STALE_OR_EXPIRED_FENCING_TOKEN"):
            self.db.complete(
                job,
                "wrong-worker",
                item["fencing_token"],
                decide(item["request"], {}, self.db.clock.now()),
            )

    def test_expired_lease_rejected_without_reclaim(self):
        job, _ = self.db.enqueue({"symbol": "AAA", "market": "US"}, "expired")
        item = self.db.claim("worker", lease_seconds=5)
        later = RuntimeDB(
            self.root / "runtime.db", self.schema, FakeClock(self.t0 + timedelta(seconds=6))
        )
        with self.assertRaisesRegex(RuntimeError, "STALE_OR_EXPIRED_FENCING_TOKEN"):
            later.complete(
                job,
                "worker",
                item["fencing_token"],
                decide(item["request"], {}, later.clock.now()),
            )

    def test_expired_job_is_reclaimed_with_monotonic_fence(self):
        job, _ = self.db.enqueue({"symbol": "AAA", "market": "US"}, "reclaim")
        first = self.db.claim("worker-1", lease_seconds=5)
        later = RuntimeDB(
            self.root / "runtime.db", self.schema, FakeClock(self.t0 + timedelta(seconds=6))
        )
        second = later.claim("worker-2", lease_seconds=5)
        self.assertEqual(second["job_id"], job)
        self.assertGreater(second["fencing_token"], first["fencing_token"])
        self.assertEqual(second["attempt_number"], 2)
        with later.connect() as conn:
            attempts = conn.execute(
                "SELECT number,state,error_code FROM attempts ORDER BY number"
            ).fetchall()
        self.assertEqual(
            [(row["number"], row["state"], row["error_code"]) for row in attempts],
            [(1, "ABANDONED", "LEASE_EXPIRED"), (2, "RUNNING", None)],
        )
        with self.assertRaisesRegex(RuntimeError, "STALE_OR_EXPIRED_FENCING_TOKEN"):
            later.complete(
                job,
                "worker-1",
                first["fencing_token"],
                decide(first["request"], {}, later.clock.now()),
            )
        later.complete(
            job,
            "worker-2",
            second["fencing_token"],
            decide(second["request"], {}, later.clock.now()),
        )

    def test_input_limits(self):
        with self.assertRaisesRegex(ValueError, "INVALID_IDEMPOTENCY_KEY"):
            self.db.enqueue({"symbol": "AAA"}, "")
        job, _ = self.db.enqueue({"symbol": "AAA"}, "valid")
        self.assertTrue(job)
        with self.assertRaisesRegex(ValueError, "INVALID_LEASE_SECONDS"):
            self.db.claim("worker", lease_seconds=1)
