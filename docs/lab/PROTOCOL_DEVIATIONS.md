# G-0 Protocol Deviations

> ทุกการแก้หลังอนุมัติ protocol (29 ก.ย. 2026) ต้องบันทึกที่นี่: แก้อะไร · เห็นผล test แล้วหรือยัง · กระทบ validity อย่างไร

ค่า SHA-256 ตอนอนุมัติ:

| ไฟล์ | SHA-256 |
|---|---|
| `G0_EXPERIMENT_PROTOCOL.md` | `2ce061e8ced379caf301d142620ade41942f95ff7bdff40276004fbfb240ee88` |
| `G0_SCENARIO_SPEC.md` | `6e2b33b910f941a7e4aabe2e431de55a747ab2026311d15d4dda0ebd90bb3fea` |
| `G0_GENERATOR_BRIEF.md` | `c5a7e0254547d6ebf6a59e613fe0c0aaeaef99ef234f353374981c419f820a95` |

## Deviation 2 — ลงทะเบียนเพิ่มก่อนมีข้อมูล (30 ก.ย. 2026)

ที่มา: ตรวจซ้ำ audit (`G0_AUDIT.md` ส่วน "ตรวจซ้ำ 30 ก.ย.") · ตอนลงทะเบียนยังไม่มีข้อมูล ยังไม่ train และยังไม่เห็นผล validation หรือ test · ทีมสั่งให้ทำ · กติกาทุกข้อถูกเขียนเป็นโค้ดแล้ว และ manifest จะ hash โค้ดนั้นตอน train

1. **Arm 2e (ablation):** LightGBM บน `GENERIC + TRUST_ESCALATION` (`escalation_vs_new_cluster`, `escalation_vs_established`, `ladder_steps`) ใช้ hyperparameter และวิธีเลือก threshold เดียวกับทุก arm · `TRUST` = `TRUST_SEED` 7 ตัว + `TRUST_ESCALATION` 3 ตัว (ไม่เปลี่ยน feature)
2. **H1s** = Δ recall before largest ของ arm 2 − arm 2e บน population เดียวกับ H1 ที่ budget หลัก ใช้เกณฑ์เดียวกับ H1 · H1 เดิมยังเป็นคำถามหลัก · อ้างว่า "เงินล่อ/เงินคืนช่วยเตือน" ได้เฉพาะเมื่อ H1s ผ่าน · ถ้า H1 ผ่านแต่ H1s ไม่ผ่าน ต้องเขียนว่าประโยชน์มาจาก baseline ยอดไต่
3. **Placebo ใหม่** = Δ arm 2 − arm 2e บน family D (CI > 0 = สัญญาณ artifact) · แบบเดิม (Δ arm 2 − arm 1 บน D) ใช้ไม่ได้ เพราะ feature ยอดไต่ 3 ตัวใน TRUST ช่วยจับ drain ที่ยอดไต่ได้โดยไม่ต้องมีเงินล่อ (ยืนยันด้วย `State` ของ repo) · ยังรายงาน Δ arm 2 − arm 1 บน D เป็นข้อมูลประกอบ
4. **Ceiling:** ถ้า recall before largest ของ arm 1 บน validation ที่ 20/10k ≥ 0.95 (บันทึกใน manifest ก่อนเปิด test) รายงานว่า H1 ที่งบนี้แยกความต่างได้น้อย · budget หลักยังเป็น 20/10k · 5/10k และ 1/10k ยังเป็นผลรอง ห้ามยกขึ้นเป็นผลหลักหลังเห็นผล
5. **งบจริงไม่เท่ากัน:** verdict ผ่านหรือไม่ผ่านของทุกคู่ arm ลดเป็น "สรุปไม่ได้ (งบจริงไม่เท่ากัน)" เมื่อ arm ที่ชนะมี FPR จริงบน split ที่ประเมินสูงกว่าอีก arm เกิน 0.2 × งบ
6. **G3:** รายงานจำนวน alert ดิบรายกลุ่ม · กลุ่มที่ alert ของ arm 2 + rule < 10 ติดป้าย "alert น้อยเกินเทียบ" (เกณฑ์ G3 เดิมไม่เปลี่ยน)
7. **G4 audit** (protocol เปิดไว้โดยไม่ได้นิยาม): คำนวณบน validation ตอน train และตรึงใน manifest ได้แก่ PR-AUC ของแต่ละ arm และ AP ของ feature เดี่ยว (ทิศที่ดีกว่า, missing อยู่ท้าย) · ถ้ามี feature เดี่ยวที่ AP ≥ 0.95 ต้องเขียนในรายงานว่า simulator แยก class ง่ายเกินจริง
8. **G2/G2b:** รายงานคู่กับ TPR และระบุว่าเทียบเท่ากับ TPR ≥ 0.42 / 0.48 เพราะ FPR ถูกตั้งให้ใช้งบพอดี · ไม่ใช้เป็นหลักฐานภาระเตือนผิด
9. **Data contract:** `G0_DATA_CONTRACT.md` (schema อย่างเดียว) เข้า manifest · generator agent อ่านได้เพิ่ม · `tp.dataset` หยุดเมื่อไม่ตรง · `tp.evaluate` หยุดเมื่อ population ที่ลงทะเบียนว่าง
10. **Rehearsal:** `tp.evaluate --rehearse` และ `make_report.py --rehearsal` บน validation ต้องผ่านครบก่อนเปิด test และต้องตรวจว่าชุด mimicry มีแถวก่อนวันที่ 330 เหมือน m0
11. **รายงานเพิ่ม:** alert บนรายการที่ payer เป็นบัญชี ring · ค่าเฉลี่ย seed-like ของรายการสุจริตรายช่วงวัน (ตรวจ cold start) · ข้อจำกัดเรื่อง hard negative 3 กลุ่มที่ตัดออก และ CI ที่ไม่รวมความแปรปรวนข้าม seed
12. **ลำดับคำสั่ง** (แทน protocol §7): sim m0/m0.5/m1 → dataset ทั้ง 3 ชุด → train → evaluate --rehearse + make_report --rehearsal → commit → evaluate → make_report → commit ผล
13. หัวไฟล์ `G0_SCENARIO_SPEC.md` ยังเขียน "ร่างรอทีมอนุมัติ" แต่ spec อนุมัติแล้ว 29 ก.ย. ตาม SHA-256 ข้างบน · ไม่แก้ไฟล์เพื่อรักษา hash
14. Bug fix: `tp.train` และ `tp.evaluate` resolve path ก่อนเรียก `relative_to` (ถ้าส่ง path แบบ relative จะ crash หลัง evaluate คำนวณผลเสร็จ)

