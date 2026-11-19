"""Phase 4: deterministic replay of 4 scenes (v3.3 §14.1, gate G6) with the frozen models. Everything is SYNTHETIC.

A: a normal user's real next transfer · B: §14.1 with money back from a different account (S) than the receivers ·
C: the same sequence with money back from the receivers themselves · D: a personal-shop partial refund taken from
the test set. Shows what the frozen arm 2 model outputs; no threshold is changed for the demo.
Runs only after tp.evaluate opened the test split, because scenes A and D replay test-period events.
Run: PYTHONPATH=src .venv/bin/python -m tp.demo data/processed/g0/m0
"""
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from tp.dataset import DAY0, ROOT, switch_view, to_events
from tp.features import DAY, Event, State
from tp.metrics import PRIMARY
from tp.train import ARMS, ARTIFACTS, MANIFEST, score

OUT = ROOT / "reports" / "demo"
RESULTS = ARTIFACTS / "test_results.json"
FEATS = list(ARMS["arm2"])
SCENE_START = DAY0 + 345 * DAY + 3 * 3600       # test period, 10:00 ICT
REASONS = {  # §6.3: contributions are summed per group, only positive groups whose facts hold are shown (max 3)
    "TP01_PAYOUT_THEN_ESCALATION": (("seed_like_inbound_count_90d", "hours_since_seed_like_inbound", "return_ratio",
                                     "new_cluster_return_ratio", "cycle_count", "account_context_cycle_count",
                                     "in_out_ratio_90d"),
                                    lambda f: (f["seed_like_inbound_count_90d"] or 0) >= 1,
                                    "ก่อนหน้านี้มีเงินกลับเข้าบัญชี และรายการนี้มียอดสูงขึ้น การได้เงินคืนเล็กน้อยยังไม่ยืนยันความน่าเชื่อถือของการลงทุน"),
    "TP02_ESCALATION_VS_BASELINE": (("amount_abs", "escalation_vs_pair", "escalation_vs_observed_outbound",
                                     "escalation_vs_established"),
                                    lambda f: any((f[k] or 0) > 1 for k in ("escalation_vs_pair",
                                                  "escalation_vs_observed_outbound", "escalation_vs_established")),
                                    "ยอดครั้งนี้สูงกว่ารายการที่ผ่านมาในช่วงข้อมูลที่ธนาคารตรวจสอบได้ โปรดตรวจสอบก่อนโอน"),
    "TP03_INTERVAL_COMPRESSION": (("interval_compression", "outbound_count_24h"),
                                  lambda f: (f["interval_compression"] or 0) > 1,
                                  "ช่วงนี้มีการโอนต่อเนื่องใกล้กัน หากมีผู้เร่งให้โอน ควรหยุดตรวจสอบก่อน"),
    "TP04_SPLIT_TRANSFERS": (("split_transfer_cum_24h",), lambda f: f["outbound_count_24h"] >= 1,
                             "ยอดหลายรายการในช่วงสั้นรวมกันสูง โปรดตรวจสอบยอดรวมและวัตถุประสงค์"),
    "TP05_MULTI_SOURCE_PAYOUT": (("new_payout_sources_14d",), lambda f: f["new_payout_sources_14d"] >= 2,
                                 "ช่วงนี้มีเงินก้อนเล็กเข้าจากหลายบัญชี หากเป็นผลตอบแทนที่ใช้ชวนให้โอนเพิ่ม โปรดตรวจสอบก่อน"),
    "TP06_NEW_PAYEE_ROTATION": (("new_cluster_payee_count_14d", "relationship_age_observed_days",
                                 "escalation_vs_new_cluster", "ladder_steps"),
                                lambda f: f["new_cluster_payee_count_14d"] >= 1 and (f["escalation_vs_new_cluster"] or 0) > 1,
                                "ช่วงนี้มีการโอนเข้าบัญชีที่ไม่เคยโอนด้วยหลายบัญชี และยอดสูงขึ้นเรื่อย ๆ หากถูกขอให้โอนเข้าบัญชีใหม่ทุกครั้ง โปรดหยุดตรวจสอบก่อน"),
}
GENERIC_TEXT = "ธนาคารพบรูปแบบธุรกรรมที่ควรตรวจสอบเพิ่มเติม โปรดยืนยันที่มาและวัตถุประสงค์กับช่องทางที่เชื่อถือได้"
STATE_KEYS = ("seed_like_inbound_count_90d", "new_cluster_payee_count_14d", "account_context_cycle_count",
              "outbound_count_24h")


