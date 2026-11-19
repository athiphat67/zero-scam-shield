"""Leakage and correctness tests for the G-0 pipeline (protocol §6)."""
import math
import random
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tp import dataset as ds  # noqa: E402
from tp.features import DAY, Event, State, replay  # noqa: E402

D0 = ds.DAY0
METADATA = {"episode_id", "scenario", "ring_id", "is_synthetic", "synthetic_fields", "generator_version", "label",
            "event_role", "subject_token", "family", "variant", "is_holdout", "hn_id", "hn_group", "y_true", "y_train"}


def toy_events(n_acc=25, n_ev=1500, days=200, seed=0):
    """Random traffic among a few accounts: many repeat pairs, same-second collisions and rows to exclude."""
    rnd = random.Random(seed)
    rows = []
    for i in range(n_ev):
        a, b = rnd.sample(range(n_acc), 2)
        ts = D0 + rnd.randrange(days) * DAY + rnd.choice((0, 3600, 7200))
        rows.append(row(f"e{i:05d}", ts, f"t{a}", f"t{b}", rnd.choice((100, 250.5, 800, 1000, 3000, 20000)),
                        txn_type="P2P" if rnd.random() < 0.95 else "MERCHANT",
                        payee_type="PERSON" if rnd.random() < 0.97 else "MERCHANT",
                        route_scope="CROSS_BANK" if rnd.random() < 0.85 else "ON_US",
                        event_status="SETTLED" if rnd.random() < 0.98 else "FAILED"))
    return pd.DataFrame(rows)


def row(event_id, ts, payer, payee, baht, txn_type="P2P", payee_type="PERSON", route_scope="CROSS_BANK",
        event_status="SETTLED"):
    return {"event_id": event_id, "ts": ts, "ingested_at": ts, "payer_token": payer, "payee_token": payee,
            "payer_bank": "B1", "payee_bank": "B2", "amount_thb": baht, "txn_type": txn_type,
            "payer_type": "PERSON", "payee_type": payee_type, "channel": "MOBILE", "rail": "PROMPTPAY",
            "route_scope": route_scope, "event_status": event_status, "source": "TEST", "is_synthetic": 1,
            "synthetic_fields": "ALL"}


def truncated(events, e):
    """Features of intent e from a fresh state that only ever saw events strictly before e.ts."""
    state = State()
    for x in events:
        if x.ts < e.ts:
            state.add(x)
    return state.features(e.payer, e.payee, e.amount, e.ts)


def pit_mismatches(scored, events, n=60):
    sample = random.Random(1).sample(sorted(scored), min(n, len(scored)))
    by_id = {e.event_id: e for e in events}
    return sum(scored[i] != truncated(events, by_id[i]) for i in sample)


def leaky_replay(events):
    """The classic <= bug: the current event (and same-second events) is visible when scoring."""
    state = State()
    for e in sorted(events, key=lambda e: e.ts):
        if state.add(e) and e.txn_type == "P2P":
            yield e, state.features(e.payer, e.payee, e.amount, e.ts + 1)


class PointInTimeTest(unittest.TestCase):
    def setUp(self):
        self.events = ds.to_events(ds.switch_view(toy_events()))

    def test_replay_equals_history_strictly_before_t(self):
        scored = {e.event_id: f for e, f in replay(self.events)}
        self.assertEqual(pit_mismatches(scored, self.events), 0)

    def test_checker_catches_a_planted_leak(self):
        scored = {e.event_id: f for e, f in leaky_replay(self.events)}
        self.assertGreater(pit_mismatches(scored, self.events), 10)


class AdapterTest(unittest.TestCase):
    def test_vectorized_adapter_matches_from_row(self):
        view = ds.switch_view(toy_events())
        rows = view.assign(ts=pd.to_datetime(view.ts, unit="s", utc=True)).to_dict("records")
        self.assertEqual(ds.to_events(view), [Event.from_row(r) for r in rows])

    def test_switch_view_hides_on_us_and_non_p2p(self):
        view = ds.switch_view(toy_events())
        self.assertEqual(set(view.route_scope), {"CROSS_BANK"})
        self.assertEqual(set(view.txn_type), {"P2P"})

    def test_rejects_fractional_satang(self):
        df = pd.DataFrame([row("x", D0, "a", "b", 10.005)])
        with self.assertRaises(ValueError):
            ds.to_events(df)


