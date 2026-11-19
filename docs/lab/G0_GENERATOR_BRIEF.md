# G-0 Generator Brief — ส่งให้ generator agent (detector-blind)

> เอกสารนี้คือ **ทุกอย่างที่ผู้เขียน generator ได้รู้** เก็บไว้เป็นหลักฐานว่า simulator ไม่ได้ออกแบบจาก threshold ของ detector (integrity ข้อ 3 ของ G-0)
> ผู้เขียน brief (detector side) ตั้งใจไม่ใส่นิยาม feature, ช่วงเวลาที่ feature ใช้, threshold ของ rule หรือเลขของ demo

## บทบาท

คุณเป็นผู้ออกแบบ simulator ของทีม Trust Provenance ที่ **ไม่รู้ว่า detector ทำงานอย่างไร** เป้าคือข้อมูลจำลองที่สมจริงและหลากหลาย ไม่ใช่ข้อมูลที่ detector ใดจับง่ายหรือยาก ถ้าลังเลระหว่างสองค่า ให้เลือกช่วงที่กว้างกว่าและบอกเหตุผล

Trust Provenance (ระดับแนวคิด): ให้คะแนนความเสี่ยงของรายการโอนออกของบุคคลก่อนกดยืนยัน โดยดูประวัติการโอนเข้า/ออกของบัญชีนั้นกับคู่บัญชีต่าง ๆ · typology ที่สนใจ: ผู้เสียหายโอนเงินให้บัญชีที่เพิ่งรู้จัก ได้เงินก้อนเล็กคืน (เงินล่อ) แล้วโอนยอดใหญ่ขึ้นเรื่อย ๆ

## ขอบเขตความรู้ (บังคับ มีลำดับเหนือ AGENTS.md สำหรับงานนี้)

**อ่านได้เท่านั้น:**
- ไฟล์นี้
- `../10-research/03-scam-cases/aoc1441-ch2-delivery/README.md`
- `../10-research/03-scam-cases/aoc1441-ch2-delivery/data/` เฉพาะ `aoc_cases.csv`, `aoc_accounts.csv`, `aoc_event_annotations.csv`, `fraud_taxonomy.csv`, `quality_report.json`, `source_manifest.csv`

**ห้ามเปิดหรือ grep:** `src/`, `tests/`, `DECISIONS.md`, `CONTEXT.md`, `MILESTONES.md`, `product_design/`, `references/`, ไฟล์อื่นใน `docs/lab/`, ไฟล์ `synthetic_*` และ `reason_codes.csv` ในโฟลเดอร์ AOC (สร้างคู่กับ detector รุ่นเก่า), `../30-prototype/`, `../20-solution/`, `../reports/`, `../10-research/` ส่วนอื่น
ถ้าต้องรู้อะไรนอกนี้ ให้เขียนเป็นคำถามในหัวข้อ "คำถามถึง detector side" ของ spec แทนการเปิดไฟล์

## ข้อเท็จจริงจาก AOC ที่ทีมใช้อยู่ (ตรวจซ้ำจากข้อมูลได้)

- 191 เคส · ความเสียหาย median 46,400 บาท · heavy tail · เป็นเคสคัดเผยแพร่ ไม่ใช่ประชากร · ไม่มีวันเวลาระดับเหตุการณ์
- `weak_archetype = A_SEED_PAYOUT_LADDER` 14 เคส (typology หลัก) · `D_ESCALATING_DRAIN` 32 เคส
- 14 เคสที่มีเงินล่อ: บัญชีปลายทางมัธยฐาน 4 บัญชี, กระจายมัธยฐาน 2 ธนาคาร · 7/14 เคส PDF แสดงรายชื่อไม่ครบ (`destination_list_complete=0`) จึงเป็นค่าขั้นต่ำ ให้ใช้ `declared_account_count`

## Simulator ที่ต้องการ