def p2p(event_id, ts, payer, payee, baht):
    return Event(event_id, ts, payer, payee, round(baht * 100), "P2P", "PERSON", "PERSON")


def history(d, token, until):
    """The account's own switch-view events before `until`: all that arm 2 features of its intents depend on."""
    ev = pd.read_parquet(d / "events.parquet", filters=[[("payer_token", "==", token)], [("payee_token", "==", token)]])
    return [e for e in to_events(switch_view(ev)) if e.ts < until]


def run(events, intents):
    """Replay in time order; score each intent in `intents` before it enters the state (same logic as replay())."""
    state, seen = State(), {}
    for e in sorted(events, key=lambda e: e.ts):
        if e.event_id in intents:
            before = state.features(e.payer, e.payee, e.amount, e.ts)
            state.add(e)
            after = state.features(e.payer, "PROBE", 100, e.ts + 1)      # what the next intent would see
            seen[e.event_id] = (e, before, after)
        else:
            state.add(e)
    return seen


def judge(f, models, man):
    """Scores, level and reason codes of one intent from the frozen models and thresholds."""
    row = pd.DataFrame([{k: np.nan if v is None else v for k, v in f.items()}])
    th = man["thresholds"]
    s = {a: float(score(a, row, models.get(a), man["rule_k"])[0]) for a in ("arm0", "rule", "arm1", "arm2")}
    lvl = {a: "HIGH" if s[a] >= th[a]["5/10k"] else "ELEVATED" if s[a] >= th[a][PRIMARY] else "NONE" for a in s}
    contrib = models["arm2"].predict(row[FEATS], pred_contrib=True)[0][:-1]      # drop the bias term
    by = dict(zip(FEATS, contrib))
    groups = {code: sum(by[k] for k in keys) for code, (keys, _, _) in REASONS.items()}
    codes = [c for c, v in sorted(groups.items(), key=lambda kv: -kv[1]) if v > 0 and REASONS[c][1](f)][:3]
    return s, lvl, codes, groups


def evidence(chain, scene, e, f, s, lvl, codes, man, latency_ms):
    entry = {"scene": scene, "touchpoint": "T2", "intent_id": e.event_id, "subject_token": e.payer,
             "payee_token": e.payee, "amount_thb": e.amount / 100, "decision_ts": e.ts, "engine": "LGBM_ARM2",
             "model_sha256": man["lightgbm"]["model_sha256"]["arm2"],
             "policy": {"budget_elevated": PRIMARY, "budget_high": "5/10k", "thresholds": man["thresholds"]["arm2"]},
             "risk_score": round(s["arm2"], 6), "signal_level": lvl["arm2"], "reason_codes": codes,
             "copy_version": "v3.3-§6.3", "delay_seconds": 30 if lvl["arm2"] == "HIGH" else 0,
             "sent": "SIMULATED", "ack": "SIMULATED", "displayed_at": None, "user_action": "NOT_OBSERVED (synthetic)",
             "latency_ms": latency_ms, "fail_open": False, "is_synthetic": 1,
             "prev_hash": chain[-1]["hash"] if chain else "0" * 64}
    entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    chain.append(entry)
    return entry


def fmt(v):
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:,.3f}" if isinstance(v, float) else f"{v:,}"


def pick_user(d):
    """Scene A/B/C subject: the first ordinary account (not victim, ring or hard-negative subject) by token with
    at least 20 visible intents in the 90 days before the scenes."""
    rows = pd.read_parquet(d / "features.parquet", columns=["event_id", "ts", "payer_token", "in_t2"],
                           filters=[("ts", ">=", SCENE_START - 90 * DAY), ("ts", "<", SCENE_START)])
    busy = rows[rows.in_t2].payer_token.value_counts()
    excluded = set(pd.read_parquet(d / "episodes.parquet").victim_token)
    excluded |= set(pd.read_parquet(d / "ring_accounts.parquet").token)
    excluded |= set(pd.read_parquet(d / "hn_events.parquet").subject_token)
    return sorted(t for t, n in busy.items() if n >= 20 and t not in excluded)[0]