class ScoreTest(unittest.TestCase):
    def test_batch_scores_equal_replay(self):
        """The demo replays events directly; the training table must hold the same numbers."""
        view = ds.switch_view(toy_events())
        out = ds.score(view).set_index("event_id")
        ref = {e.event_id: f for e, f in replay(ds.to_events(view))
               if e.payer_type == "PERSON" and e.payee_type == "PERSON" and e.ts >= ds.BOUNDS[0]}
        self.assertEqual(set(out.index), set(ref))
        for i, f in ref.items():
            for k, v in f.items():
                got = out.at[i, k]
                self.assertTrue(math.isnan(got) if v is None else got == v, (i, k, v, got))

    def test_metadata_never_changes_features(self):
        rnd = random.Random(2)
        a = toy_events().assign(episode_id=lambda d: [f"ep{rnd.randrange(9)}" for _ in range(len(d))],
                                ring_id="R1", scenario="A", generator_version="v1")
        b = a.assign(episode_id=a.episode_id.sample(frac=1, random_state=3).to_numpy(), ring_id="R9",
                     scenario="D", generator_version="v2", is_synthetic=0, synthetic_fields="NONE")
        pd.testing.assert_frame_equal(ds.score(ds.switch_view(a)), ds.score(ds.switch_view(b)))
        self.assertFalse(set(ds.FEATURES) & METADATA)

    def test_duplicates_and_row_order_do_not_change_features(self):
        df = toy_events()
        noisy = pd.concat([df, df.sample(200, random_state=4)]).sample(frac=1, random_state=5)
        pd.testing.assert_frame_equal(ds.score(ds.switch_view(df)), ds.score(ds.switch_view(noisy)))

    def test_warm_up_is_history_only(self):
        out = ds.score(ds.switch_view(toy_events())).merge(toy_events()[["event_id", "ts"]], on="event_id")
        self.assertGreaterEqual(out.ts.min(), ds.BOUNDS[0])


def at(day):
    return D0 + int(day * DAY)