**พฤติกรรมปกติหลายธนาคาร** (ไทย, retail, PromptPay/โอนบัญชี): 6 ธนาคาร market share ไม่เท่ากัน · บัญชีบุคคลราว 12,000 (ปรับได้ตามข้อกำหนดขนาด) ที่ระดับกิจกรรมต่างกันมาก · P2P กับคู่ประจำ (ค่าเช่า, ครอบครัว, เพื่อน), คู่ใหม่ที่เกิดขึ้นตามธรรมชาติ, เงินเดือน, บิล, ร้านค้า (merchant/bill/payroll ต้องมี `txn_type`/`payee_type` ที่แยกจาก P2P ได้) · ทุกบัญชีมีทั้งเงินเข้าและเงินออก · โอนภายในธนาคารเดียวกัน (on-us) ต้องมีจริงตามสัดส่วน share

**Scam injection ลงในบัญชีปกติ** (ไม่ใช่ลำดับสะอาดแยกก้อน; เหยื่อยังมีกิจกรรมปกติต่อระหว่าง episode):
- Family หลัก = seed-payout ladder ตาม AOC: เหยื่อโอนออกหลายก้อนเข้าบัญชีปลายทางที่หมุนเปลี่ยน (หลายธนาคาร) ระหว่างทางได้เงินก้อนเล็กคืน บางครั้งเงินคืนมาจากบัญชีเดียวกับที่เหยื่อโอนไป บางครั้งมาจากบัญชีอื่นของแก๊ง (seeder) · ยอดไต่ขึ้น · ring (แก๊ง) หนึ่งมีหลาย seeder และหลายบัญชีรับ และหลอกเหยื่อหลายราย
- Family เทียบ (รอทีมตัดสิน ให้ spec ไว้ด้วย) = escalating drain แบบไม่มีเงินล่อ ตาม `D_ESCALATING_DRAIN`
- ทุก parameter (จำนวนก้อน, ยอดก้อนแรก, ความเร็วไต่ยอด, ยอดรวม, สัดส่วนเงินคืน, จังหวะเวลาระหว่างขั้น, จำนวนบัญชีรับ/ธนาคาร/seeder, จำนวนเหยื่อต่อ ring, ระยะเวลาที่เหยื่อแจ้งความ) **สุ่มเป็นช่วงกว้าง** อิง AOC ถ้ามี (ระบุ field/สถิติ) ถ้าไม่มีให้ติด [อนุมาน] และให้เหตุผล · อ่าน narrative / event annotation ของ 14 เคสได้เพื่อหาจังหวะเวลาและยอดเงินคืนที่เอกสารเล่าไว้
- Variants: ซอยยอด (ก้อนใหญ่แตกหลายรายการ) · เว้นช่วงยาวระหว่างขั้น 40 / 60 / 90+ วัน · บาง hop เป็น on-us (บัญชีรับอยู่ธนาคารเดียวกับเหยื่อ) · เสนอ 1–2 variant เป็น **novel holdout** ที่อยู่เฉพาะชุด test พร้อมเหตุผล

**Hard negatives 6 กลุ่ม** (พฤติกรรมสุจริตที่หน้าตาคล้าย scam; มีทั้งเงินออก เงินเข้า และรายการถัดไป):
1. ร้านค้าออนไลน์บัญชีบุคคลคืนเงินบางส่วน (ลูกค้าโอนซื้อ ร้านคืนบางส่วน ลูกค้าซื้อต่อ)
2. เพื่อนคืนเงินยืม
3. หารค่าเที่ยว/ค่ากิน (คนหนึ่งจ่ายก่อน เพื่อนหลายคนโอนส่วนของตนคืน)
4. ครอบครัว
5. รับมัดจำแล้วคืน
6. โอนสุจริตที่ยอดไต่ขึ้น (เช่น ผ่อนงวด/จ้างงานที่ยอดเพิ่ม)
เลือก subject ของ hard negatives และเหยื่อจาก **ประชากรปกติชุดเดียวกันแบบสุ่ม** ไม่เลือกตามลักษณะที่ทำให้แยกกลุ่มได้ง่าย · ความถี่ของแต่ละกลุ่มในประชากรเป็น [อนุมาน] ให้บอกเหตุผล (ทีมจะรายงาน sensitivity แยก)

**Mimicry (SHOULD):** `mimicry = m` = สัดส่วน scam episodes ที่ **เวลาและอัตราส่วนเงินคืน** ถูกสุ่มจาก distribution ของ hard negatives ที่คำนวณจากชุด train เท่านั้น · ค่า m ∈ {0, 0.5, 1.0} ใช้กับ ring ของชุด test เท่านั้น · ground truth ของ scam คงเดิม · ส่วนอื่นของข้อมูลต้องเหมือนเดิมทุกไบต์เมื่อเปลี่ยน m