def check_parity(d, seen):
    """G6 needs a real replay: the demo's features for real events must equal the batch table."""
    ids = [i for i in seen if not i.startswith("DEMO")]
    if not ids:
        return
    batch = pd.read_parquet(d / "features.parquet", filters=[("event_id", "in", ids)]).set_index("event_id")
    for i in ids:
        for k in FEATS:
            v, b = seen[i][1][k], batch.at[i, k]
            if not (math.isnan(b) if v is None else v == b):
                raise AssertionError(f"demo/batch feature mismatch {i} {k}: {v} vs {b}")


def scene_lines(title, story, e_list, seen, verdicts, chain_entry):
    L = [f"## {title} · **SYNTHETIC**", "", f"> {story}", "", "| วันที่ในฉาก | รายการ | ยอด (บาท) | สิ่งที่ระบบเห็น ณ ตอนนั้น |",
         "|---|---|---|---|"]
    start = e_list[0].ts
    for e in e_list:
        note = ""
        if e.event_id in seen:
            _, f, _ = seen[e.event_id]
            s, lvl, codes, _ = verdicts[e.event_id]
            note = (f"เงินล่อที่เห็น {fmt(f['seed_like_inbound_count_90d'])} · คู่ใหม่ 14 วัน "
                    f"{fmt(f['new_cluster_payee_count_14d'])} · arm 2 = {s['arm2']:.4f} → **{lvl['arm2']}**")
        L.append(f"| {(e.ts - start) / DAY + 1:.1f} | {e.payer[-8:]} → {e.payee[-8:]} | {e.amount / 100:,.0f} | {note} |")
    last = [e for e in e_list if e.event_id in seen][-1]
    _, f, after = seen[last.event_id]
    s, lvl, codes, groups = verdicts[last.event_id]
    L += ["", f"**ผลของโมเดลจริง ณ รายการสุดท้าย:** arm 2 = {s['arm2']:.4f} → **{lvl['arm2']}** · arm 1 → {lvl['arm1']} · "
          f"rule T2 → {lvl['rule']} · arm 0 → {lvl['arm0']} (threshold จาก validation ตาม manifest ไม่ได้ปรับ)", ""]
    if lvl["arm2"] == "NONE":
        L.append("ไม่แสดงคำเตือนต่อลูกค้า")
    else:
        L += [f"- `{c}`: {REASONS[c][2]}" for c in codes] or [f"- ข้อความทั่วไป: {GENERIC_TEXT}"]
    L += ["", "Contribution รายกลุ่ม (pred_contrib, ไม่รวม bias): "
          + " · ".join(f"{c.split('_')[0]} {v:+.3f}" for c, v in sorted(groups.items(), key=lambda kv: -kv[1])), "",
          "<details><summary>Feature ที่เห็น ณ decision time และ state ก่อน/หลัง</summary>", "",
          "| feature | ค่า |", "|---|---|"] + [f"| `{k}` | {fmt(f[k])} |" for k in FEATS]
    L += ["", "| state | ก่อน | หลังรายการนี้ |", "|---|---|---|"] + [f"| `{k}` | {fmt(f[k])} | {fmt(after[k])} |" for k in STATE_KEYS]
    L += ["", "</details>", "", "Evidence log entry:", "", "```json", json.dumps(chain_entry, ensure_ascii=False, indent=1), "```", ""]
    return L


