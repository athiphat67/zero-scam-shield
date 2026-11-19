"""Build reports/G0_LAB_REPORT.md from artifacts/*.json only, so every number comes from a run.

Also re-runs the unit tests and quotes their summary. Run: .venv/bin/python scripts/make_report.py
--rehearsal builds reports/G0_REHEARSAL_VAL.md from the validation dry run instead (deviation 2).
"""
import json
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
REHEARSAL = "--rehearsal" in sys.argv[1:]
OUT = ROOT / "reports" / ("G0_REHEARSAL_VAL.md" if REHEARSAL else "G0_LAB_REPORT.md")
RESULTS = ART / ("rehearsal_val.json" if REHEARSAL else "test_results.json")
PRIMARY = "20/10k"
ARMS = {"arm0": "Arm 0 control (ผู้รับใหม่ + ยอด ≥ X)", "rule": "Rule T2 (§6.2)", "arm1": "Arm 1 generic (LightGBM)",
        "arm2e": "Arm 2e generic + ยอดไต่ (LightGBM)", "arm2": "Arm 2 + trust provenance (LightGBM)",
        "arm3": "Arm 3 + B (LightGBM, simulator)"}
HN_TH = {"SHOP_PARTIAL_REFUND": "ร้านค้าบุคคลคืนเงินบางส่วน", "FRIEND_LOAN_REPAID": "เพื่อนคืนเงินยืม",
         "BILL_SPLIT": "หารค่าเที่ยว/กิน", "FAMILY": "ครอบครัว", "DEPOSIT_RETURNED": "มัดจำแล้วคืน",
         "LEGIT_ESCALATION": "โอนสุจริตที่ยอดไต่ขึ้น"}


def pct(x):
    return "–" if x is None else f"{100 * x:.1f}%"


def pci(v):
    return f"{pct(v[0])} ({pct(v[1])}–{pct(v[2])})"


def num(x, d=1):
    return "∞" if x is None or x == float("inf") else f"{x:,.{d}f}"


def rci(v):
    return f"{num(v[0])} ({num(v[1])}–{num(v[2])})"


def dci(p):
    return f"{100 * p['diff']:+.1f} pp (95% CI {100 * p['ci'][0]:+.1f} ถึง {100 * p['ci'][1]:+.1f})"


def tests_summary():
    run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT,
                         capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError("Unit tests failed:\n" + run.stderr[-2000:])
    ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", run.stderr)
    status = run.stderr.strip().splitlines()[-1] if run.stderr.strip() else "?"
    return f"{ran.group(1) if ran else '?'} tests · {status}"


def label(man, budget, split):
    return (f"_ที่มา: simulator g0 (synthetic ทุกแถว) · มุมมอง: switch = P2P ข้ามธนาคารเท่านั้น · "
            f"arm/version: manifest `{man['code_sha256']['src/tp/train.py'][:8]}` · budget: {budget} "
            f"ถ่วงที่ p = 1:5,000 · split: {split} · learnability ไม่ใช่ production accuracy_")