## Deviation 3 — ไม่ fit แถว train วัน 90–119 (30 ก.ย. 2026)

ทีมสั่งให้ทำ · ตอนลงทะเบียนยังไม่มีข้อมูลและยังไม่ train

- เหตุผล: state ของ feature เริ่มว่างที่วัน 0 ทุกคู่จึง "ใหม่" ในช่วงแรก · seed-like ที่ติดในวัน 0–30 จึงค้างอยู่ใน window 90 วันจนถึงราววัน 120 · smoke test บนข้อมูลปลอมที่คู่ค้าคงที่พบว่าค่าเฉลี่ย seed-like ของรายการสุจริตในวัน 90–119 = 3.18 เทียบกับ 1.56 ในวัน 150–269 (ขนาดบน simulator จริงดูได้จาก profile)
- แก้: LightGBM ทุก arm fit เฉพาะแถว train วัน 120–269 (`FIT_START`) · วัน 90–119 ยังใช้เป็น history ของ feature · ring, episode, split, label cutoff และ validation ไม่เปลี่ยน · manifest บันทึกจำนวนแถวและ positive ที่ไม่ได้ fit
- ผล: [อนุมาน] train positive ลดลงราว 1/6 · artifact เดิมทำให้ arm 2 เสียเปรียบ การตัดออกจึงไม่ได้ออกแบบมาเพื่อช่วย H1 แต่ทำให้การกระจายของ train ตรงกับ val/test