def main(path):
    if not RESULTS.exists():
        sys.exit("Run tp.evaluate first: scenes A and D replay test-period events.")
    d = Path(path).resolve()
    man = json.loads(MANIFEST.read_text())
    models = {a: lgb.Booster(model_file=str(ARTIFACTS / "models" / f"{a}.txt")) for a in ("arm1", "arm2")}
    user = pick_user(d)
    t = SCENE_START
    script = {  # §14.1 numbers; B and C differ only in who sends the money back
        "B": [("V", "DEMO_B1", 1000, 0), ("DEMO_S", "V", 200, 2), ("V", "DEMO_B2", 5000, 4), ("DEMO_S", "V", 800, 6),
              ("V", "DEMO_B3", 50000, 7)],
        "C": [("V", "DEMO_B1", 1000, 0), ("DEMO_B1", "V", 200, 2), ("V", "DEMO_B2", 5000, 4), ("DEMO_B2", "V", 800, 6),
              ("V", "DEMO_B3", 50000, 7)]}
    hist = history(d, user, t + 60 * DAY)
    real_next = next(e for e in hist if e.payer == user and e.ts >= t and e.payee_type == "PERSON")
    scenes = {"A": (hist, [real_next], [real_next], "ฉาก A — ผู้ใช้ปกติ",
                    "บัญชีปกติจาก simulator โอนรายการจริงรายการถัดไปของตัวเอง (ไม่ได้แต่งรายการ)")}
    for name, rows in script.items():
        ev = [p2p(f"DEMO{name}{i}", t + int(day * DAY) + 600 * i, user if a == "V" else a, user if b == "V" else b, baht)
              for i, (a, b, baht, day) in enumerate(rows)]
        who = "บัญชี S ที่ไม่ใช่ผู้รับ" if name == "B" else "บัญชีที่เหยื่อเพิ่งโอนไป (B1, B2)"
        scenes[name] = ([e for e in hist if e.ts < ev[-1].ts] + ev, [e for e in ev if e.payer == user], ev,
                        f"ฉาก {name} — ลำดับ §14.1 เงินคืนมาจาก{who}",
                        "V→B1 1,000 · เงินคืน 200 · V→B2 5,000 · เงินคืน 800 · V เตรียมโอน B3 50,000 · "
                        "ทุกบัญชีในฉากเป็น token ใหม่ ต่างธนาคารกับ V · ประวัติของ V เป็นของจริงใน simulator")
    hn = pd.read_parquet(d / "hn_events.parquet", filters=[("group", "==", "SHOP_PARTIAL_REFUND"), ("split", "==", "test")])
    scored = pd.read_parquet(d / "features.parquet", columns=["event_id", "in_t2"],
                             filters=[("event_id", "in", hn.event_id.tolist())])
    first = sorted(hn[(hn.step == "NEXT") & hn.event_id.isin(set(scored.event_id[scored.in_t2]))].hn_id)[0]
    seq = hn[hn.hn_id == first]
    subject = seq.subject_token.iloc[0]
    seq_ev = sorted(to_events(switch_view(pd.read_parquet(d / "events.parquet",
                                                          filters=[("event_id", "in", seq.event_id.tolist())]))),
                    key=lambda e: e.ts)
    mine = [e for e in seq_ev if e.payer == subject and e.payee_type == "PERSON"]
    scenes["D"] = (history(d, subject, seq_ev[-1].ts + 1), mine, seq_ev,
                   "ฉาก D — hard negative: ร้านค้าบัญชีบุคคลคืนเงินบางส่วน",
                   f"ลำดับ hard negative จริงชุดแรกใน test (`{first}`) · ผลอาจเตือนหรือไม่เตือนก็ได้ และแสดงตามจริง")

    chain, lines = [], ["# G-0 Demo replay · SYNTHETIC", "",
                        "> ข้อมูลจำลองทั้งหมด (is_synthetic=1) · replay จริงด้วยโมเดลและ threshold ที่ตรึงใน "
                        f"manifest `{man['code_sha256']['src/tp/train.py'][:8]}` · learnability ไม่ใช่ production accuracy · "
                        "ฉาก T3 / Fraud Ops อยู่นอก scope ของ lab · demo code แก้ parity guard หลังเปิด test "
                        "ตาม deviation 6", ""]
    for name, (events, intents, shown, title, story) in scenes.items():
        started = time.perf_counter()
        seen = run(events, {e.event_id for e in intents})
        check_parity(d, seen)
        verdicts = {i: judge(f, models, man) for i, (_, f, _) in seen.items()}
        latency = round((time.perf_counter() - started) * 1000 / max(len(seen), 1), 1)
        last = intents[-1]
        s, lvl, codes, _ = verdicts[last.event_id]
        entry = evidence(chain, name, last, seen[last.event_id][1], s, lvl, codes, man, latency)
        lines += scene_lines(title, story, shown, seen, verdicts, entry)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "G0_DEMO.md").write_text("\n".join(lines))
    (OUT / "evidence_log.jsonl").write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chain) + "\n")
    print(f"wrote {(OUT / 'G0_DEMO.md').relative_to(ROOT)} · levels: "
          + ", ".join(f"{c['scene']}={c['signal_level']}" for c in chain))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/processed/g0/m0")
