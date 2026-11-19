# G-0 Lab — Progress

> อ่านไฟล์นี้ก่อนทำต่อทุกครั้ง · protocol: `G0_EXPERIMENT_PROTOCOL.md` · spec ของ simulator: `G0_SCENARIO_SPEC.md` (เขียนโดย detector-blind agent จาก `G0_GENERATOR_BRIEF.md`)

## Phase 0 — audit + protocol (29 ก.ย.) · ✅ อนุมัติแล้ว

เสร็จ:
- Audit: `src/tp/features.py` + 8 tests ผ่าน · `GENERIC`/`TRUST`/`NETWORK` ตรง arm 1/2/3 ของ §8.4 · ยังไม่มี simulator, label, rule, training, evaluation, demo replay, `data/`, `docs/` · `src/` และ `tests/` ยังไม่ถูก commit (manifest จึงใช้ SHA-256)
- ข้อมูลที่มี: AOC 191 เคส (ระดับเคส ไม่มีเวลาระดับเหตุการณ์; seed-payout 14 เคส, escalating drain 32 เคส) · synthetic ชุดเก่าใน AOC delivery ใช้ไม่ได้ (episode สะอาดแยกก้อน + ออกแบบคู่กับ rule เก่า) · Berka ไม่มีในเครื่อง (`../data/external/` หายไป) ต้องดาวน์โหลดถ้าจะทำ SHOULD · ไม่มีข้อมูล NITMX/ธนาคาร
- Timing: `replay()` ≈ 43 µs/event (270k events 11.7 วินาที) → ~2–3M events รันได้ในไม่กี่นาที
- Protocol draft + generator brief · generator agent (detector-blind) ส่ง `G0_SCENARIO_SPEC.md` แล้ว: family A seed ladder 160/55/80 rings, family D drain (placebo) เพิ่มครึ่งหนึ่ง, ~5 เหยื่อต่อ ring, holdout `FRAGMENTED_SEED` + `AGED_RECEIVER` เฉพาะ test, HN 6 กลุ่ม 1.5–6% ต่อบัญชีต่อ 30 วัน · ช่วงพารามิเตอร์อิง AOC รายเคส (เช่น อัตราเงินล่อ 0.18–14.5 ทำให้ ~50% ของเงินล่อ ≥ ยอดก้อนก่อนหน้า)
- ตอบคำถาม 9 ข้อของ generator ใน spec §6 (schema/ขอบเขตเท่านั้น ไม่แก้ช่วงพารามิเตอร์)

ตัดสินไปแล้ว (รายละเอียดใน protocol ข้อ 10): budget ถ่วงที่ p = 1:5,000 · rule T2 ใช้ m ต่อเนื่อง · training cutoff วันที่ 330 · switch view = P2P ข้ามธนาคารเท่านั้น · ตัดรายการที่ payer เป็นบัญชี ring ออกจากประชากร T2 · ประชากร H1 = family A ใน test ที่ไม่ใช่ holdout

ค้าง ณ ตอนร่าง (ปิดแล้ว): คำตอบ Q1–Q3 และการอนุมัติ protocol + spec · Phase 1 ให้ generator agent ตัวเดิมเขียน `src/tp/sim.py` + `tests/test_sim.py` จาก spec

**อนุมัติ 29 ก.ย.** (`APPROVE G0 PROTOCOL`): budget หลัก 20/10k · เก็บ placebo · SHOULD เริ่มที่ H4 → D43 · SHA-256 ตอนอนุมัติอยู่ใน `PROTOCOL_DEVIATIONS.md`

Audit ก่อนเปิด test (29 ก.ย.): ตรึง source tables, ชุด mimicry และตัวสร้างรายงานใน manifest; รายงานต้องแสดง validation labels ที่รู้หลัง cutoff และจำกัดข้ออ้างเป็นการจูนย้อนหลัง · รายละเอียดใน `G0_AUDIT.md` และ `PROTOCOL_DEVIATIONS.md`

ตรวจซ้ำ 30 ก.ย. → deviation 2 / D45 (ก่อนมีข้อมูล): arm 2e + H1s, placebo = arm 2 − arm 2e บน D, กติกา ceiling / งบจริง / G3 / G4, ถ้อยคำ G2, `G0_DATA_CONTRACT.md`, rehearsal บน validation · deviation 3 / D46: fit เฉพาะแถว train วัน 120–269 (cold start) · commit ก่อนเปิด test แล้ว (`72abff3`)

## Phase 1 — ข้อมูล · ✅
- `src/tp/sim.py` สร้าง m0 / m0.5 / m1 (seed 20261003) ครบชุดละ 5,589,024 events · ส่วนท้ายเขียนต่อโดยผู้ที่เห็น detector แล้วหลัง generator agent หยุดกลางทาง จึงไม่อ้าง blind implementation ทั้งไฟล์ (D47 / deviation 4)
- `tests/test_sim.py` ตรวจไฟล์จาก seed เดิมตรงกันทุกไบต์และแถวก่อน test เหมือนกันเมื่อเปลี่ยน mimicry · `data/SOURCES.md` บันทึกคำสั่ง, seed และ SHA-256 ของ source กับ source tables ทั้ง 15 ไฟล์
- เสร็จ: `src/tp/dataset.py` (switch view → replay ครั้งเดียว → ตาราง feature + คอลัมน์ประเมิน, `episode_events`, profile) · `check_contract()` หยุดเมื่อข้อมูลไม่ตรง contract · profile รายงานค่าเฉลี่ย seed-like ของรายการสุจริตรายช่วงวัน (cold start) · `tests/test_pipeline.py` ผ่าน รวม leak ที่ฝังไว้ต้องถูกจับ
- `tp.dataset` ผ่านทั้งสามชุด · m0 มี train 718,837, val 239,035, test 478,182 eligible intents · train/val/test มี 1,204/436/566 episodes และ 240/83/120 rings · hard negative ทุกกลุ่มมี ≥ 300 subject ดิบใน validation (ต่ำสุด 331; บางกลุ่มเหลือ < 300 หลังกรอง switch view)