## ข้อกำหนดจาก detector side (ขนาด เวลา รูปแบบ — ไม่ใช่ threshold)

- ช่วงเวลา (day index): warm-up 0–89 (ไม่มี scam) · train 90–269 · validation 270–329 · test 330–449
- ring ถูก assign ให้ split เดียว และ event ทุกตัวของทุก episode ต้องอยู่ใน window ของ split นั้น · บัญชีของแก๊ง (seeder/บัญชีรับ) ไม่ปรากฏข้าม split · เหยื่อถูกหลอกไม่เกิน 1 episode
- ขั้นต่ำ: test ≥ 100,000 eligible intents (P2P บุคคล→บุคคล ข้ามธนาคาร สำเร็จ ในช่วง test) และ ≥ 200 scam episodes จาก ≥ 40 rings · validation ≥ 200 episodes / ≥ 40 rings · train ≥ 600 episodes / ≥ 120 rings · hard negatives แต่ละกลุ่ม ≥ 300 subjects ต่อ split (ต่อ train/validation/test)
- Deterministic จาก seed เดียว (seed เดียวกัน = ไฟล์เหมือนกันทุกไบต์) · generate ทั้งหมด < 10 นาทีบน laptop (เป้า < 3 นาที) ด้วย Python + numpy/pandas
- Token แบบ opaque สุ่ม ไม่บอกบทบาท/class · `is_synthetic=1` ทุกแถว · `ts` เป็นวินาที UTC · `ingested_at = ts` (late event อยู่นอก scope) · ยอดเป็นบาททศนิยมไม่เกิน 2 ตำแหน่ง > 0
- Events (schema กลาง): `event_id, ts, ingested_at, payer_token, payee_token, payer_bank, payee_bank, amount_thb, txn_type, payer_type, payee_type, channel, rail, route_scope, event_status, source, is_synthetic, synthetic_fields` · `payer_type`/`payee_type` ∈ PERSON / MERCHANT / BILLER / EMPLOYER / UNKNOWN · `route_scope` ∈ CROSS_BANK / ON_US
- Labels (schema กลาง): `label_id, label_unit, event_id, intent_id, intent_revision, episode_id, subject_token, window_start, window_end, label, label_source, event_ts, report_ts, label_effective_ts, review_reference, revision_of` · ทุกรายการโอนออกของ scam รวมก้อนแรก = `TRANSACTION / CONFIRMED_SCAM / INJECTED` · เงินล่อเข้าติด label แยก (ใช้ภายหลัง) · `label_effective_ts` = หลังรายการ scam สุดท้าย + ระยะแจ้งความที่สุ่ม
- Metadata แยกตาราง (ไม่อยู่ในตาราง events): episodes (`episode_id, ring_id, split, family, variant, victim_token, seeder_tokens, receiver_tokens, start_ts, end_ts, loss_thb, mimicry_applied, is_holdout`) และ hard negatives (`hn_id, group, subject_token, counterpart_tokens, event_ids, start_ts, end_ts`)

## ส่งมอบรอบนี้ (Phase 0 — spec เท่านั้น ยังไม่เขียนโค้ด)

`docs/lab/G0_SCENARIO_SPEC.md` ภาษาไทย ≤ ~3 หน้า:
1. ตาราง parameter: ชื่อ · ช่วง/การแจกแจง · ที่มา ([AOC: field/สถิติ] หรือ [อนุมาน]) · เหตุผลหนึ่งบรรทัด
2. ประชากรปกติ, โครง ring/episode, variants + novel holdout ที่เสนอ, hard negatives, mimicry, ระยะแจ้งความ
3. สถิติ sanity ที่จะรายงานหลัง generate (เช่น P2P ต่อบัญชีต่อเดือน, สัดส่วน on-us) — เป็นความสมจริง ไม่ใช่ผลของ detector
4. Knowledge boundary: รายชื่อไฟล์ที่อ่านจริง
5. คำถามถึง detector side (ถ้ามี)

Phase 1 (หลังทีมอนุมัติ) จะขอให้เขียน `src/tp/sim.py` + `tests/test_sim.py` ตาม spec นี้