def main():
    manifest_path = ART / "protocol_manifest.json"
    man = json.loads(manifest_path.read_text())
    res = json.loads(RESULTS.read_text())
    split = res["meta"]["labels"]["split"]
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != res["meta"]["manifest_sha256"]:
        raise RuntimeError("Test results do not match the frozen manifest")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != man["code_sha256"]["scripts/make_report.py"]:
        raise RuntimeError("Report generator differs from the frozen manifest")
    profile_path = ART / "dataset_profile_m0.json"
    if hashlib.sha256(profile_path.read_bytes()).hexdigest() != man["profile_sha256"]:
        raise RuntimeError("Dataset profile differs from the frozen manifest")
    test_result = tests_summary()
    prof = json.loads(profile_path.read_text())
    deviations = (ROOT / "docs/lab/PROTOCOL_DEVIATIONS.md").read_text().split("| # |", 1)[1]
    ep, it, hn = res["episodes"][PRIMARY], res["intents"], res["hard_negatives"]
    A = ep["A"]
    pairs = A["pairs"]
    L = ["> การทดลอง G-0 นี้วัด learnability และความถูกต้องของ pipeline บนข้อมูลจำลอง "
         "ไม่ได้พิสูจน์ production fraud accuracy", ""]
    if REHEARSAL:
        L += ["> **REHEARSAL บน validation (วัน 270–329) — ไม่ใช่ผล test** · ใช้ตรวจว่าโค้ดประเมินและรายงานทำงานครบ "
              "ก่อนเปิด test (deviation 2) · ตัวเลขชุดนี้ถูกใช้เลือก threshold มาแล้ว จึงมองโลกในแง่ดีเกินจริง "
              "และห้ามนำไปอ้างเป็นผล", ""]
    L += ["# G-0 Lab Report — Trust Provenance", "",
          f"ผลโมเดลสร้างจาก `artifacts/*.json` ด้วย `scripts/make_report.py` · {split} · รันเมื่อ {res['meta']['opened_at']} · "
          f"manifest {res['meta']['manifest_sha256'][:12]} · unit tests: {test_result}", ""]

    # 1 summary
    g3_fail = [HN_TH.get(g, g) for g, v in hn[PRIMARY].items() if not v["G3_arm2_le_rule"]]
    g3_few = [HN_TH.get(g, g) for g, v in hn[PRIMARY].items() if v["too_few_alerts"]]
    D = ep["D_placebo"]["pairs"]
    mim = res.get("mimicry", {}).get("m0.5")
    ceil = man["ceiling"]
    L += ["## 1. สรุป", "", label(man, PRIMARY, split), "",
          f"Population ของ H1: family A ที่ไม่ใช่ holdout · {A['episodes']} episodes จาก {A['rings']} rings "
          f"(หน่วย bootstrap = ring)", "",
          "| คำถาม | ผล | ตัวเลขหลัก |", "|---|---|---|",
          f"| **H1** TRUST ช่วยเตือนก่อนก้อนใหญ่สุด | **{pairs['H1 arm2-arm1 recall']['verdict']}** | recall before largest "
          f"arm 1 {pci(A['arms']['arm1']['recall'])} → arm 2 {pci(A['arms']['arm2']['recall'])} · Δ "
          f"{dci(pairs['H1 arm2-arm1 recall'])} |",
          f"| H1 ตัวรอง: exposure (ต่ำ = เตือนเร็วกว่า) | {pairs['H1 arm2-arm1 exposure']['verdict']} | arm 1 "
          f"{pci(A['arms']['arm1']['exposure'])} → arm 2 {pci(A['arms']['arm2']['exposure'])} |",
          f"| **H1s** เงินล่อ/เงินคืนเพิ่มค่าเหนือยอดไต่ (arm 2 − arm 2e) | **{pairs['H1s arm2-arm2e recall']['verdict']}** | "
          f"arm 2e {pci(A['arms']['arm2e']['recall'])} → arm 2 {pci(A['arms']['arm2']['recall'])} · Δ "
          f"{dci(pairs['H1s arm2-arm2e recall'])} |",
          f"| ยอดไต่เพิ่มค่าเหนือ generic (arm 2e − arm 1) | {pairs['arm2e-arm1 recall']['verdict']} | Δ "
          f"{dci(pairs['arm2e-arm1 recall'])} |",
          f"| H2 rule ชนะ arm 0 | {pairs['H2 rule-arm0 recall']['verdict']} | Δ {dci(pairs['H2 rule-arm0 recall'])} |",
          f"| H2 / G1 ML (arm 2) ชนะ rule | {pairs['G1 arm2-rule recall']['verdict']} | Δ "
          f"{dci(pairs['G1 arm2-rule recall'])} |",
          f"| H3 / G3 hard negatives: arm 2 ≤ rule ทุกกลุ่ม (point estimate) | {'ผ่าน' if not g3_fail else 'ไม่ผ่าน'} | "
          f"{'—' if not g3_fail else 'กลุ่มที่ arm 2 เตือนผิดมากกว่า rule: ' + ', '.join(g3_fail)}"
          f"{'' if not g3_few else ' · ⚠️ alert น้อยเกินเทียบ (< 10): ' + ', '.join(g3_few)} |",
          f"| H4 / G7 mimicry 0.5 ลดลง ≤ 30% | "
          f"{'ยังไม่ประเมิน (mimicry เฉพาะ test)' if REHEARSAL else 'ไม่ได้ทำ' if not mim else 'ผ่าน' if mim['G7_arm2_pass'] else 'ไม่ผ่าน'} | "
          f"{'—' if REHEARSAL or not mim else 'arm 2 recall เหลือ ' + pct(mim['recall_ratio_vs_m0']['arm2']) + ' ของชุดปกติ'} |",
          f"| H5 B เพิ่มค่าเหนือ arm 2 (simulator) | {pairs['H5 arm3-arm2 recall']['verdict']} | Δ "
          f"{dci(pairs['H5 arm3-arm2 recall'])} |",
          f"| Placebo: เงินล่อไม่ควรช่วยบน scam ไม่มีเงินล่อ (family D, arm 2 − arm 2e) | "
          f"{'⚠️ ต้องตรวจ artifact' if D['H1s arm2-arm2e recall']['verdict'] == 'ผ่าน' else 'ไม่พบสัญญาณ artifact'} | "
          f"Δ {dci(D['H1s arm2-arm2e recall'])} · ประกอบ: arm 2 − arm 1 บน D {dci(D['H1 arm2-arm1 recall'])} "
          f"(คาดว่า > 0 จาก feature ยอดไต่ ไม่ใช่ artifact) |", ""]
    L += [f"**อ่านผล H1:** คำว่า \"เงินล่อ/เงินคืนช่วยเตือน\" ใช้ได้เมื่อ H1s ผ่านเท่านั้น · ถ้า H1 ผ่านแต่ H1s ไม่ผ่าน "
          "ประโยชน์มาจาก baseline ยอดไต่ (แนวเดียวกับ fraud engine ทั่วไป) · verdict \"สรุปไม่ได้ (งบจริงไม่เท่ากัน)\" = "
          "arm ที่ชนะใช้ FPR จริงเกินอีก arm มากกว่า 0.2 × งบ", "",
          f"**Ceiling (ตรึงก่อน test):** arm 1 recall before largest บน validation ที่ {PRIMARY} = "
          f"{pct(ceil['arm1_val_recall'])} → "
          + (f"**ชนเพดาน (≥ {pct(ceil['at_or_above'])})** H1 ที่งบนี้แยกความต่างได้น้อย · งบ 5/10k และ 1/10k "
             "ยังเป็นผลรองตาม protocol ห้ามยกขึ้นเป็นผลหลักหลังเห็นผล" if ceil["flag"] else
             f"ไม่ชนเพดาน (< {pct(ceil['at_or_above'])})"), "",
          f"**ขอบเขตการจูน:** validation positives ที่รู้ label ทัน cutoff วันที่ 330 = "
          f"{man['rows']['val_pos_known_at_cutoff']:,}/{man['rows']['val_pos']:,}; "
          "การเลือกโมเดลและ threshold ใน G-0 ใช้ ground truth ที่ mature ภายหลัง จึงเป็นการจูนย้อนหลัง", ""]
    g2, g2b = it["5/10k"]["arm2"], it["20/10k"]["arm2"]
    need = {b: man["budgets"][b] / man["p_main"] / (r + 1) for b, r in (("5/10k", 5), ("20/10k", 20))}
    top = list(man["g4_audit_val"]["single_feature_ap"].items())[:3]
    L += [f"G2 (arm 2, HIGH 5/10k): FP:TP ที่ p = 1:5,000 = {rci(g2['fp_per_tp']['1:5,000'])} → "
          f"{'ผ่าน' if g2['fp_per_tp']['1:5,000'][0] <= 5 else 'ไม่ผ่าน'} (เกณฑ์ ≤ 5) · G2b (20/10k): "
          f"{rci(g2b['fp_per_tp']['1:5,000'])} → {'ผ่าน' if g2b['fp_per_tp']['1:5,000'][0] <= 20 else 'ไม่ผ่าน'} "
          f"(เกณฑ์ ≤ 20) · point estimate", "",
          f"**G2/G2b ไม่ใช่หลักฐานภาระเตือนผิด:** threshold ถูกเลือกให้ FPR ใช้งบพอดี FP:TP จึงเท่ากับ ≈ B/(p·TPR) − 1 "
          f"→ G2 ผ่านเมื่อ TPR ระดับ intent ≥ {need['5/10k']:.2f} (ได้ {pct(g2['tpr'])}) · G2b ผ่านเมื่อ TPR ≥ "
          f"{need['20/10k']:.2f} (ได้ {pct(g2b['tpr'])}) · negative ทั้งหมดเป็น synthetic และ p เป็นสมมติฐาน "
          "ภาระเตือนผิดจริงต้องวัดบนธุรกรรมสุจริตจริง · ที่งบ 1/10k สูตรงบจำกัด TPR ระดับ intent ไว้ ≤ 50% "
          "(ไม่ใช่โมเดลอ่อน)", "",
          f"G4: PR-AUC ≥ 0.99 บน split นี้: {', '.join(res['counts']['pr_auc_audit_trigger']) or 'ไม่มี'} · audit ที่ตรึงไว้ "
          "(validation, ก่อนเปิด test): PR-AUC " + " · ".join(f"{a} {v:.3f}" for a, v in man["g4_audit_val"]["pr_auc"].items())
          + " · AP ของ feature เดี่ยวสูงสุด: " + " · ".join(f"`{f}` {v:.3f}" for f, v in top)
          + (" · ⚠️ feature เดียวแยก class ได้เกือบหมด = simulator ง่ายเกินจริง" if top and top[0][1] >= 0.95 else ""), ""]

    # 2 pipeline
    ex = prof["excluded"]
    L += ["## 2. ความถูกต้องของ pipeline และ leakage", "",
          f"- Unit tests: {test_result} · ครอบคลุม point-in-time (และ test ที่ต้อง fail เมื่อฝัง leak แบบ `<=`), "
          "score ก่อน update, metadata ไม่เข้า feature, dedupe, ลำดับแถว, parity batch/replay, determinism ของ "
          "generator/split, ring ไม่ข้าม split, test ไม่ถูกอ่านตอน train",
          f"- ตัดออกจากประชากร T2: รายการที่ payer เป็นบัญชี ring {ex['ring_payer_intents']:,} · purge {ex['purged_scam_intents']:,} · "
          f"positive ใน train ที่ยังไม่รู้ ณ cutoff (ใช้เป็น negative proxy) {ex['train_positive_intents_unknown_at_cutoff']:,}",
          f"- Threshold, k ของ rule ({man['rule_k']}) และ early stopping มาจาก validation เท่านั้น · manifest ตรึงก่อนเปิด test",
          f"- Validation positive ที่รู้ label ทัน cutoff วันที่ 330: {man['rows']['val_pos_known_at_cutoff']:,}/"
          f"{man['rows']['val_pos']:,} · การจูนใช้ ground truth หลัง label mature จึงเป็น retrospective experiment "
          "และยังไม่พิสูจน์ว่าจูนได้ด้วย label ที่มีจริง ณ วัน 330",
          "- Cold start: state เริ่มว่างที่วัน 0 ทุกคู่จึง \"ใหม่\" ช่วงแรก · ค่าเฉลี่ย `seed_like_inbound_count_90d` ของรายการสุจริต"
          "ตามช่วงวัน: " + " · ".join(f"{k} {v}" for k, v in prof["negative_seed_like_mean_by_day"].items())
          + f" · จึง fit เฉพาะแถว train วัน {man['fit_start_day']}–269 (deviation 3) วันก่อนหน้าเป็น history อย่างเดียว: "
          f"ไม่ fit {man['rows']['train_cold_start_excluded']:,} แถว (positive "
          f"{man['rows']['train_pos_cold_start_excluded']:,})",
          f"- รายการที่ payer เป็นบัญชี ring ({res['ring_payer_alerts']['intents']:,} intents ใน split นี้) ถูกตัดจากประชากร T2 "
          f"แต่ของจริงถูกให้คะแนนและใช้งบเตือน · alerts ที่ {PRIMARY}: "
          + " · ".join(f"{a} {n:,}" for a, n in res["ring_payer_alerts"][PRIMARY].items()),
          ""]
    L += ["| split | intents | accounts | positive intents | episodes | rings | ไม่มี intent ที่ switch เห็น |",
          "|---|---|---|---|---|---|---|"]
    for s, v in prof["splits"].items():
        L.append(f"| {s} | {v['intents']:,} | {v['accounts']:,} | {v['positive_intents']:,} | "
                 f"{', '.join(f'{k} {n}' for k, n in v['episodes'].items())} | {v['rings']} | "
                 f"{v['episodes_without_visible_intent']} |")
    L.append("")

    # 3 arms
    L += ["## 3. เทียบ arm ที่ budget เดียวกัน", ""]
    for b in ("20/10k", "5/10k", "1/10k"):
        e, i = res["episodes"][b]["A"], it[b]
        L += [f"### Budget {b}", "", label(man, b, split), "",
              f"Episode: family A ไม่รวม holdout {e['episodes']} episodes / {e['rings']} rings · intent: positive "
              f"{i['positives']:,} ({i['rings']} rings), negative {i['negatives']:,} ({i['payers']:,} บัญชี) · "
              f"holdout positive ที่ไม่รวมในตาราง {i['holdout_positive_intents_excluded']:,} intents", "",
              "| Arm | recall before largest | missed | exposure | alerts วิเคราะห์ / ทั้ง split | TP | FP | FPR จริง | FP:TP p=1:5,000 | FP:TP p=1:50,000 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for a, name in ARMS.items():
            x, r = e["arms"][a], i[a]
            L.append(f"| {name} | {pci(x['recall'])} | {pci(x['missed'])} | {pci(x['exposure'])} | "
                     f"{r['alerts']:,} / {r['all_test_alerts']:,} | {r['tp']:,} | {r['fp']:,} | "
                     f"{100 * r['fpr']:.3f}% | {rci(r['fp_per_tp']['1:5,000'])} | {rci(r['fp_per_tp']['1:50,000'])} |")
        L += ["", "FP:TP ในตารางคำนวณจาก TPR ที่งบนั้น (FPR ถูกตั้งให้ใช้งบพอดี) ไม่ใช่ภาระเตือนผิดที่วัดบนธุรกรรมจริง", ""]
    L += [f"PR-AUC ระดับ intent (ตัวรอง, ถูกขยายด้วยความหนาแน่นของ scam ใน simulator): "
          + " · ".join(f"{a} {v:.3f}" for a, v in res["pr_auc"].items()), "",
          "Episode ที่เตือนก่อนก้อนใหญ่สุดที่ weighted FP:TP 5:1 (§8.4, threshold จาก validation): "
          + " · ".join(f"{a} {v['warned_before_largest']} (เพิ่มจาก arm 0: {v['extra_vs_arm0']})"
                       for a, v in res["fp_tp5"].items()), "",
          f"Diagnostic (ไม่ใช้ตัดสิน): recall เมื่อ threshold ถูกตั้งใหม่บน split นี้ให้ได้ {PRIMARY} พอดี: "
          + " · ".join(f"{a} {pct(v)}" for a, v in res["diagnostic_matched_on_test"].items() if a != "note"), ""]

    # 4 hard negatives
    L += ["## 4. Hard negatives รายกลุ่ม", "", label(man, PRIMARY, split), "",
          "| กลุ่ม | intents / subjects | " + " | ".join(ARMS) + " | alerts arm 2 / rule | arm 2 − rule | G3 |",
          "|---|---|" + "---|" * len(ARMS) + "---|---|---|"]
    for g, v in hn[PRIMARY].items():
        L.append(f"| {HN_TH.get(g, g)} | {v['intents']:,} / {v['subjects']:,} | "
                 + " | ".join(pci(v[a]) for a in ARMS) + f" | {v['alerts']['arm2']} / {v['alerts']['rule']} | "
                 f"{100 * v['arm2-rule']['diff']:+.2f} pp | {'ผ่าน' if v['G3_arm2_le_rule'] else 'ไม่ผ่าน'}"
                 f"{' ⚠️ alert น้อยเกินเทียบ' if v['too_few_alerts'] else ''} |")
    L += ["", "หน่วย bootstrap = subject ของ hard negative · อัตรา = คำเตือน / intent ขาออกของ subject ในลำดับนั้น · "
          "กลุ่มที่ alert ของ arm 2 + rule < 10 ผลต่างเป็น noise (ตรึงไว้ใน deviation 2)", ""]

    # 5 robustness
    shown = ("arm0", "rule", "arm1", "arm2e", "arm2")
    L += ["## 5. ความทนทาน", "", label(man, PRIMARY, split), "",
          "| ชุด | episodes / rings | " + " | ".join(shown) + " | arm 2 − arm 1 | arm 2 − arm 2e |",
          "|---|---|" + "---|" * len(shown) + "---|---|"]
    for name, e in ep.items():
        if name == "A":
            continue
        L.append(f"| {name} | {e['episodes']} / {e['rings']} | "
                 + " | ".join(pct(e['arms'][a]['recall'][0]) for a in shown)
                 + f" | {dci(e['pairs']['H1 arm2-arm1 recall'])} | {dci(e['pairs']['H1s arm2-arm2e recall'])} |")
    for m, v in (() if REHEARSAL else res.get("mimicry", {}).items()):
        a = v["A"]
        L.append(f"| mimicry {m} ({v['episodes_mimicked']} episodes ถูกปรับ) | {a['episodes']} / {a['rings']} | "
                 + " | ".join(pct(a['arms'][x]['recall'][0]) for x in shown)
                 + f" | {dci(a['pairs']['H1 arm2-arm1 recall'])} | {dci(a['pairs']['H1s arm2-arm2e recall'])} |")
    L += ["", "ค่าในตารางคือ recall before largest ที่ budget 20/10k · holdout ไม่ถูกใช้ตอน train หรือจูน", ""]
    if REHEARSAL:
        L += ["Mimicry ใช้เฉพาะ test; rehearsal บน validation จึงยังประเมิน H4/G7 ไม่ได้", ""]

    # 6 examples
    L += ["## 6. สิ่งที่จับไม่ได้ และพฤติกรรมสุจริตที่ถูกเตือน", ""]
    for x in res["examples"]["missed_episodes"]:
        L += [f"**Episode ที่ arm 2 ไม่เตือนก่อนก้อนใหญ่สุด** `{x['episode_id']}` variant: {x['variant'] or 'ไม่มี'}", "",
              "| วัน | payer → payee | ยอด | route | ประเภท | คะแนน arm 2 |", "|---|---|---|---|---|---|"]
        L += [f"| {r['day']} | {r['payer']} → {r['payee']} | {r['amount_thb']:,.0f} | {r['route']} | {r['txn_type']} | "
              f"{'–' if r['arm2_score'] is None else r['arm2_score']} |" for r in x["rows"]]
        L.append("")
    for x in res["examples"]["false_warnings"]:
        L += [f"**รายการสุจริตที่ arm 2 เตือน** กลุ่ม {HN_TH.get(x['group'], x['group'])} (`{x['hn_id']}`)", "",
              "| วัน | payer → payee | ยอด | route | ประเภท | คะแนน arm 2 |", "|---|---|---|---|---|---|"]
        L += [f"| {r['day']} | {r['payer']} → {r['payee']} | {r['amount_thb']:,.0f} | {r['route']} | {r['txn_type']} | "
              f"{'–' if r['arm2_score'] is None else r['arm2_score']} |" for r in x["rows"]]
        L.append("")

    # 7-9
    L += ["## 7. ข้อจำกัด", "",
          "- **Circularity:** scam ใน simulator มาจากสมมติฐาน typology ของทีม arm 2 จึงได้เปรียบโดยโครงสร้างบน family A "
          "มาตรการที่ใช้: ช่วงพารามิเตอร์ตั้งโดย generator agent ที่ไม่เห็น feature/threshold (`docs/lab/G0_GENERATOR_BRIEF.md`) "
          "แต่ผู้เขียนฝั่ง detector เติมส่วนท้ายของ implementation หลัง generator หยุด (D47) และ brief ระบุ typology เงินล่อ + ยอดไต่ให้ generator ตรง ๆ "
          "จึงกันได้แค่การจูนช่วงพารามิเตอร์ตาม threshold ไม่ได้กันสมมติฐานหรือ implementation bias ทั้งหมด · "
          "placebo family D (arm 2 − arm 2e), ablation arm 2e, holdout 2 แบบที่ไม่เข้า train, mimicry ซึ่งปรับแค่จังหวะเวลาและอัตราเงินคืน "
          "(บัญชีรับยังใหม่และยอดยังไต่)",
          "- ข้อมูลเป็น simulator ทั้งหมด ไม่ได้ทดสอบบนพฤติกรรมจริง (Berka ยังไม่ได้ audit) · prevalence 1:5,000 และ 1:50,000 เป็นสมมติฐาน ไม่ใช่ค่าของไทย",
          "- Arm 0 ไม่มี CFR mock ส่วนที่ TP ดีกว่า arm 0 จึงเป็นขอบบน · หนึ่งคนหนึ่งบัญชี · ไม่จำลองการแทรกแซงของธนาคาร · "
          "ใช้รายการสำเร็จแทน intent · field ที่ยังไม่ยืนยันว่า PromptPay มี = สมมติใน simulator",
          "- ความหนาแน่นของ hard negatives กลุ่มที่พบน้อยถูกยกให้พอวัดได้ จึงน่าจะสูงกว่าจริง · calibration ไม่ได้ตรวจ",
          "- Hard negatives 3 กลุ่มของ v3.3 §7.3 ถูกตัดออก (ค่าแรง · ค่าคอม · วงแชร์) ไม่ทราบอัตราเตือนผิดบนพฤติกรรมเหล่านี้ "
          "ซึ่งเป็นพฤติกรรมสุจริตที่มีเงินเข้าก้อนเล็กจากคู่ค้าแล้วโอนออกมากขึ้นได้",
          "- บัญชีม้า (payer เป็นบัญชี ring) ถูกตัดจากประชากร T2 จำนวน alert บนกลุ่มนี้อยู่ใน §2 · CI ครอบคลุมเฉพาะความแปรปรวนของ "
          "split นี้ในโลกจำลองเดียวกับโมเดลเดียว ไม่รวมความแปรปรวนจาก seed ของ simulator หรือการ train", "",
          "## 8. สิ่งที่ต้องใช้ข้อมูลจริงจากธนาคาร/NITMX", "",
          "ตาม v3.3 §7.4 และ legal/data pack §10: Tier 1 ธุรกรรม P2P ข้ามธนาคารของลูกค้าธนาคารนำร่อง 2 แห่ง 12 เดือน "
          "(ขั้นต่ำ 9) พร้อมเคสยืนยันที่ผูก `event_id` และ label 60 วัน เพื่อวัด base rate ของ pattern, recall และเตือนผิดต่อการจับถูก "
          "ที่ prevalence จริง · ต้องผ่าน Legal sign-off A8/A9 ก่อน · ส่วน B ต้องผ่าน A1-B", "",
          "## 9. Protocol deviations", "", "| #" + deviations.rstrip(), ""]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(L))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