def crafted_tables():
    """One victim (t1), a ring (r1 receiver, s1 seeder) and one shop-refund hard negative (t2) on toy traffic."""
    extra = [
        row("scam1", at(100), "t1", "r1", 3000),     # train positive, reported in time
        row("seed1", at(101), "s1", "t1", 500),      # seed from the ring: a ring payer, not a T2 intent
        row("scam2", at(105), "t1", "r1", 9000),     # reported after the training cutoff
        row("scam3", at(275), "t1", "r1", 20000),    # lands in val though the ring is train: purged
        row("hn_out", at(150), "t2", "shop", 800),
        row("hn_in", at(151), "shop", "t2", 100),
        row("hn_next", at(160), "t2", "t4", 1500),
    ]
    events = pd.concat([toy_events(days=450, n_ev=3000), pd.DataFrame(extra)], ignore_index=True)
    lab = pd.DataFrame({"event_id": ["scam1", "seed1", "scam2", "scam3"], "label": "CONFIRMED_SCAM",
                        "subject_token": "t1", "episode_id": "ep1",
                        "event_role": ["STEP", "SEED_INFLOW", "STEP", "STEP"],
                        "label_effective_ts": [at(120), at(120), at(340), at(340)]})
    episodes = pd.DataFrame({"episode_id": ["ep1"], "ring_id": ["R1"], "split": ["train"], "family": ["A"],
                             "variant": [""], "is_holdout": [0], "victim_token": ["t1"], "loss_thb": [32000.0]})
    rings = pd.DataFrame({"ring_id": ["R1", "R1"], "token": ["r1", "s1"], "role": ["RECEIVER", "SEEDER"]})
    hn = pd.DataFrame({"event_id": ["hn_out", "hn_in", "hn_next"], "hn_id": "hn1", "group": "SHOP_PARTIAL_REFUND",
                       "subject_token": "t2", "step": ["OUT", "IN", "NEXT"], "split": "train"})
    return {"events": events, "labels": lab, "episodes": episodes, "ring_accounts": rings, "hn_events": hn}


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tables = crafted_tables()
        self.t = ds.build(self.tables).set_index("event_id")

    def test_labels_cutoff_purge_and_ring_payers(self):
        t = self.t
        self.assertTrue(t.at["scam1", "y_true"] and t.at["scam1", "y_train"] and t.at["scam1", "in_t2"])
        self.assertTrue(t.at["scam2", "y_true"] and not t.at["scam2", "y_train"])   # negative proxy in train
        self.assertTrue(t.at["scam3", "purged"] and not t.at["scam3", "in_t2"])
        self.assertTrue(t.at["seed1", "ring_payer"] and not t.at["seed1", "y_true"] and not t.at["seed1", "in_t2"])
        self.assertEqual(int(t.y_true.sum()), 3)

    def test_hard_negative_intents_are_the_subjects_outbound(self):
        t = self.t
        self.assertEqual(t.at["hn_out", "hn_group"], "SHOP_PARTIAL_REFUND")
        self.assertEqual(t.at["hn_next", "hn_group"], "SHOP_PARTIAL_REFUND")
        self.assertTrue(pd.isna(t.at["hn_in", "hn_group"]))

    def test_episode_events_keep_invisible_and_purged_rows(self):
        e = ds.episode_events(self.tables, self.t.reset_index()).set_index("event_id")
        self.assertEqual(sorted(e.index), ["scam1", "scam2", "scam3"])
        self.assertEqual(e.scored.to_dict(), {"scam1": True, "scam2": True, "scam3": False})

    def test_split_boundaries(self):
        days = [0, 89.99, 90, 269.99, 270, 329.99, 330, 449.99, 450]
        self.assertEqual(ds.split_of([at(d) for d in days]).tolist(),
                         ["warmup", "warmup", "train", "train", "val", "val", "test", "test", "after"])

    def test_build_is_deterministic(self):
        pd.testing.assert_frame_equal(ds.build(crafted_tables()), ds.build(crafted_tables()))


class ContractTest(unittest.TestCase):
    """docs/lab/G0_DATA_CONTRACT.md: generator output that breaks the schema must stop tp.dataset, not lose rows."""

    def tables(self):
        t = crafted_tables()
        t["episodes"] = t["episodes"].assign(mimicry_applied=0)
        return t

    def test_crafted_tables_meet_the_contract(self):
        ds.check_contract(self.tables())

    def test_violations_fail_loudly(self):
        cases = [
            ("episodes", lambda x: x.assign(family="SEED_PAYOUT_LADDER"), "episodes.family"),
            ("episodes", lambda x: x.assign(split="validation"), "episodes.split"),
            ("episodes", lambda x: x.assign(variant="SPLIT,LONG_GAP"), "episodes.variant"),
            ("episodes", lambda x: x.assign(variant="AGED_RECEIVER", is_holdout=1), "is_holdout"),  # holdout in train
            ("hn_events", lambda x: x.drop(columns="step"), "hn_events: missing"),
            ("labels", lambda x: x.assign(label_effective_ts=x.label_effective_ts.astype(float)), "label_effective_ts"),
            ("events", lambda x: x.assign(is_synthetic=0), "is_synthetic"),
        ]
        for name, change, expected in cases:
            with self.subTest(expected):
                t = self.tables()
                t[name] = change(t[name])
                with self.assertRaises(ValueError) as cm:
                    ds.check_contract(t)
                self.assertIn(expected, str(cm.exception))


class HistoryTest(unittest.TestCase):
    def test_insufficient_history(self):
        busy = [row(f"a{i}", at(10 + 5 * i), "a", "x", 100) for i in range(12)]   # 12 rows over 55 days
        quiet = [row(f"b{i}", at(60 + i), "b", "x", 100) for i in range(3)]
        view = ds.switch_view(pd.DataFrame(busy + quiet))
        got = ds.history_insufficient(view, pd.Series(["a", "b", "a"]), [at(70), at(70), at(12)])
        self.assertEqual(got.tolist(), [False, True, True])


if __name__ == "__main__":
    unittest.main()
