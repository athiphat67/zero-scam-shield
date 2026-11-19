# G-0 Experiment Protocol — freeze sheet

> **สถานะ: APPROVED 29 ก.ย. 2026** · ทีมตอบ Q1 budget หลัก 20/10k · Q2 เก็บ placebo · Q3 SHOULD เริ่มที่ H4 · แก้ต่อจากนี้ทาง `PROTOCOL_DEVIATIONS.md` เท่านั้น
> นิยาม feature / rule / label / metric / gate ใช้ตาม v3.3 §6.1–6.2, §7.1–7.3, §8.1–8.4, §14.1 ตรงตัว · เอกสารนี้ตรึงเฉพาะการตัด scope และค่าที่ v3.3 เปิดไว้
> **ผลทั้งหมด = learnability บนข้อมูลจำลอง ไม่ใช่ production accuracy**

## 1. คำถามและเกณฑ์ (เขียนก่อนเห็นผล)

| | คำถาม | Endpoint บน test | ผ่าน / ไม่ผ่าน / สรุปไม่ได้ |
|---|---|---|---|
| **H1** | TRUST ช่วยเตือนก่อนก้อนใหญ่สุดได้มากกว่า GENERIC ไหม | Δ recall before largest = arm 2 − arm 1 · episode family seed-payout · budget หลัก | paired 95% CI (ring bootstrap) > 0 / < 0 / คร่อม 0 |
| H2 | rule T2 และ ML ชนะ arm 0 ไหม · ML ชนะ rule ไหม (G1) | Δ rule − arm 0 · Δ arm 2 − rule | เกณฑ์เดียวกับ H1 · G1 ผ่านเมื่อ CI ของ Δ arm 2 − rule > 0 |
| H3 | เตือนผิดบน hard negatives รายกลุ่ม (G3) | false-warning rate ต่อ hard-negative intent ต่อกลุ่ม ต่อ arm | G3 ผ่านเมื่อ arm 2 ≤ rule ทุกกลุ่มที่ budget หลัก (point estimate) พร้อมแสดง CI |
| H4 · SHOULD | ผลอยู่ไหมเมื่อมี mimicry และ variant ใหม่ (G7) | recall ที่ mimicry 0.5 เทียบ 0 · recall บน novel holdout | G7 ผ่านเมื่อลดลง ≤ 30% relative ที่ threshold เดิม |
| H5 · SHOULD | B เพิ่มอะไรเหนือ arm 2 บน simulator | Δ arm 3 − arm 2 | เกณฑ์เดียวกับ H1 |
| Placebo | TRUST ไม่ควรช่วยกับ scam ที่ไม่มีเงินล่อ | Δ arm 2 − arm 1 บน family no-seed | CI > 0 = สัญญาณ artifact ต้องตรวจก่อนอ้าง H1 |

ประชากรของ H1 = episode family A ใน test ที่ไม่ใช่ holdout (รวม variants ตามที่ generator สร้าง) · Budget หลักของ H1/G1 = **ELEVATED+HIGH 20/10k** · รายงาน 5/10k และ 1/10k ด้วย · ตัวรองของ H1: mean normalized exposure, missed-episode rate · ถ้า arm 1 ≈ arm 2 ให้รายงานตรง ๆ (§8.4)

## 2. ข้อมูล

