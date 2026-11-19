"""Generator integrity checks on disposable synthetic data; no frozen test rows are read."""
import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tp import sim  # noqa: E402


class SimulatorTest(unittest.TestCase):
    def test_reproducible_and_mimicry_isolated_to_test(self):
        (ROOT / "data").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "data") as tmp:
            base = Path(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.save(20261003, 0, base / "a", scale=0.25)
                sim.save(20261003, 0, base / "repeat", scale=0.25)
                sim.save(20261003, 1, base / "mimic", scale=0.25)
            for name in ("events", "labels", "episodes", "ring_accounts", "hn_events"):
                def digest(folder):
                    with (base / folder / f"{name}.parquet").open("rb") as f:
                        return hashlib.file_digest(f, "sha256").digest()
                self.assertEqual(digest("a"), digest("repeat"), name)
            cutoff = sim.DAY0 + 330 * sim.DAY
            for name, field in (("events", "ts"), ("labels", "event_ts")):
                left = pq.read_table(base / "a" / f"{name}.parquet", filters=[(field, "<", cutoff)])
                right = pq.read_table(base / "mimic" / f"{name}.parquet", filters=[(field, "<", cutoff)])
                self.assertTrue(left.equals(right), name)
            with (base / "a" / "events.parquet").open("rb") as f:
                original = hashlib.file_digest(f, "sha256").digest()
            with (base / "mimic" / "events.parquet").open("rb") as f:
                mimicked = hashlib.file_digest(f, "sha256").digest()
            self.assertNotEqual(original, mimicked)


if __name__ == "__main__":
    unittest.main()
