# G-0 Lab — ตรวจความน่าเชื่อถือก่อนเปิด test

> 29 ก.ย. 2026 · ตรวจจาก protocol, scenario spec และโค้ดใน folder นี้ · ยังไม่มี `artifacts/test_results.json` ตอนตรวจ · ข้อค้นพบเป็นความเสี่ยงของการออกแบบและการนำผลไปอ้าง ไม่ใช่ผล performance

## จุดที่ต้องตรวจเข้ม

| ระดับ | ประเด็นและหลักฐาน | ผลต่อข้อสรุป | การจัดการ |
|---|---|---|---|
| สูง | `train.py` ใช้ `val.y_true` สำหรับ early stopping, เลือก rule และ threshold แต่ label ของ validation บางส่วนอาจมีผลหลัง cutoff วันที่ 330 (`G0_EXPERIMENT_PROTOCOL.md` §2) | ผล test ตอบคำถามแบบย้อนหลังได้ แต่ยังไม่พิสูจน์ว่าทีมจะเลือกโมเดลและ threshold เดียวกันได้ ณ วัน 330 | Manifest นับ positive ที่รู้ label ทัน cutoff; report ระบุข้อจำกัดนี้ หากจะอ้างการจูนแบบ prospective ต้องทำ sensitivity ที่ใช้เฉพาะ label ซึ่งมี ณ cutoff ก่อน แล้วบันทึก deviation |
| สูง | Family A ใน simulator ถูกสร้างจาก typology เงินล่อและยอดไต่ขึ้น ซึ่งเป็นสมมติฐานของฟีเจอร์ TRUST (`G0_SCENARIO_SPEC.md` §1.2; protocol §8) | H1 ที่ผ่านอาจสะท้อนความเข้ากันระหว่าง generator กับ detector | ตรวจ placebo, hard negatives, mimicry และ novel holdout ตาม protocol; ผลยังเป็น learnability จนกว่าจะตรวจบนพฤติกรรมจริงและ label ที่น่าเชื่อถือ |
| สูง | Arm 0 ไม่มี CFR mock; score ใช้รายการสำเร็จ P2P ข้ามธนาคารแทน intent ก่อนยืนยัน (protocol §2, §4) | ส่วนที่ชนะ arm 0 เป็นขอบบนของประโยชน์เหนือ control จริง; coverage และ false-warning burden ของ live flow ยังไม่ทราบ | รายงานข้อจำกัดทั้งสองข้างตารางผล และไม่อ้างว่าชนะ control ธนาคารจริง |
| กลาง | ก่อน audit manifest hash เพียง `features.parquet`, `episode_events.parquet`, `episodes.parquet` ของ m0; ไม่ตรึง source tables, dataset profile, mimicry หรือ report generator | แก้ input หรือวิธีนำเสนอหลัง freeze ได้โดยไม่ถูกตรวจ | แก้แล้ว: hash source tables, dataset profile และชุด mimicry ที่มีตอน train; evaluator ปฏิเสธชุดไม่ตรึง; report ตรวจ manifest และ unit tests |
| กลาง | ในตาราง intent เดิม `alerts` รวม positive ของ holdout แต่ `TP` ตัด holdout ออก ทำให้ `alerts` ไม่เท่ากับ `TP+FP` | ตัวเลขดิบในรายงานชวนให้เข้าใจว่ามีรายการที่จัดประเภทไม่ได้ | แก้แล้ว: แสดงทั้ง alerts ในประชากร TP/FP และ alerts ของ test ทั้งหมด พร้อมจำนวน holdout positive ที่ตัดออก |
| กลาง | Prevalence 1:5,000 และ 1:50,000 เป็นสมมติฐาน ไม่ใช่ base rate ของ eligible T2 ในไทย (protocol §4, v3.3 §8.2) | FP:TP และงบเตือนที่ถ่วงน้ำหนักเปลี่ยนมากเมื่อ base rate จริงต่างไป | แสดงทั้งสองสมมติฐานพร้อม TP/FP ดิบ; ต้องวัด base rate บนข้อมูล pilot ก่อนอ้าง burden จริง |
| กลาง | `features.py` เดิน state ตาม `ts`; late ingestion ยังอยู่นอก scope (protocol §9) | Point-in-time ที่ทดสอบครอบคลุมลำดับเวลาใน simulator แต่ยังไม่ครอบคลุม feed มาช้า | ระบุขอบเขตนี้ใน report; pilot ต้องแยก `ts` กับ `ingested_at` และทดสอบ availability ก่อนใช้จริง |

## เงื่อนไขก่อนใช้ผล test สื่อสารภายนอก

1. ตรวจ manifest, ผล unit tests, จำนวน train positives ที่ label มาไม่ทัน cutoff และ validation positives ที่รู้ทัน cutoff; ถ้า validation positive ที่ทัน cutoff น้อย ให้ย้ำว่าการจูนเป็นแบบย้อนหลัง
2. ตรวจว่าชุด m0/m0.5/m1 ถูกตรึงก่อน test และ generator sanity ผ่าน; ถ้าชุด mimicry ยังไม่พร้อม ให้รายงาน H4 ว่าไม่ได้ทำ
3. เมื่อ H1 ผ่าน ให้ดู placebo, hard negatives, holdout และจำนวน ring พร้อม CI ก่อนใช้คำว่า “ช่วยได้”; H1 ที่ไม่ผ่านหรือ CI คร่อมศูนย์ต้องรายงานตรงตามนั้น
4. ทุกตัวเลขจาก simulator ใช้คำว่า **learnability บนข้อมูลจำลอง**; ข้อมูล pilot จริงและการยืนยัน field/สิทธิข้อมูลเป็นขั้นแยกก่อนกล่าวถึงการใช้งานจริง