| หัวข้อ | ค่าที่ตรึง |
|---|---|
| แหล่ง | simulator หลายธนาคารอย่างเดียว (MUST) · AOC 191 เคส ใช้ออกแบบ scenario เท่านั้น (§7.4) · Berka = SHOULD audit 1 ชม. (ยังไม่มีไฟล์ในเครื่อง) |
| Scenario / ช่วงพารามิเตอร์ | `G0_SCENARIO_SPEC.md` เขียนโดย generator agent ที่เห็นเฉพาะ `G0_GENERATOR_BRIEF.md` + ข้อมูล AOC ไม่เห็น `features.py` / §6 · ค่าในนั้นตรึงพร้อม protocol นี้ |
| ขนาด | บัญชีบุคคล ~12,000 · 6 ธนาคาร · 450 วัน · test ≥ 100,000 eligible intents, ≥ 200 episodes, ≥ 40 rings · val ≥ 200 / 40 · train ≥ 600 / 120 · hard negatives ≥ 300 subjects ต่อกลุ่มต่อ split · generate < 10 นาที |
| Scam (MUST) | **Family A** seed-payout ladder (ลำดับแบบ §14) ฉีดลงบัญชีปกติ · เงินล่อจากบัญชีเดียวกับผู้รับ / คนละบัญชี · หมุนผู้รับ (AOC มัธยฐาน 4 บัญชี ≥ 2 ธนาคาร, D42) · 1–4 seeder ต่อ ring · **Family D** drain ไม่มีเงินล่อ = placebo · variants `SPLIT` / `LONG_GAP` / `ON_US_HOP` อยู่ในทุก split ตามสัดส่วนของ spec (detector side ไม่ได้เลือกเอง) · holdout `FRAGMENTED_SEED` / `AGED_RECEIVER` อยู่ใน test เท่านั้น |
| Hard negatives (MUST) | 6 กลุ่มตาม prompt: ร้านค้าบุคคลคืนบางส่วน · เพื่อนคืนเงินยืม · หารค่าเที่ยว/กิน · ครอบครัว · มัดจำแล้วคืน · โอนสุจริตที่ยอดไต่ขึ้น |
| Observation view | **switch view** = P2P ข้ามธนาคารที่สำเร็จเท่านั้น on-us มองไม่เห็น (§2.1) · feature ทุกตัวคำนวณบน view นี้ · field ที่ยังไม่ยืนยันว่า PromptPay มี = "สมมติใน simulator" |
| Eligible T2 intent | settled P2P, payer และ payee เป็น PERSON, CROSS_BANK, อยู่ใน window ของ split · payer ไม่ใช่บัญชีของ ring (T2 ประเมินฝั่งลูกค้าที่อาจเป็นเหยื่อ · ตัดด้วย metadata ฝั่งประเมินเท่านั้น และรายงานจำนวน) · ใช้รายการสำเร็จแทน intent (§7.4) · merchant / bill / payroll ไม่ eligible · score ทุก intent โดยไม่ route `INSUFFICIENT_HISTORY` (§2.2) แต่รายงานสัดส่วนที่เข้าข่าย |
| Label (§7.2) | T2 positive = รายการ scam ออกทุกก้อนของเหยื่อรวมก้อนแรก (`CONFIRMED_SCAM` และ payer = `subject_token`) · training cutoff = วันที่ 330 (train จบ + 60 วัน maturation) · train ใช้เฉพาะ positive ที่ `label_effective_ts ≤ 330` ที่เหลือเป็น negative proxy และนับรายงาน · val/test ใช้ ground truth หลัง mature (simplification: ใน production label ของ val ยังไม่ครบ ณ วันที่ 330 · ไม่เปิดข้อมูล test เพราะ ring และช่วงเวลาไม่ทับกัน) |

## 3. Split, ring holdout, purge

| ช่วง (day) | 0–89 | 90–269 | 270–329 | 330–449 |
|---|---|---|---|---|
| ใช้ทำ | warm-up (เป็น history เท่านั้น) | train | validation: early stopping, grid ของ rule, threshold | test: เปิดครั้งเดียว |

- Temporal split · ring ถูก assign split เดียว และทุก event ของ episode อยู่ใน window นั้น · บัญชี seeder/ผู้รับไม่ข้าม split · เหยื่อ ≤ 1 episode
- Purge: scam intent ที่หลุดนอก window ของ split ตัวเองจะไม่ถูก score ใน split อื่น (คาดว่า 0 และรายงานจำนวน) · state ของ feature เดินต่อเนื่องทั้ง timeline เพราะ history ใช้ได้จริงใน production
- Novel-variant holdout อยู่เฉพาะ test และรายงานแยกจาก endpoint หลัก

## 4. Arms (§8.4) และ operating point

| Arm | Score | Knob ที่เลือกบน validation |
|---|---|---|
| 0 control เดิม | ผู้รับใหม่ (`relationship_age_observed_days` missing) และยอด ≥ X · **ไม่มี CFR mock** (ตัด scope) | X ที่ budget |
| Rule T2 (§6.2) | `seed_like_inbound_count_90d` ≥ k และยอด ≥ m × max(ยอดสูงสุดให้คู่นี้, ยอดสูงสุดในกลุ่มคู่ใหม่) ถ้าไม่มีทั้งสองใช้ p95 established ถ้าไม่มีเลยไม่ fire | k ∈ {1,2,3} · m ต่อเนื่องที่ budget (ค่า grid 2/3/5 รายงานเป็นจุดอ้างอิง) |
| 1 generic | LightGBM บน `GENERIC` 9 ตัว | threshold ที่ budget |
| 2 + trust provenance | LightGBM บน `GENERIC + TRUST` 19 ตัว | threshold ที่ budget |
| 3 + B · SHOULD | arm 2 + `NETWORK` (`receiver_fan_in_7d`) | threshold ที่ budget |