## Phase 2 — baseline + โมเดล · ✅
- `src/tp/metrics.py` (threshold ถ่วง p, episode outcomes, bootstrap) · `src/tp/train.py` (arm 0, rule T2, LightGBM 1/2e/2/3, อ่านเฉพาะ train/val ด้วย parquet filter, เขียน manifest พร้อม ceiling flag และ G4 audit บน validation) · `tests/test_lab.py` ผ่าน
- เทรน m0 แล้ว: `artifacts/protocol_manifest.json` ตรึงโค้ด, source tables, ชุด mimicry, profile และโมเดล · validation เท่านั้น: arm 1 recall 57.1%, arm 2 62.1% ที่งบหลัก 20/10k (เป็นค่าที่ใช้เลือก threshold ยังไม่ใช่ผล test)
- manifest hash รวม `evaluate.py`, `make_report.py` และ `G0_DATA_CONTRACT.md` → แก้ไฟล์เหล่านี้หลัง train ต้อง train ใหม่ (ก่อนเปิด test) หรือบันทึก deviation (หลังเปิด)

## Phase 3 — ประเมิน · ✅ (เปิด test ครั้งเดียวแล้ว; เกณฑ์บางข้อไม่ผ่าน)
- `src/tp/evaluate.py` (ตรวจ hash, `--rehearse` บน validation, เปิด test ครั้งเดียว, `--rerun` บันทึก deviation อัตโนมัติ, H1/H1s–H5, placebo, holdout, variant, G7, alert บนบัญชี ring) · `scripts/make_report.py` → `reports/G0_LAB_REPORT.md` หรือ `--rehearsal` → `reports/G0_REHEARSAL_VAL.md`
- ลำดับ: train → `tp.evaluate ... --rehearse` + `make_report.py --rehearsal` ต้องผ่านครบ → commit → `tp.evaluate` (test) → `make_report.py` → commit ผล
- `tp.evaluate --rehearse` ตรวจ hash และความเหมือนของ train/val ข้ามชุด mimicry แล้วผ่าน · `scripts/make_report.py --rehearsal` สร้าง `reports/G0_REHEARSAL_VAL.md` พร้อม 48 unit tests ผ่าน · รายงาน validation ระบุว่า G2/G2b/G3 ยังไม่ผ่าน แต่ยังไม่ใช่ verdict บน test
- Pretest commit `72abff3` ตรึง `src/tp/demo.py` เพิ่มตาม protocol §7 (deviation 5) · เปิด test ครั้งเดียวหลัง commit และบันทึก `artifacts/test_results.json` · รายงาน `reports/G0_LAB_REPORT.md` สร้างแล้ว
- Test: H1 arm 2 เหนือ arm 1 +2.8 pp (95% CI -0.4 ถึง +6.4) และ H1s +2.4 pp (CI คร่อมศูนย์) จึงสรุปไม่ได้ทั้งคู่ · G2/G2b/G3 ไม่ผ่าน · G1/G7 ผ่าน · H5 ผ่านเฉพาะ simulator · ข้อมูลทั้งหมดเป็น synthetic learnability

## Phase 4 — demo · ✅ (replay 4 ฉากสำเร็จ)
- `src/tp/demo.py`: 4 ฉาก (A รายการจริงถัดไปของบัญชีปกติ · B/C ลำดับ §14.1 ต่างกันแค่ผู้โอนคืน · D hard negative ร้านค้าบุคคลชุดแรกใน test) บน history จริงใน simulator · ใช้โมเดล/threshold จาก manifest · ตรวจ parity กับตาราง batch · evidence log แบบ hash chain → `reports/demo/` · รันได้หลัง `tp.evaluate` เท่านั้น
- Replay สำเร็จ: A=NONE, B=HIGH, C=HIGH, D=NONE · ผลและ evidence log อยู่ใน `reports/demo/` · แก้ parity guard ของ demo หลังเปิด test ตาม deviation 6; manifest ยัง hash demo เวอร์ชันก่อนแก้ และไม่ได้รัน test ซ้ำ
- 30 ก.ย.: generator agent หยุดกลางทางเพราะ rate limit แล้ว resume พร้อม `G0_DATA_CONTRACT.md` (ตรวจแล้วว่าเป็น schema อย่างเดียว ไม่มีชื่อ feature/threshold)

## ข้อควรระวังสำหรับ session ถัดไป
- ผู้เขียน detector (session หลัก) อ่าน `features.py` / §6.2 แล้ว → ห้ามแก้ช่วงพารามิเตอร์ของ generator เอง ถ้าจำเป็นต้องแก้เพื่อขนาด/เวลา ให้บันทึกใน deviations
- `State.add` สแกน deque 90 วันของ payee ทุก event → ป้อนเฉพาะ P2P ของ switch view เข้า state เพื่อไม่ให้บัญชี merchant ที่มีรายการมากทำให้ replay เป็น O(n²)
- เปิด `tp.evaluate` บน test แล้วหนึ่งครั้ง; ห้ามรัน test ซ้ำโดยไม่บันทึก deviation ตาม protocol
- ห้ามใช้คำว่า "เงินล่อช่วยเตือน" ถ้า H1s ไม่ผ่าน · ห้ามใช้ G2/G2b เป็นหลักฐานภาระเตือนผิด
