"""Tests for thresholds, episode metrics, bootstrap and the train/test wall (protocol §4-7)."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tp import metrics as m  # noqa: E402
from tp import dataset, evaluate  # noqa: E402
from tp import train  # noqa: E402


class ThresholdTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        self.y = rng.random(20_000) < 0.01
        self.s = np.where(self.y, rng.normal(2, 1, 20_000), rng.normal(0, 1, 20_000)).round(2)  # many ties

    def rate(self, th):
        a = self.s >= th
        return a[~self.y].mean() * (1 - m.P_MAIN) + a[self.y].mean() * m.P_MAIN

    def test_lowest_threshold_within_budget(self):
        for budget in m.BUDGETS.values():
            th = m.threshold_at_budget(self.s, self.y, budget)
            self.assertLessEqual(self.rate(th), budget)
            lower = self.s[self.s < th].max()        # the next distinct score down must break the budget
            self.assertGreater(self.rate(lower), budget)

    def test_no_alert_fits(self):
        self.assertEqual(m.threshold_at_budget(np.ones(10), np.zeros(10, bool), 1e-4), float("inf"))

    def test_fp_tp_operating_point(self):
        th = m.threshold_at_fp_tp(self.s, self.y, ratio=5.0)
        a = self.s >= th
        self.assertLessEqual(m.fp_per_tp(a[~self.y].mean(), a[self.y].mean(), m.P_MAIN), 5.0)


def ep_rows(amounts, scored=None, episode="ep"):
    n = len(amounts)
    return pd.DataFrame({"episode_id": episode, "event_id": [f"{episode}-{i}" for i in range(n)], "ts": range(n),
                         "amount_thb": amounts, "scored": scored if scored is not None else [True] * n})


class EpisodeOutcomeTest(unittest.TestCase):
    def outcome(self, rows, alerted):
        return m.episode_outcomes(rows, alerted).iloc[0]

    def test_warning_before_largest_and_exposure(self):
        o = self.outcome(ep_rows([100, 500, 2000, 800]), {"ep-1"})
        self.assertTrue(o.warned_before_largest)
        self.assertAlmostEqual(o.exposure, 100 / 3400)

    def test_warning_on_the_largest_counts(self):
        self.assertTrue(self.outcome(ep_rows([100, 500, 2000, 800]), {"ep-2"}).warned_before_largest)

    def test_warning_after_largest_is_late_not_missed(self):
        o = self.outcome(ep_rows([100, 500, 2000, 800]), {"ep-3"})
        self.assertFalse(o.warned_before_largest)
        self.assertFalse(o.missed)
        self.assertAlmostEqual(o.exposure, 2600 / 3400)

    def test_missed_and_invisible_rows(self):
        o = self.outcome(ep_rows([100, 5000], scored=[True, False]), {"ep-1"})   # alert on an invisible row
        self.assertTrue(o.missed)
        self.assertEqual(o.exposure, 1.0)

    def test_equal_amounts_use_the_first(self):
        self.assertFalse(self.outcome(ep_rows([1000, 1000]), {"ep-1"}).warned_before_largest)


class BootstrapTest(unittest.TestCase):
    def test_deterministic_and_covers_the_estimate(self):
        num, den = np.array([1, 0, 2, 1, 3.0]), np.array([2, 1, 2, 2, 4.0])
        a, b = m.bootstrap(num, den, reps=500), m.bootstrap(num, den, reps=500)
        np.testing.assert_array_equal(a, b)
        lo, hi = m.ci(a[:, 0])
        self.assertTrue(lo <= num.sum() / den.sum() <= hi)

    def test_verdict(self):
        self.assertEqual([m.verdict(0.01, 0.2), m.verdict(-0.2, -0.01), m.verdict(-0.1, 0.1)],
                         ["ผ่าน", "ไม่ผ่าน", "สรุปไม่ได้"])


class RuleTest(unittest.TestCase):
    def test_rules(self):
        t = pd.DataFrame({"relationship_age_observed_days": [None, 40.0, None],
                          "amount_abs": [50_000.0, 50_000.0, 900.0],
                          "seed_like_inbound_count_90d": [2, 1, 0],
                          "escalation_vs_pair": [None, 2.0, None],
                          "escalation_vs_new_cluster": [10.0, 4.0, None],
                          "escalation_vs_established": [30.0, 3.0, 1.0]})
        np.testing.assert_array_equal(train.arm0_score(t), [50_000.0, -1.0, 900.0])
        np.testing.assert_array_equal(train.rule_t2_score(t, 1), [10.0, 2.0, -1.0])   # min of pair/cluster
        np.testing.assert_array_equal(train.rule_t2_score(t, 2), [10.0, -1.0, -1.0])


class TrainTestWallTest(unittest.TestCase):
    def test_load_never_returns_test_rows(self):
        feats = pd.DataFrame({"event_id": ["a", "b", "c", "d"], "split": ["train", "val", "test", "val"],
                              "in_t2": [True, True, True, False]})
        eps = pd.DataFrame({"episode_id": ["e1", "e2"], "split": ["val", "test"], "family": "A", "is_holdout": 0})
        ep_events = pd.DataFrame({"episode_id": ["e1", "e2"], "event_id": ["b", "c"]})
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            eps.to_parquet(d / "episodes.parquet")
            ep_events.to_parquet(d / "episode_events.parquet")
            feats.to_parquet(d / "features.parquet")
            tr, va, ev = train.load(d)
            feats.loc[2, "event_id"] = "changed"             # altering test rows must not change what train sees
            feats.to_parquet(d / "features.parquet")
            tr2, va2, _ = train.load(d)
        self.assertEqual((tr.event_id.tolist(), va.event_id.tolist(), ev.event_id.tolist()), (["a"], ["b"], ["b"]))
        pd.testing.assert_frame_equal(va, va2)
        pd.testing.assert_frame_equal(tr, tr2)

    def test_manifest_rejects_changed_source_and_mimicry(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "m0"
            variant = Path(tmp) / "m0.5"
            profile = Path(tmp) / "dataset_profile_m0.json"
            d.mkdir()
            variant.mkdir()
            (d / "labels.parquet").write_bytes(b"original labels")
            (variant / "features.parquet").write_bytes(b"original features")
            profile.write_bytes(b"original profile")
            manifest = {"code_sha256": {}, "lightgbm": {"model_sha256": {}},
                        "data_sha256": {"labels.parquet": train.sha256(d / "labels.parquet")},
                        "profile_sha256": train.sha256(profile),
                        "mimicry_sha256": {"m0.5": {"features.parquet": train.sha256(variant / "features.parquet")}}}
            original_artifacts = evaluate.ARTIFACTS
            evaluate.ARTIFACTS = Path(tmp)
            try:
                evaluate.check_frozen(manifest, d, [variant])
                (variant / "features.parquet").write_bytes(b"changed")
                with self.assertRaises(SystemExit):
                    evaluate.check_frozen(manifest, d, [variant])
                (variant / "features.parquet").write_bytes(b"original features")
                (d / "labels.parquet").write_bytes(b"changed")
                with self.assertRaises(SystemExit):
                    evaluate.check_frozen(manifest, d, [variant])
                (d / "labels.parquet").write_bytes(b"original labels")
                profile.write_bytes(b"changed")
                with self.assertRaises(SystemExit):
                    evaluate.check_frozen(manifest, d, [variant])
            finally:
                evaluate.ARTIFACTS = original_artifacts


class IntentCountsTest(unittest.TestCase):
    def test_holdout_alerts_do_not_break_tp_fp_total(self):
        rows = pd.DataFrame({"y_true": [True, True, False], "episode_id": ["main", "holdout", None],
                             "ring_id": ["r1", "r2", None], "payer_token": ["v1", "v2", "legit"]})
        scores = {a: np.ones(3) for a in evaluate.ORDER}
        thresholds = {a: 0.5 for a in evaluate.ORDER}
        out = evaluate.intent_block(rows, scores, thresholds, {"holdout"})
        self.assertEqual(out["holdout_positive_intents_excluded"], 1)
        self.assertEqual(out["arm2"]["alerts"], out["arm2"]["tp"] + out["arm2"]["fp"])
        self.assertEqual((out["arm2"]["alerts"], out["arm2"]["tp"], out["arm2"]["fp"]), (2, 1, 1))
        self.assertEqual(out["arm2"]["all_test_alerts"], 3)


class Deviation2Test(unittest.TestCase):
    """Pre-registered before train (PROTOCOL_DEVIATIONS.md #2): arm 2e, fail-closed sets, budget parity, G3 counts."""

    def test_arm2e_is_generic_plus_escalation_only(self):
        from tp.features import GENERIC, TRUST_ESCALATION, TRUST_SEED
        self.assertEqual(train.ARMS["arm2e"], GENERIC + TRUST_ESCALATION)
        self.assertFalse(set(train.ARMS["arm2e"]) & set(TRUST_SEED))
        self.assertEqual(evaluate.PAIRS["H1s arm2-arm2e"], ("arm2", "arm2e"))

    def episodes(self):
        rows = [("A", 0, ""), ("A", 0, "SPLIT"), ("A", 0, "LONG_GAP|ON_US_HOP"), ("D", 0, ""),
                ("A", 1, "FRAGMENTED_SEED"), ("A", 1, "AGED_RECEIVER")]
        e = pd.DataFrame(rows, columns=["family", "is_holdout", "variant"])
        return e.assign(episode_id=[f"e{i}" for i in range(len(e))], ring_id=[f"r{i}" for i in range(len(e))])

    def test_populations_fail_closed(self):
        e = self.episodes()
        self.assertIn("holdout_AGED_RECEIVER", evaluate.populations(e, "test"))
        val = evaluate.populations(e[~e.is_holdout.astype(bool)], "val")   # holdouts exist in test only
        self.assertFalse([k for k in val if k.startswith("holdout_")])
        for broken in (e[e.family != "D"], e.assign(family=e.family.replace("A", "SEED_LADDER")),
                       e[e.variant != "AGED_RECEIVER"]):
            with self.assertRaises(SystemExit):
                evaluate.populations(broken, "test")

    def test_win_bought_with_extra_false_alerts_is_downgraded(self):
        def pairs(v):
            return {f"{n} {k}": {"verdict": v} for n in evaluate.PAIRS for k in ("recall", "exposure")}
        budget = 0.002
        fpr = {a: 0.001 for a in evaluate.ORDER} | {"arm2": 0.001 + 0.25 * budget}
        p = pairs("ผ่าน")
        evaluate.confound(p, fpr, budget)
        self.assertEqual(p["H1 arm2-arm1 recall"]["verdict"], "สรุปไม่ได้ (งบจริงไม่เท่ากัน)")
        self.assertEqual(p["H2 rule-arm0 recall"]["verdict"], "ผ่าน")          # same spend: untouched
        q = pairs("ไม่ผ่าน")
        evaluate.confound(q, fpr, budget)
        self.assertEqual(q["H1 arm2-arm1 recall"]["verdict"], "ไม่ผ่าน")       # arm 1 won while spending less
        self.assertEqual(q["H5 arm3-arm2 recall"]["verdict"], "สรุปไม่ได้ (งบจริงไม่เท่ากัน)")  # arm 2 won by spending more

    def test_hard_negative_counts_and_missing_group(self):
        n = len(dataset.HN_GROUPS) * 4
        rows = pd.DataFrame({"hn_group": list(dataset.HN_GROUPS) * 4, "y_true": False,
                             "payer_token": [f"s{i}" for i in range(n)]})
        th = {a: 0.5 for a in evaluate.ORDER}
        out = evaluate.hn_block(rows, {a: np.ones(n) for a in evaluate.ORDER}, th)
        self.assertEqual((out["FAMILY"]["alerts"]["arm2"], out["FAMILY"]["too_few_alerts"]), (4, True))
        rest = rows[rows.hn_group != "FAMILY"].reset_index(drop=True)
        with self.assertRaises(SystemExit):
            evaluate.hn_block(rest, {a: np.ones(len(rest)) for a in evaluate.ORDER}, th)

    def test_rehearsal_never_reads_test_rows(self):
        feats = pd.DataFrame({"event_id": ["a", "b", "c", "d"], "split": ["train", "val", "test", "val"],
                              "in_t2": [True, True, True, False], "ring_payer": [False, False, False, True]})
        eps = pd.DataFrame({"episode_id": ["e1", "e2"], "split": ["val", "test"]})
        ep_events = pd.DataFrame({"episode_id": ["e1", "e2"], "event_id": ["b", "c"]})
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            feats.to_parquet(d / "features.parquet")
            eps.to_parquet(d / "episodes.parquet")
            ep_events.to_parquet(d / "episode_events.parquet")
            rows, e, ev, ring = evaluate.load_split(d, "val")
        self.assertEqual((rows.event_id.tolist(), e.episode_id.tolist(), ev.event_id.tolist(), ring.event_id.tolist()),
                         (["b"], ["e1"], ["b"], ["d"]))

    def test_cold_start_days_are_never_fitted(self):
        """Deviation 3: days 90-119 are history only."""
        day = [int(dataset.DAY0 + d * 86_400) for d in (90, 119.99, 120, 269)]
        self.assertEqual(train.fit_rows(pd.DataFrame({"ts": day})).ts.tolist(), day[2:])

    def test_g4_single_feature_audit(self):
        t = pd.DataFrame({f: np.nan for f in dataset.FEATURES}, index=range(6)).assign(
            y_true=[True, True, False, False, False, False],
            amount_abs=[1.0, 2, 5, 6, 7, 8],             # low = scam: separates perfectly in reverse
            ladder_steps=[3.0, np.nan, 0, 0, 1, 0])       # a missing positive ranks last, not first
        ap = train.single_feature_ap(t)
        self.assertEqual(ap["amount_abs"], 1.0)
        self.assertLess(ap["ladder_steps"], 1.0)
        self.assertNotIn("return_ratio", ap)              # all missing: nothing to audit


if __name__ == "__main__":
    unittest.main()