- Feature จาก `src/tp/features.py` ชุดเดียว · LightGBM hyperparameter ตรึงล่วงหน้าและเหมือนกันทุก arm (binary, lr 0.05, num_leaves 31, min_child_samples 50, early stopping 50 รอบบน validation AP, seed คงที่) · ไม่ทำ SMOTE / class weight · missing = NaN · calibration ไม่ตรวจ (รายงาน unverified)
- **Budget กับข้อมูลที่ scam หนาแน่น:** simulator มี positive หนาแน่นกว่าจริงมาก ถ้านับเตือนดิบต่อ 10k รายการ recall จะถูกกดด้วยความหนาแน่นแทนความสามารถ จึงเลือก threshold ต่ำสุดที่ `FPR_val(t)·(1−p) + TPR_val(t)·p ≤ B` ที่ p = 1:5,000 (อัตราเตือนที่ธนาคารจะเห็นที่ prevalence นั้น ตาม §8.2) · B ∈ {1, 5, 20}/10k · level: HIGH = ผ่าน threshold 5/10k, ELEVATED = ผ่าน 20/10k
- Test ใช้ threshold เดิม รายงาน realized rate และจำนวนดิบ · เทียบที่ FPR เท่ากันบน test เป็น diagnostic เท่านั้น ไม่ใช้ตัดสิน

## 5. Metrics และ gates

- Recall before largest = episode ที่มีเตือนบน scam intent ใดก็ได้ ณ หรือก่อนก้อนใหญ่สุด (ยอดเท่ากันใช้ก้อนแรก) · missed-episode rate · mean normalized exposure = mean(E_e / L_e) โดย L_e รวมก้อนที่ switch มองไม่เห็นด้วย และ missed มีค่า 1 (§8.1)
- FP:TP ที่ p = 1:5,000 และ 1:50,000 = `FPR·(1−p) / (TPR·p)` ระดับ intent พร้อม TP/FP ดิบ · false-warning rate รายกลุ่ม hard negative · ตัวรอง: PR-AUC ระดับ intent และ episode ที่จับได้เพิ่มจาก arm 0 ที่ weighted FP:TP 5:1 (threshold จาก validation ตาม §8.4 / D42)
- CI: percentile bootstrap 2,000 รอบ · ตัววัดระดับ episode resample ring · ตัววัดระดับ FPR resample บัญชี subject · ผลต่างแบบ paired ใช้ resample ชุดเดียวกันทั้งสอง arm · ทุกตารางแสดงจำนวน transactions / accounts / episodes / rings / หน่วย bootstrap
- Gates ที่ใช้: **G1, G2** (weighted FP:TP ≤ 5:1 ที่ p = 1:5,000 และ budget 5/10k), **G2b** (≤ 20:1 ที่ 20/10k), **G3, G4** (leakage test ผ่านครบ ไม่มี ring overlap · PR-AUC ≥ 0.99 = ต้อง audit ก่อนอ้าง), **G6** (4 ฉากจาก replay จริง) และ **G7** ถ้าทำ · ไม่ใช้ G5, G8–G11 · ผ่าน gate บน synthetic ≠ พร้อม production

## 6. Leakage และความถูกต้อง (unittest ต้องผ่านก่อน train)

Point-in-time (คำนวณซ้ำจาก history ที่ตัด `ts < t` แล้วต้องเท่ากัน **และต้อง fail เมื่อจงใจใส่ feature ที่รั่ว**) · score ก่อน update state · metadata (`episode_id, scenario, ring_id, is_synthetic, synthetic_fields, generator_version`) ไม่อยู่ใน feature path และสลับค่าแล้ว feature ไม่เปลี่ยน · token ไม่บอกบทบาท · ring/บัญชีแก๊งไม่ข้าม split · determinism (seed เดิม = SHA-256 เดิมทั้ง events, labels และ split) · dedupe `event_id` · feature parity ระหว่าง batch กับ replay ของ demo · เลือก threshold จาก validation เท่านั้น (แก้แถว test แล้ว threshold ต้องไม่เปลี่ยน)

## 7. ขั้นเปิด test

ลำดับคำสั่ง: `python -m tp.sim` → `python -m tp.dataset` → `python -m tp.train` → `python -m tp.evaluate` → `python scripts/make_report.py` → `python -m tp.demo`