## ตรวจซ้ำ 30 ก.ย. 2026 (ก่อนเขียน sim.py ต่อ)

ตรวจสิ่งที่แก้ไปแล้ว: hash ของ protocol, spec และ brief ตรงกับค่าตอนอนุมัติ · unit tests ผ่านทั้งชุด · evaluate ปฏิเสธไฟล์ที่เปลี่ยน · report หยุดเมื่อ test ไม่ผ่าน · alerts = TP + FP

ปรับระดับความเสี่ยง:
- label ของ validation ที่มาช้า: **ต่ำ** สำหรับ H1 (เดิมให้สูง) · กระทบทุก arm เท่ากัน, threshold ถูกกำหนดเกือบทั้งหมดจาก FPR ของ negative (TPR·p ใช้ได้ไม่เกิน 10% ของงบ 20/10k) และระยะแจ้งความใน spec สุ่มแยกจาก feature · การเปิดเผยจำนวนในรายงานพอแล้ว
- arm 0, intent และ switch view: เป็นเรื่องคุมถ้อยคำ ไม่ได้ทำให้ผล H1 ผิด

ข้อค้นพบใหม่:

| ระดับ | ประเด็นและหลักฐาน | สถานะ |
|---|---|---|
| สูง | Placebo เดิมใช้ตรวจ artifact ไม่ได้ และ H1 แยกไม่ออกว่าได้จากเงินล่อหรือจากยอดไต่ · TRUST มี feature ยอดไต่ 3 ตัวที่ไม่ต้องมีเงินล่อ · `State` กับ drain ที่ไม่ได้เงินคืนเลยให้ `escalation_vs_new_cluster` 1.58 และ `ladder_steps` 2 · family D ใน spec ไต่ยอดไปบัญชีใหม่ | แก้แล้ว (deviation 2): arm 2e, H1s, placebo = arm 2 − arm 2e บน D |
| สูง | G2/G2b คำนวณได้จาก TPR เพราะ FPR ถูกตั้งตามงบ: FP:TP ≈ B/(p·TPR) − 1 · ทดสอบด้วย `threshold_at_budget` 8 กรณี ต่างจากสูตรไม่เกิน 0.1 · G2 ⟺ TPR ≥ 0.42, G2b ⟺ TPR ≥ 0.48 · ที่งบ 1/10k TPR ถูกจำกัดไว้ ≤ 50% | แก้ถ้อยคำในรายงานแล้ว · ภาระเตือนผิดจริงยังต้องวัดบนธุรกรรมจริง (M2) |
| สูง | ข้อมูลจริงชุดแรกที่ evaluate จะได้เจอคือ test · brief บอกให้ทำตาราง HN แบบ `event_ids` แต่ pipeline ต้องการ `hn_events` + `step` · ไม่มีเอกสารตรึงชื่อ family, variant, split หรือชนิดของเวลา · `populations()` ทิ้งกลุ่มที่ว่างไปเงียบ ๆ | แก้แล้ว: `G0_DATA_CONTRACT.md` + `check_contract()` · population ที่ว่างทำให้หยุด · rehearsal บน validation |
| สูง | การ freeze ตรวจสอบจากภายนอกไม่ได้ · `src/`, `tests/`, `docs/` ยังไม่ถูก track · manifest สร้างใหม่ได้ · guard เช็กแค่ว่ามีไฟล์หรือไม่ | เปิด: ต้อง commit ก่อน `tp.evaluate` (รอทีมสั่ง) |
| กลาง | กติกาตัดสินที่ยังไม่ได้เขียน: ceiling, G4 audit, งบจริงไม่เท่ากัน, G3 ที่ alert น้อย | แก้แล้ว: เขียนเป็นโค้ดและตรึงใน deviation 2 |
| กลาง | Bug: `tp.train`/`tp.evaluate` crash เมื่อส่ง path แบบ relative (ตัวอย่างคำสั่งใน PROGRESS ใช้แบบนี้) และใน evaluate crash หลังคำนวณผลเสร็จ | แก้แล้ว |
| กลาง | Cold start: state เริ่มว่างที่วัน 0 · smoke test ที่คู่ค้าคงที่พบว่าค่าเฉลี่ย seed-like ของรายการสุจริตช่วงวัน 90–119 สูงเป็น 2 เท่าของช่วงวัน 150–269 (3.18 เทียบ 1.56) · ทำให้ arm 2 เสียเปรียบและกระจายของ train ต่างจาก test | แก้แล้ว (deviation 3 / D46): fit เฉพาะวัน 120–269 · profile ยังรายงานค่ารายช่วงไว้ตรวจ |
| ต่ำ | รายงานไม่ได้พูดถึง hard negative 3 กลุ่มที่ตัด · บัญชีม้าถูกตัดจากประชากร T2 · CI ไม่รวมความแปรปรวนข้าม seed | แก้แล้ว: ข้อจำกัดใน report และนับ alert บนบัญชี ring · ยังไม่ทำการรันซ้ำหลาย seed |

Smoke test: ใช้ข้อมูลปลอมที่ตรงตาม contract ใน scratchpad (ไม่ใช่ส่วนของการทดลอง) รันผ่านครบ ได้แก่ dataset ×3 → train → rehearsal → report → test → report และ guard ปฏิเสธการรันซ้ำที่ไม่ระบุเหตุผล
