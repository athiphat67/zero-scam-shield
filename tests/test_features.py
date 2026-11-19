import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tp.features import (DAY, GENERIC, NETWORK, TRUST, TRUST_ESCALATION, TRUST_SEED, Event, State,  # noqa: E402
                         replay)

T0 = int(datetime(2026, 6, 1, 9, tzinfo=timezone.utc).timestamp())


def at(day):
    return T0 + day * DAY


def p2p(event_id, day, payer, payee, baht, payer_type="PERSON", status="SETTLED"):
    return Event(event_id, at(day), payer, payee, baht * 100, "P2P", payer_type, "PERSON", status)


def demo():
    """v3.3 §14 with rotation (D42) on a 90-day warm-up of rent (L), mom (M) and a friend (F)."""
    rows = [
        (-89, "V", "L", 1500), (-59, "V", "L", 1500), (-29, "V", "L", 1500),
        (-80, "V", "M", 800), (-50, "V", "M", 800), (-20, "V", "M", 800),
        (-85, "V", "F", 300), (-40, "V", "F", 300), (-10, "V", "F", 300),
        (1, "V", "B1", 1000),
        (2, "F", "V", 150),   # money back from a friend known > 30 days: must not be seed-like
        (3, "S", "V", 200),
        (5, "V", "B2", 5000),
        (6, "X1", "B3", 3000),  # other payers into B3 (network context)
        (7, "S", "V", 800),
        (7, "X2", "B3", 4000),
    ]
    return [p2p(f"e{i}", d, a, b, baht) for i, (d, a, b, baht) in enumerate(rows)]


def state_of(events):
    state = State()
    for e in sorted(events, key=lambda e: e.ts):
        state.add(e)
    return state


def intent(state):
    return state.features("V", "B3", 50_000 * 100, at(8))


class DemoTest(unittest.TestCase):
    def test_rotating_payees_still_show_the_ladder(self):
        f = intent(state_of(demo()))
        self.assertIsNone(f["escalation_vs_pair"])
        self.assertIsNone(f["relationship_age_observed_days"])
        self.assertEqual(f["escalation_vs_new_cluster"], 10.0)
        self.assertEqual(f["new_cluster_payee_count_14d"], 2)
        self.assertEqual(f["ladder_steps"], 2)
        self.assertEqual(f["seed_like_inbound_count_90d"], 2)
        self.assertEqual(f["new_payout_sources_14d"], 1)
        self.assertEqual(f["hours_since_seed_like_inbound"], 24.0)
        self.assertAlmostEqual(f["new_cluster_return_ratio"], 1000 / 6000)
        self.assertEqual(f["account_context_cycle_count"], 1)
        self.assertEqual(f["cycle_count"], 0)
        self.assertEqual(f["receiver_fan_in_7d"], 2)

    def test_established_baseline_is_not_inflated_by_the_scam(self):
        f = intent(state_of(demo()))
        # p95 of [300, 300, 800, 1500] vs p95 of all outbound, which includes B1/B2
        self.assertAlmostEqual(f["escalation_vs_established"], 50_000 / 1395)
        self.assertAlmostEqual(f["escalation_vs_observed_outbound"], 50_000 / 3600)

    def test_uses_only_events_before_t(self):
        state = state_of(demo() + [p2p("same_ts", 8, "S", "V", 300), p2p("later", 9, "S", "V", 300)])
        self.assertEqual(intent(state)["seed_like_inbound_count_90d"], 2)

    def test_ignores_duplicates_failed_and_unknown_payer_type(self):
        events = demo()
        extra = [
            events[12],                                             # duplicate event_id of V->B2
            p2p("failed", 6, "V", "B4", 9000, status="FAILED"),
            p2p("unknown", 6, "Z", "V", 100, payer_type="UNKNOWN"),  # T1 never guesses PERSON
        ]
        f = intent(state_of(events + extra))
        self.assertEqual(f["new_cluster_payee_count_14d"], 2)
        self.assertEqual(f["escalation_vs_new_cluster"], 10.0)
        self.assertEqual(f["seed_like_inbound_count_90d"], 2)

    def test_replay_scores_before_adding(self):
        events = demo() + [p2p("big", 8, "V", "B3", 50_000)]
        scored = {e.event_id: f for e, f in replay(events)}
        self.assertEqual(len(scored), len(events))
        self.assertEqual(scored["e12"]["escalation_vs_new_cluster"], 5.0)  # V->B2 5,000 vs B1 1,000
        self.assertEqual(scored["big"]["escalation_vs_new_cluster"], 10.0)

    def test_feature_groups_match_output(self):
        f = intent(state_of(demo()))
        self.assertEqual(set(f), set(GENERIC) | set(TRUST) | set(NETWORK))
        self.assertEqual(len(f), len(GENERIC) + len(TRUST) + len(NETWORK))

    def test_escalation_group_never_reads_money_back(self):
        """Arm 2 − arm 2e (deviation 2) isolates money back only if TRUST_ESCALATION stays put when it is removed."""
        with_seed = intent(state_of(demo()))
        no_inbound = intent(state_of([e for e in demo() if e.payee != "V"]))
        self.assertEqual({k: with_seed[k] for k in TRUST_ESCALATION}, {k: no_inbound[k] for k in TRUST_ESCALATION})
        self.assertNotEqual({k: with_seed[k] for k in TRUST_SEED}, {k: no_inbound[k] for k in TRUST_SEED})
        self.assertEqual(TRUST, TRUST_SEED + TRUST_ESCALATION)


class FromRowTest(unittest.TestCase):
    ROW = {"event_id": "r1", "ts": "2026-09-28T03:00:00Z", "payer_token": "tok_v",
           "payee_token": "tok_b3", "amount_thb": "50000.00"}

    def test_parses_canonical_row(self):
        e = Event.from_row(self.ROW)
        self.assertEqual(e.amount, 5_000_000)
        self.assertEqual(e.ts, int(datetime(2026, 9, 28, 3, tzinfo=timezone.utc).timestamp()))
        self.assertEqual((e.txn_type, e.payer_type, e.status), ("UNKNOWN", "UNKNOWN", "SETTLED"))

    def test_rejects_bad_amounts(self):
        for bad in ("10.005", "0", "-5"):
            with self.assertRaises(ValueError):
                Event.from_row({**self.ROW, "amount_thb": bad})


if __name__ == "__main__":
    unittest.main()