1. `python -m tp.train` เขียน `artifacts/protocol_manifest.json`: SHA-256 ของ `src/tp/*.py`, scripts, spec และ protocol (โค้ดยังไม่ commit จึงใช้ SHA-256 แทน git hash) · seed · ขอบ split · จำนวนแถว · threshold ต่อ arm × budget · k ของ rule · LightGBM params + best iteration · p · จำนวนรอบ bootstrap
2. `python -m tp.evaluate` ปฏิเสธการรันถ้า hash ไม่ตรง manifest · ถ้ารันซ้ำหลังเห็นผลต้องใส่เหตุผล ซึ่งจะถูกบันทึกลง `PROTOCOL_DEVIATIONS.md`
3. `python scripts/make_report.py` สร้าง `reports/G0_LAB_REPORT.md` จาก `artifacts/*.json` เท่านั้น

## 8. อ้างได้ / อ้างไม่ได้

- **อ้างได้:** "บน simulator (synthetic, switch view) ที่ฉีด scam ลงพฤติกรรมปกติ ที่งบเตือนเท่ากัน arm 2 ต่างจาก arm 1 เท่ากับ X (95% CI …)" · pipeline point-in-time ผ่าน test ที่ระบุ · อัตราเตือนผิดบน hard negatives แบบสังเคราะห์รายกลุ่ม
- **อ้างไม่ได้:** production accuracy/precision · prevalence ของไทย · prevented loss (ใช้ "value flagged before loss") · คุณค่าของ B ในเครือข่ายจริง · ผลบนพฤติกรรมจริง (ถ้า Berka ไม่ผ่าน) · ว่า PromptPay มี field ใดจริง
- Circularity: generator มาจากสมมติฐาน typology ของทีม arm 2 จึงได้เปรียบโดยโครงสร้างบน family seed-payout · ส่วนที่มีความหมายคือ arm 1 จับได้เท่ากันหรือไม่, ต้นทุนบน hard negatives, mimicry และ placebo

## 9. Scope

- **MUST:** simulator + injection + hard negatives + labels + split + leakage tests · arm 0, rule T2, arm 1, arm 2 · threshold บน validation · metrics + CI ข้อ 5 · replay 4 ฉาก (§14.1, ติดป้าย SYNTHETIC, แสดงผลจริงแม้ B ไม่เตือนหรือ D เตือน) · report
- **SHOULD (ทำตามลำดับ ตัดจากท้ายถ้าไม่ทัน):** 1) mimicry 0/0.5/1 + novel holdout (H4) · 2) arm 3 (H5) · 3) ผลแยกราย variant · 4) sensitivity ความหนาแน่น hard negatives ×⅓ และ ×3 (reweight ราย `hn_id`; กลุ่มที่พบน้อยถูกยกให้ถึง 300 ต่อ split จึงน่าจะสูงกว่าจริง) · 5) Berka audit 1 ชม. · 6) rule T1 + burden
- **OUT → roadmap ใน report:** T3 / Fraud Ops · G8 T1+T2 budget allocation · G5, G9–G11 · CFR mock · metadata หาย · late event · token rotation · cap exhaustion · latency SLO · serving API · UI · calibration เต็มรูปแบบ · AMLworld / PaySim · bank-local view

## 10. จุดที่ prompt ต่างจาก v3.3 (ตัดสินแล้ว)

1. Hard negatives: prompt 6 กลุ่ม ส่วน v3.3 §7.3 มี 8 กลุ่ม (ตัดค่าแรง / ค่าคอม / วงแชร์ เพิ่มโอนสุจริตที่ยอดไต่ขึ้น) → ยึด prompt (ตัด scope) และบันทึก 3 กลุ่มที่ตัดเป็น roadmap
2. Arm 0 ไม่มี direct CFR mock (§8.4 มี) → ยึด prompt · ส่วนที่ TP ดีกว่า arm 0 เป็นขอบบน เพราะ control จริงแรงกว่านี้
3. Berka: v3.3 §7.1 ให้เป็นตัวเลือกแรก ส่วน prompt ให้เป็น SHOULD 1 ชม. → ยึด prompt · AGENTS ข้อ 5 ("ฉีดเข้าประวัติบัญชีจริง") จึงทำได้แค่ประวัติบัญชีจำลอง ถ้าไม่ทำ Berka ให้เขียนใน `data/SOURCES.md` และ report ว่ายังไม่ได้ประเมินบนพฤติกรรมจริง
4. Budget ถ่วงด้วย p = 1:5,000 (ข้อ 4) เป็นการตีความ §8.2 เมื่อข้อมูลหนาแน่น ไม่ใช่นิยามใหม่
5. Rule T2 ใช้ m ต่อเนื่องที่ budget แทน grid 3 ค่า เพื่อให้ rule ได้ใช้งบเท่ากับ ML ทำให้ G1 ผ่านยากขึ้น (อนุรักษ์นิยม)