| # | วันที่ | แก้อะไร | เห็นผล test แล้ว? | ผลต่อ validity |
|---|---|---|---|---|
| 1 | 29 ก.ย. 2026 | ก่อนเปิด test: เพิ่ม SHA-256 ของ source tables ทั้งหมด, ชุด mimicry ที่มีตอน train, dataset profile และ `scripts/make_report.py`; report หยุดเมื่อ unit tests ไม่ผ่านหรือ hash ไม่ตรง; บันทึกจำนวน validation positives ที่รู้ label ทัน cutoff; แสดง raw alerts ทั้งในประชากร TP/FP และ test ทั้งหมดพร้อมจำนวน holdout ที่ตัดออก | ไม่ (`artifacts/test_results.json` ยังไม่มี) | ปิดช่องเปลี่ยน input/รายงานหลัง freeze และเปิดเผยการจูนแบบย้อนหลัง; แก้ยอด alerts ในประชากรวิเคราะห์ให้เท่ากับ TP+FP โดยไม่เปลี่ยน score, threshold หรือเกณฑ์ผ่าน |
| 2 | 30 ก.ย. 2026 | ลงทะเบียนเพิ่มก่อนมีข้อมูล: arm 2e + H1s, placebo ใหม่, กติกา ceiling / งบจริง / G3 / G4, ถ้อยคำ G2, data contract, rehearsal บน validation, รายงานเพิ่ม, bug fix path (รายละเอียดใน Deviation 2 ข้างบน) | ไม่ (ยังไม่มีข้อมูล ยังไม่ train) | แยกผลของเงินล่อออกจากยอดไต่ได้ และปิดช่องเลือกเล่าผลหลังเห็นตัวเลข · H1, budget หลัก, split, arm เดิม และเกณฑ์ผ่านเดิมไม่เปลี่ยน |
| 3 | 30 ก.ย. 2026 | fit เฉพาะแถว train วัน 120–269 · วัน 90–119 เป็น history อย่างเดียว (cold start · รายละเอียดใน Deviation 3) | ไม่ (ยังไม่มีข้อมูล ยังไม่ train) | การกระจายของ train ตรงกับ val/test · train positive ลดลงราว 1/6 · split, H1 และเกณฑ์เดิมไม่เปลี่ยน |
| 4 | 30 ก.ย. 2026 | ผู้เขียนฝั่ง detector ทำ `src/tp/sim.py` ส่วนที่ค้างต่อจาก generator agent โดยยึดช่วงพารามิเตอร์และ scenario spec ที่ freeze แล้ว; แก้ให้ mimicry ใช้ RNG แยกเพื่อรักษาข้อมูลนอก episode และสร้าง m0/m0.5/m1 | ไม่ (ยังไม่ train หรือเปิดผล test) | scenario spec ยังเขียนแบบ detector-blind แต่ implementation ตอนจบไม่ blind เต็มที่ จึงต้องระบุข้อจำกัดนี้ในรายงาน; ห้ามอ้างว่า generator code ทั้งหมดเป็น independent blind implementation |
| 5 | 30 ก.ย. 2026 | หลังเห็น validation rehearsal แต่ก่อนเปิด test: เพิ่ม `src/tp/demo.py` ในรายการไฟล์ที่ manifest hash ตาม protocol §7 แล้ว train/rehearse ใหม่ | ไม่ | ตรึงไฟล์ `src/tp/*.py` ให้ครบ; ไม่เปลี่ยนข้อมูล, feature, arm, threshold rule หรือเกณฑ์ตัดสิน |
| 6 | 30 ก.ย. 2026 | หลังเปิด test: `tp.demo` หยุดเมื่อฉาก B/C มีแต่ event จำลองใหม่ ทำให้ชุด ID สำหรับตรวจ parity กับ batch ว่าง; เพิ่ม guard ให้ข้ามการอ่าน batch เฉพาะกรณีนี้ และระบุ deviation ในหน้า demo | ใช่ | ไม่แก้ source data, model, threshold หรือผล test; `src/tp/demo.py` หลังแก้ต่างจาก hash ใน pretest manifest จึงแสดงข้อจำกัดนี้ตรง ๆ และไม่รัน `tp.evaluate` ซ้ำ |
