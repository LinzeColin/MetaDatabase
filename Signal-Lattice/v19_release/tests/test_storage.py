from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from signal_lattice_v19.storage import RuntimeStorage, StateConflictError


class RuntimeStorageTests(unittest.TestCase):
    def test_corrupt_strategy_state_is_quarantined_and_requires_explicit_recovery(self):
        canonical = {"provider_code": "AU.SPY", "code": "SPY", "last_price": 100.0}
        known = {"provider_code": "AU.IVV", "code": "IVV", "last_price": 101.0}
        with TemporaryDirectory() as tmp:
            storage = RuntimeStorage(Path(tmp))
            storage.bootstrap(canonical)
            storage.save_state(known)
            storage.state_file.write_text("{not-json", encoding="utf-8")

            recovered = storage.load_state(canonical)

            self.assertEqual(recovered, known)
            self.assertTrue(storage.has_state_conflict)
            self.assertEqual(storage.state_conflict["state"], "CONFLICT")
            self.assertTrue(storage.state_conflict_file.is_file())
            self.assertEqual(len(list((storage.root / "conflicts").glob("*.corrupt.json"))), 1)
            with self.assertRaises(StateConflictError):
                storage.save_state(canonical)

            storage.resolve_state_conflict(known, "reviewed last-known strategy state")

            self.assertFalse(storage.has_state_conflict)
            self.assertEqual(storage.load_state(canonical), known)


if __name__ == "__main__":
    unittest.main()
