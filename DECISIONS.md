# DECISIONS.md — Trust Provenance Final Prototype

> สถานะ: ✅ ล็อกแล้ว · 🟡 เสนอ รอทีมยืนยัน · ❓ ยังเปิด
> เพิ่มข้อใหม่ต่อท้าย ห้ามแก้ประวัติ ถ้าเปลี่ยนใจให้เขียนข้อใหม่ที่อ้างถึงข้อเดิม

## Product

**D1 🟡 Product คือ signal service ที่ NITMX host**
- ลูกค้าคือ fraud engine ของธนาคารต้นทาง ไม่ใช่ผู้ใช้แอป
- เราส่ง score band + reason code + case bundle · ธนาคารเป็นคนตัดสินและเป็นเจ้าของหน้าจอพักรายการ
- ธนาคารของเหยื่อเห็นเงินคืน seed เองอยู่แล้ว (เป็นธนาคารผู้รับของรายการนั้น) จุดขายของ NITMX จึงเป็นสิ่งที่ธนาคารเดียวไม่เห็น:
  - ปลายทางรับเงินจากผู้โอนหน้าใหม่กี่คน จากกี่ธนาคาร
  - บัญชีที่คืน seed กับบัญชีปลายทางอยู่เครือข่ายเดียวกันไหม
  - เคสจากทุกธนาคารรวมกันพอเทรนโมเดลได้
  - เส้นทางเงินข้ามธนาคารสำหรับ case bundle

**D2 🟡 หน่วยทำนาย = รายการโอนออก 1 รายการ ก่อนผู้ใช้กดยืนยัน**

**D3 🟡 Episode = ธุรกรรมเข้าและออกของผู้โอน กับคู่บัญชีที่เจอกันครั้งแรกภายใน 30 วัน (rolling)**
- ไม่ต้องรู้ว่าบัญชีไหนอยู่แก๊งเดียวกัน: เงินคืนจากบัญชี A แล้วโอนก้อนใหญ่ไปบัญชี B ก็ยังจับได้
- ใช้นิยามเดียวกันทั้งตอนคำนวณ feature และทำ case bundle

**D4 ❓ Scope ของโมเดล**
- ทางเลือก: จับเฉพาะ seed-payout ladder (~15% ของเคส) หรือให้คะแนน APP scam ทั่วไปโดยมี seed-payout เป็น reason code เด่น
- ข้อเสนอ: แบบหลัง

## Data

**D5 🟡 Schema กลาง**

```
transactions: event_id, ts, payer_token, payee_token, amount_thb, txn_type, payer_type, is_synthetic
labels:       event_id, label, label_source, label_effective_ts, scenario, episode_id
```

- ไม่มีคอลัมน์ direction: เงินเข้าของบัญชี X คือแถวที่ `payee_token = X`
- `txn_type`: P2P / BILL / MERCHANT / BULK / GOV · feature เรื่องเงินคืนนับเฉพาะ P2P (กันเงินเยียวยา เงินเดือน refund)
- `payer_type`: PERSON / JURISTIC
- `label_source`: INJECTED / CASE / CFR_WEAK

**D6 ❓ ข้อมูลจริงที่ใช้จำลอง**
- ข้อเสนอ: ledger ธนาคารจริงสาธารณะ Berka (PKDD'99) เป็นพฤติกรรมปกติ เพราะมีโอนเข้าและออกพร้อมบัญชีคู่ค้า
- แล้วฉีด scam ที่ calibrate จากเคส AOC 1441 191 เคส (ยอด จำนวนครั้ง ช่วงเวลา สัดส่วนเงินคืน)

**D7 🟡 Label**
- ตอนจำลอง: label มาจากรายการที่ฉีดเข้าไป (`INJECTED`)
- ข้อมูลจริงภายหลัง:
  - แข็ง: เคสที่ผูกบัญชีเหยื่อกับรายการโอนได้ (`CASE`)
  - อ่อน: ผู้โอนหน้าใหม่โอนเข้าบัญชีที่ CFR flag ภายใน 30 วันหลังโอน โดยตัดกรณีผู้โอนเป็นม้าเอง (`CFR_WEAK`)
  - negative: ผ่านไป 60 วันแล้วไม่เชื่อมกับบัญชีที่ถูก flag
- ขอข้อมูลจาก NITMX อย่างน้อย 6 เดือน (ประวัติ 90 วันสำหรับ feature + รอ label 60 วัน)

## Model

**D8 🟡 Rules + LightGBM + calibration**
- rules: สร้าง reason code และใช้ตอนยังไม่มีประวัติ
- LightGBM: ใส่ monotone constraint ให้ feature ที่ทิศทางชัด เช่น ยอดเทียบ baseline ตัวเอง
- isotonic calibration → band LOW / ELEVATED / HIGH
- `pred_contrib` → reason code catalog ชุดเดียว → ข้อความ template ภาษาไทย

**D9 🟡 การทดลองหลัก**
- (ก) feature ฝั่งปลายทางอย่างเดียว (แนว PromptPlus) เทียบกับ (ข) ก + feature trust formation
- วัด lift ของส่วนที่เพิ่ม = คำตอบเชิงตัวเลขของ "ต่างจาก PromptPlus ยังไง"

## Metrics

**D10 🟡 ลำดับชั้นของ metric**
- North star: เงินที่กันได้ก่อนออกจากบัญชี ภายใต้ alert budget
- Offline: recall@budget · เตือนที่การโอนครั้งที่เท่าไร · PR-AUC · calibration
- Guardrail: เตือนผิดต่อการจับถูก 1 ครั้ง (เป้า ≤ 5:1 ระดับ pilot ของ Pay.UK) · FP แยกกลุ่ม · p99 latency
- ประมาณการ prevalence (สมมติฐาน ต้องวัดจริง): ~1 ใน 50,000 ของทุกรายการ · ~1 ใน 5,000 ถ้าสโคร์เฉพาะรายการที่ไปหาคู่ใหม่

## Serving

**D11 🟡 สอง phase**
- Phase 1 batch watchlist: คำนวณ 3 รอบ/วันตามรอบ CFR แล้วส่งคู่บัญชีเสี่ยงให้ธนาคารของผู้โอน
- Phase 2 real-time API:
  - `POST /v1/risk-check` (< 10 ms, fail-open)
  - `POST /v1/feedback`
  - `GET /v1/episodes/{id}`
- `evidence` ใน response เป็นข้อมูลที่ผู้โอนรู้อยู่แล้วเท่านั้น
- ตัดสินว่าต้อง real-time ไหมจากข้อมูล: มัธยฐานเวลาจากได้เงินคืน seed → โอนก้อนถัดไป

## Timeline

**D12 ❓ Horizon: demo วัน Final 3 ต.ค. หรือ PoC กับ NITMX หลัง final**


## M0 — ปรับตาม Product Design v2.1 (27 ก.ย. 2026)

> ที่มา: `product_design/trust-provenance-product-design-v2.1.md` (หลังปรึกษา mentor NITMX วันที่ 27 ก.ย.) · อ้าง § ของเอกสารนั้น

**D13 ✅ ใช้ Product Design v2.1 เป็นแหล่งอ้างอิงหลักด้าน product**
- ถ้า DECISIONS.md ขัดกับ v2.1 ให้ถือ v2.1 แล้วเขียนข้อใหม่ที่นี่
- ถ้า v2.1 ออกเวอร์ชันใหม่ ให้เทียบแล้วเพิ่มข้อใหม่อีกรอบ

**D14 ✅ Architecture = Phase 0 + Layer A + Layer B (ใช้แทน D1)** · v2.1 §4
- Phase 0 CFR-at-Lookup: เตือนบัญชีที่ถูกแจ้งไว้แล้ว ณ ขั้น Lookup
- Layer A (bank-local): ธนาคารรัน engine บนประวัติลูกค้าตัวเอง ครอบคลุม on-us และข้อมูลไม่ออกนอกธนาคาร
- Layer B (NITMX): ตัวนับข้ามธนาคารที่หมดอายุเอง ไม่เก็บธุรกรรมดิบ + CFR · เป็นความสามารถใหม่ที่ยังต้องยืนยันกับ NITMX
- ลูกค้ายังเป็นธนาคาร · ธนาคารเป็นผู้ตัดสินใจและเป็นเจ้าของหน้าจอ
- จุดขายเฉพาะของ NITMX ใน D1 (fan-in ข้ามธนาคาร, บัญชีที่จ่าย seed เชื่อมกับปลายทาง) ย้ายไปอยู่ใน Layer B

**D15 ✅ Scope = trust-formation ในความสัมพันธ์ที่มีประวัติ (ปิด D4 และใช้ทางเลือกที่แคบกว่าข้อเสนอเดิม)** · v2.1 §3, §4 Out-of-scope
- ในขอบเขต: เงินคืนก้อนเล็ก → ยอดโอนไต่ขึ้น (รวมเงินคืนที่มาจากคนละบัญชีกับบัญชีที่รับเงิน), เร่งความถี่, ซอยยอด, ได้เงินเล็กจากหลายบัญชีใหม่
- นอกขอบเขต: one-shot fraud ที่ไม่มีประวัติความสัมพันธ์ (ตอบ `INSUFFICIENT_HISTORY`) · fraud ประเภทอื่น (typology อีก 7 แบบอยู่ใน roadmap Phase 3)
- วิธีพูดตัวเลข: "ในชุดตัวอย่าง 185 เคส พบอย่างน้อย 27 เคส" ห้ามพูดเป็นสัดส่วนของประชากร (เช่น ~15% ใน D4)

**D16 ✅ Output และการกระทำ (ใช้แทน band ใน D8 · ไม่มีการพักรายการ)** · v2.1 §10, Appendix A
- `status`: `OK | INSUFFICIENT_HISTORY | TIMEOUT`
- `signal_level`: `NONE | ELEVATED | HIGH` (ใช้แทน LOW / ELEVATED / HIGH) · ไม่แสดงเป็น %
- `recommended_action`: `NONE | WARN | WARN_WITH_DELAY` (หน่วงปุ่ม 30 วินาที) · **ไม่มี `BLOCK` และไม่พักรายการใน MVP**
- `NONE` ≠ ปลอดภัย · `INSUFFICIENT_HISTORY` ≠ ความเสี่ยงต่ำ · ห้ามใช้สีเขียว
- reason code 3 อันดับจาก `pred_contrib` ตาม catalog ใน v2.1 Appendix B (TP01–TP05 = Layer A, TP10–TP12 = Layer B)
- ยังใช้ LightGBM + isotonic calibration ตาม D8 เพื่อตั้ง threshold ของแต่ละ level

**D17 ✅ Label policy (ใช้แก้ D7)** · v2.1 §6, §11
- positive = เคสที่ยืนยันแล้วเท่านั้น (CASE หรือ INJECTED ตอนจำลอง) · prediction ≠ label
- `CFR_WEAK` และสถานะบัญชีต้องสงสัยใช้เป็น **feature ที่ไม่แน่นอน** หรือส่งเข้าคิว review ไม่ใช้เป็น label สำหรับเทรน
- บัญชีที่ถูกถอดสถานะหลังตรวจ KYC = hard negative
- field `label_effective_ts` ตาม D5 ยังคงใช้ · ค่าและ source ของ label สรุปใน M1

**D18 ✅ การทดลองหลัก = Rule vs GBDT(A) vs GBDT(A+B) (ใช้แทน D9)** · v2.1 §8
- ablation A → A+B คือคำตอบเชิงตัวเลขของ "context ข้ามธนาคารของ NITMX เพิ่มอะไร"
- split: temporal holdout + ring separation (เครือข่ายเดียวกันไม่อยู่ทั้งใน train และ test) + novel-variant holdout
- prefix evaluation: ให้คะแนนทุกรายการตามลำดับเวลา โดย `feature_time < prediction_time`
- วัดเพิ่ม: เตือนผิดบน hard negative (ครอบครัว, แชร์บิล, วงแชร์, ร้านค้าคืนเงิน, คืนเงินยืม) · sensitivity เมื่อ mimicry เพิ่มจาก 0 → 1
- gate: ถ้า ML ไม่ชนะ rule ที่ alert budget เดียวกัน → ใช้ rule

**D19 ✅ Metric (ใช้แก้ north star ใน D10)** · v2.1 §7
- north star: **มูลค่า (บาท) ที่ถูก flag ก่อนสูญเสีย** ภายใต้ alert budget (เปลี่ยนจาก "เงินที่กันได้" เพราะไม่มีการพักรายการ)
- early detection: recall before largest transfer · lead time (จำนวนรายการ / ชั่วโมง ก่อนก้อนใหญ่)
- customer impact: false-warning rate บนความสัมพันธ์ปกติ · alerts / 10k รายการ
- ไม่ใช้ accuracy · guardrail เตือนผิดต่อการจับถูก ≤ 5:1 และ prevalence ใน D10 ยังใช้อยู่

**D20 ✅ Horizon = offline PoC + demo สำหรับวัน Final 3 ต.ค. (ปิด D12)** · v2.1 §12, Appendix A
- replay บนข้อมูลจริงสาธารณะ + scam ที่ฉีดเข้าไป · ผลทุกตัวเลขเป็น learnability ไม่ใช่ production accuracy
- demo 3 ฉาก: เหยื่อ (WARN_WITH_DELAY) · คนปกติคืนค่าข้าว (NONE) · กราฟเส้นทางเงินข้ามธนาคาร
- PoC บนข้อมูลจริงกับ NITMX / ธนาคาร = roadmap Phase 0–1 หลัง final

**D21 ✅ Serving (ใช้แก้ D11)** · v2.1 §10
- ธนาคารเรียก Risk API หลัง Lookup ก่อนผู้ใช้ยืนยัน · side-channel · timeout เป้า ~50 ms → หมดเวลาใช้ flow เดิม (fail-open)
- state ความสัมพันธ์ precompute จาก transaction stream · ตอน request แค่ scoring
- batch ใช้สำหรับ backfill, retrain, drift (PSI) และรายงาน alert รายสัปดาห์ · ตัด batch watchlist 3 รอบ/วันของ D11 ออก
- log ทุก response: `request_id, model_version, reason_codes, timestamp`

**D22 🟡 Problem statement และเกณฑ์ผ่านของ PoC (เขียนก่อนเห็นผล · ผลลัพธ์ของ M0)**

Problem statement
> ในกลลวงลงทุน มิจฉาชีพคืนเงินก้อนเล็กเพื่อสร้างความไว้ใจแล้วเร่งให้โอนก้อนใหญ่ ณ วันที่โอนก้อนใหญ่ บัญชีปลายทางอาจยังไม่ถูกแจ้ง และเหยื่อยืนยันเอง control ระดับบัญชีจึงไม่เห็น
> เราจะให้คะแนนรายการโอนออกก่อนผู้ใช้กดยืนยัน จาก trajectory ของความสัมพันธ์ผู้โอน ↔ คู่บัญชี แล้วส่ง signal level + reason code ให้ธนาคารเตือนหรือหน่วงปุ่ม **ก่อน** การโอนที่ใหญ่ที่สุดของ episode

ประชากรที่ให้คะแนน: รายการโอนออก P2P ไปยังคู่บัญชีที่อยู่ใน episode (D3) · ประเมินที่ prevalence 1:5,000 ของรายการที่ให้คะแนน (ปรับน้ำหนัก negative) และรายงานที่ 1:50,000 ประกอบ

Operating point: **alert budget = 5 ต่อ 10,000 รายการที่ให้คะแนน**
- เหตุผล: ที่ 1:5,000 มีรายการ scam 2 รายการต่อ 10,000 · budget 5 จึงทำ FP:TP ≤ 5:1 ได้เมื่อจับได้ ≥ 42% ของรายการ scam · ถ้าใช้ budget 10 ต่อให้จับได้ครบ FP:TP ก็ยังเป็น 4:1

| # | เกณฑ์ | ผ่านเมื่อ | ประเภท |
|---|---|---|---|
| G1 | recall before largest transfer (ระดับ episode) | โมเดลที่เลือก > rule baseline ที่ budget เดียวกัน และ bootstrap 95% CI ของผลต่าง (resample episode) ไม่คร่อม 0 | gate หลัก · ไม่ผ่าน → ใช้ rule |
| G2 | เตือนผิดต่อการจับถูก 1 ครั้ง (ระดับรายการ) ที่ 1:5,000 | ≤ 5:1 | guardrail |
| G3 | false-warning rate บน hard negative | ≤ rule baseline | guardrail |
| G4 | ตรวจ leakage | ไม่มี feature ใช้เหตุการณ์ ≥ t (มี unit test) · PR-AUC ต้อง < 0.99 ถ้าสูงกว่านี้ให้ถือว่ารั่วหรือ injection ง่ายเกินไป แล้วกลับไป M3/M4 | gate |
| G5 | p99 latency ของ scoring 1 รายการ (feature precompute แล้ว) บนเครื่อง dev | < 50 ms | gate |
| G6 | demo 3 ฉากรันจาก output ของ pipeline จริง ไม่ hardcode | ครบ 3 ฉาก | gate สำหรับวัน Final |

รายงานประกอบ (ไม่ใช่ gate): lift ของ A → A+B · ผลบน novel variant · เส้น mimicry 0 → 1 · lead time · มูลค่าที่ถูก flag ก่อนสูญเสีย · calibration curve
- เปลี่ยนตัวเลขในตารางนี้ได้เฉพาะก่อนเริ่ม M5 และต้องเขียนเป็นข้อใหม่พร้อมเหตุผล

**D23 🟡 แยกเกณฑ์เตือนผิดตาม action + เพิ่ม adversarial gate (ใช้แก้ D22)** · ที่มา: `references/compass-lab-blueprint.md`
- คำเตือนเฉย ๆ รบกวนลูกค้าน้อยกว่าการหน่วงปุ่ม จึงยอมให้เตือนผิดได้มากกว่า

| # | เกณฑ์ | ผ่านเมื่อ | ประเภท |
|---|---|---|---|
| G2 (แก้) | FP:TP ของ `HIGH` / `WARN_WITH_DELAY` ที่ 1:5,000 · budget 5 ต่อ 10,000 | ≤ 5:1 (เป้า pilot ของ Pay.UK ตาม D10 · รายงานอ้างอิงเสนอ 3:1) | guardrail |
| G2b | FP:TP ของ `ELEVATED` + `HIGH` รวมกัน · budget 20 ต่อ 10,000 | ≤ 20:1 (ต้องจับได้ ≥ 48% ของรายการ scam) | guardrail |
| G7 | recall before largest transfer บนชุดที่คนร้ายปรับตัว (seed จากหลายบัญชี, ยืดเวลา, mimicry 0.5) เทียบกับชุดปกติ | ลดลงไม่เกิน 30% (relative) | guardrail |

- รายงานผลที่ budget 1 ต่อ 10,000 ด้วย เพื่อเทียบกับตัวเลขที่ใช้ในงานอื่น

## M0 — ปรับตาม Product Design v3 (28 ก.ย. 2026)

> ที่มา: Product Design v3.1.0 ณ เวลาตัดสินใจ · ฉบับประวัติ v3.2 ที่เก็บ changelog ไว้ใน `product_design/trust-provenance-product-design-v3.2.md` · อ้าง § ของฉบับนั้น

**D24 ✅ ใช้ Product Design v3 แทน v2.1 เป็นแหล่งอ้างอิงหลัก (แก้ D13)**
- กติกาเดิมของ D13 ยังใช้: ถ้าขัดกันให้ยึด v3 แล้วเขียนข้อใหม่ที่นี่
- เก็บ v2.1 ไว้เป็นประวัติ ไม่แก้

**D25 🟡 Touchpoint 3 จุด (แก้ D2, D14)** · v3 §2, §4, §11
- T1 เงินล่อเข้า: หน่วยทำนาย = รายการเงินเข้า P2P 1 รายการ · async ไม่บล็อกการเครดิต · `recommended_action`: `NONE | NOTIFY` · จำกัด 1 ครั้งต่อความสัมพันธ์
- T2 ก่อนยืนยันโอน: หน่วยและ output เดิมตาม D2, D16
- T3 seeder lead: หน่วย = บัญชีผู้จ่ายต่อหน้าต่าง 7/14 วัน · รันที่ธนาคารของผู้จ่าย · ลูกค้าไม่เห็น
- seeder fan-out ย้ายจาก Layer B (`TP11`) มา Layer A (`TP30`) เพราะธนาคารของผู้จ่ายเห็นเงินออกของลูกค้าตัวเองครบทุกธนาคารปลายทาง → feature หลักไม่ต้องมี data sharing ใหม่
- Layer B เหลือเป็นส่วนเสริม จำกัดเฉพาะบัญชีที่มีสัญญาณแล้ว ไม่ทำจนกว่าจะได้รับความเห็นชอบ + DPIA
- "เพิ่งรู้จัก" ใช้นิยาม episode ของ D3 (≤ 30 วัน) ทั้ง T1 และ T2 · เงินล่อจากบัญชีเดียวกับบัญชีรับหรือคนละบัญชี ต้องจับได้ทั้งคู่
- ให้คะแนนเฉพาะ P2P จากบัญชีบุคคล (`txn_type`, `payer_type` ตาม D5)

**D26 🟡 Lead → CFR และ Evidence Log (ต่อจาก D17, D21)** · v3 §8, §13
- lead ≠ รายงาน: เข้า CFR ได้หลัง Fraud Ops review และบันทึกเหตุผลแล้วเท่านั้น · lead ที่ปิดว่าไม่ใช่ = hard negative ของ T3
- label เพิ่ม `label_unit`: `pair_episode` (T1/T2) / `payer_account` (T3)
- Evidence Log ขยาย log ของ D21 ด้วย `touchpoint, copy_version, delay_seconds, user_action, policy_version, latency_ms, fail_open, review_outcome` + hash chain
- เรียกว่า tamper-evident ไม่ใช่ "แก้ไม่ได้" · production ต้องเก็บ hash ล่าสุดไว้นอกระบบเป็นรอบ ๆ · demo ใช้ append-only (SQLite / JSONL)
- ห้ามเคลมว่า log ทำให้ธนาคารพ้นความรับผิด

**D27 🟡 ขอบเขตโมเดลและเกณฑ์ของ T1/T3 (เพิ่มจาก D18, D22, D23 · เขียนก่อนเห็นผล)** · v3 §3, §10, §11
- ใน MVP ใช้ GBDT กับ T2 เท่านั้น · T1 และ T3 เป็น rule จนกว่าจะมี label จาก shadow / lead review
- ไม่ใช้ "เคยถูกเตือนที่ T1" เป็น feature ของ T2 (ปรับ threshold ของ T1 แล้ว distribution ของ T2 จะเปลี่ยนตาม) · ใช้ `profit_like_inbound_count` แทน · ข้อมูลว่าเคยเตือนที่ T1 ใช้ในข้อความเตือนเท่านั้น
- "T1 เตือนก่อน T2" จริงโดยนิยาม และการเพิ่ม T1 ทำให้เตือนเร็วขึ้นได้อย่างเดียว → ต้องเทียบที่จำนวนการเตือนรวมเท่ากัน

| # | เกณฑ์ | ผ่านเมื่อ | ประเภท |
|---|---|---|---|
| G8 | exposure at first alert (median ต่อ episode) ของ v3 (T1 + T2) เทียบกับ v2.1 ที่ใช้งบเตือนทั้งหมดกับ T2 · ที่จำนวนการเตือนถึงผู้ใช้รวมเท่ากัน (ต่อ 1,000 ผู้ใช้ต่อเดือน) | v3 ต่ำกว่า และ bootstrap 95% CI ของผลต่าง (resample episode) ไม่คร่อม 0 | gate ของ T1 · ไม่ผ่าน → T1 ย้ายไป roadmap |
| G9 | FP:TP ของ T1 ที่ prevalence สมมติ 1:5,000 ของเงินเข้า P2P ที่ให้คะแนน · budget 20 ต่อ 10,000 | ≤ 20:1 (ระดับเดียวกับ G2b เพราะเป็นการแจ้งเตือนแบบนุ่ม) | guardrail |

- T3: รายงาน recall ของ seeder บน ring ที่แยกไว้ และ lead ผิดบน hard negative ฝั่งผู้จ่าย · ยังไม่ตั้งเป็น gate จนกว่าจะรู้กำลัง review จริง
- "เหยื่อรายถัดไป" ต้องจำลองดีเลย์รอบส่งข้อมูล CFR (3 รอบ/วัน)
- G6 เปลี่ยนเป็น demo 4 ฉาก (T1 → T2 → T3 → Evidence + ท้าวแชร์) และยังต้องรันจาก output ของ pipeline จริง

**D28 🟡 ตัวเลขเคส AOC ที่ใช้บนเวที (แก้วิธีพูดใน D15)** · v3 §7
- ใช้ชุด ch2 ที่ตรวจซ้ำแล้ว: 191 เคส / 25 เอกสาร / 131,966,621 บาท · seed-payout ladder (`A_SEED_PAYOUT_LADDER`) 14 เคส เป็นหลอกลงทุน 10 เคส
- วิธีพูด: "ในชุดตัวอย่าง 191 เคส พบ 14 เคส" · ห้ามใช้ "อย่างน้อย 27 เคส" ของ v2.1 จนกว่าจะหาที่มาได้ (มาจากชุดเดิม 185 เคส และเท่ากับจำนวนเคส `FINANCIAL_INVESTMENT` ในชุด ch2 พอดี)
- เคสไม่มีวันเวลาระดับเหตุการณ์ (มีระยะเวลาระบุในคำบรรยายเพียง 2 จาก 14 เคส) → lead time วัดจาก simulator เท่านั้น

**D29 🟡 เป็น feature บน PromptPay ที่ NITMX เป็น operator (แก้ D25 เรื่องที่รัน · v3.2)** · v3 §4, §5
- T1/T2/T3 คำนวณที่ NITMX จากตัวนับของรายการที่ผ่าน switch (ข้ามธนาคาร) · ไม่เก็บธุรกรรมดิบ ตัวนับหมดอายุเอง
- ธนาคารยิง Risk API คู่ขนานกับ Lookup ไม่แก้ message ของ PromptPay · fail-open · ธนาคารตัดสินว่าจะเตือน/หน่วง · ธนาคารจ่ายค่าบริการ · ธปท. กำกับ
- T3: NITMX สร้าง lead → ธนาคารเจ้าของบัญชี review → CFR (D26 ยังใช้)
- Bank module (เดิม Layer A) = ส่วนเสริมสำหรับ on-us + แผนสำรองถ้าไม่ได้รับความเห็นชอบ
- ความเสี่ยงหลัก: ฐานกฎหมายของตัวนับทุกบัญชีที่ NITMX (อ้างประกาศ 57/2568 ถ้าครอบคลุมผู้ให้บริการระบบการชำระเงิน ต้องตรวจ · อ้าง ม.4 ไม่ได้) และความสามารถทำ streaming counter จาก switch
- ผลต่อ simulation: replay ต้องมี bank code ทั้งสองฝั่ง และตัดรายการ on-us ออกจากมุมมองของ NITMX (รายงานผลแยก on-us เป็นจุดบอด)

---

## ข้อเท็จจริงที่ใช้บ่อย

| ข้อเท็จจริง | แหล่ง |
|---|---|
| PromptPay ~81 ล้านรายการ/วัน (ก.ค. 2026) · วันสูงสุด 107.44 ล้าน | สรุป mentor (ข้อมูล ธปท.) |
| ส่วนของ PromptPay ใช้ < 100 ms ต่อรายการ · รองรับ 8,000+ TPS · สมาชิก 37+ ราย | สไลด์ NITMX 4 ก.ย. 2026 |
| CFR ส่ง label เป็น batch 3 รอบ/วัน (11:00 / 15:00 / 19:00) | architecture v1.1 C10 |
| เคส AOC 1441: 191 เคส · 131,966,621 บาท · median 46,400 บาท | ch2 audit |
| seed-payout ladder: 14 จาก 191 เคส (หลอกลงทุน 10) · ไม่มีวันเวลาระดับเหตุการณ์ | ch2 audit (`aoc_cases.csv` คอลัมน์ `weak_archetype`) |
| Authorized scam Q4/2568: 39,039 กรณี / 5,442 ล้านบาท · Q2/2569 ~1.8 พันล้านบาท | ธปท. |
| ประกาศ ธปท. 57/2568 (Digital Fraud Management) ใช้กับ NITMX · เอกสารแนบให้ NITMX จัดเครื่องมือช่วยสมาชิกตรวจจับและสนับสนุนข้อมูล · FAQ 5 คาดหวังให้ NITMX สนับสนุนระบบกลางจัดลำดับความเสี่ยงรายบัญชี และให้ตรวจพบก่อนธุรกรรมเสร็จ · ไม่ยกเว้น PDPA | `references/legal-primary-sources.md` S4 (ตัวบท ตรวจ 29 ก.ย. 2026) |
| พ.ร.ก. อาชญากรรมทางเทคโนโลยี: ยกเว้น PDPA ที่ **ม.12** เฉพาะการประมวลผลตาม พ.ร.ก. · ม.4 เริ่มเมื่อมีเหตุอันควรสงสัยและผ่านระบบที่หน่วยงานเห็นชอบ (CFR) | S1, S2, S11 |
| NITMX ได้รับอนุญาตระบบโอนเงินรายย่อยฯ 28 ก.ย. 2561 · privacy notice วางตัวเป็นผู้ประมวลผลของสมาชิก และอ้างข้อตกลงการประมวลผลข้อมูลกับสมาชิก 2565 | S8, S10 |

## Product Design v3.3 — ข้อสรุปหลังรวม research และข้อทักท้วง (28 ก.ย. 2026)

> อ้างอิง: `product_design/trust-provenance-product-design-v3.3.md` v3.3.0 · D1–D29 เก็บเป็นประวัติตามเดิม ข้อใหม่ด้านล่างใช้แทนส่วนที่ขัดกัน · ✅ หมายถึงทิศทางที่ผู้ใช้ระบุแล้ว ส่วน 🟡 เป็นข้อเสนอพร้อมใช้วางแผน ไม่ใช่การรับรองจาก NITMX/ธนาคารหรือผลทดลอง

**D30 ✅ Product อยู่ใน ecosystem ของ NITMX/PromptPay และใช้งานผ่าน Mobile Banking** (ยืนยันทิศทาง D29)
- NITMX เป็น operator ของบริการสัญญาณกลาง ธนาคารเป็นผู้ implement UX/policy และ review เคส BOT มีบทบาทกำกับ/พิจารณาตามอำนาจ ไม่ใช่ผู้ซื้อหลัก
- ผู้ใช้ไม่ต้องติดตั้งแอปใหม่ ทีม HTTPS ส่งต้นแบบและเครื่องมือให้ operator นำไปพัฒนาต่อ; IP/maintenance/production owner ต้องตกลงหลังบูทแคมป์

**D31 🟡 T2 + Evidence เป็นแกน เปิด T1/T3 ด้วย gate แยก** (แก้ D25/D27/D29) · v3.3 §0–§3
- บริการหลักยังรันที่ NITMX บนข้อมูลที่ได้รับสิทธิและมองเห็นผ่าน switch; Bank module เป็นส่วนเสริม on-us/ทางสำรอง
- A = subject/pair features ที่ธนาคารทำเองได้; B = recipient/network context ที่ธนาคารฝั่งใดฝั่งหนึ่งอาจไม่เห็น ห้ามใช้ fan-out ของ seeder เพียงอย่างเดียวอ้างว่าธนาคาร seeder ทำไม่ได้
- พิสูจน์ A vs A+B, เทียบ bank-local A ที่รวม on-us และเทียบ control เดิม + TP ถ้า B ไม่เพิ่มผลให้ลด B และพิสูจน์คุณค่ามาตรฐาน/ต้นทุนแยก
- T1 เงินล่อใช้ NONE/ELEVATED เท่านั้น; CFR warning เป็น control เดิมแยกจาก pattern engine

**D32 🟡 Account context แยกจาก scam episode** (แก้ D3/D25/D26) · v3.3 §2, §7
- Feature context = subject account กับหลายคู่บัญชี ย้อนหลัง90วัน ครอบคลุม seedจากA→จ่ายBโดยไม่สรุปว่าA/Bอยู่แก๊งเดียวกัน
- Scam episode = ชุดรายการที่ case evidence หรือ injection ผูกด้วยหลักฐาน เป็นหน่วยประเมิน; ไม่ใช้ `pair_episode` เรียกทั้งสองอย่าง
- Recently observed pair ≤30วันเป็น feature ไม่ใช่ hard expiry ของ detection; อายุที่สังเกตไม่เท่ากับรู้จักกันจริง คู่นอกwindowกลับมาไม่ถือว่าใหม่แน่นอน
- User token เป็นบัญชี ไม่ใช่บุคคล; sparse history มี status แยกและไม่ถือว่าเสี่ยงต่ำ

**D33 🟡 Canonical data/label contract และ state inventory** (แก้ D5/D7/D17/D26/D29) · v3.3 §4, §7, §9
- ใช้ `event_id, ts, ingested_at, payer_token, payee_token, payer_bank, payee_bank, amount_thb, txn_type, payer_type, payee_type, channel, rail, route_scope, event_status, source, is_synthetic, synthetic_fields` ไม่มี direction; optional `original_event_id` สำหรับ reversal
- Schema label ใช้ `label_effective_ts`, `label_unit=TRANSACTION|TRANSFER_INTENT|SEEDER_WINDOW`, `label=CONFIRMED_SCAM|CONFIRMED_LEGITIMATE|UNKNOWN`, `label_source=INJECTED|CASE|REVIEW`; CFR_WEAK เป็น context ไม่ใช่ supervised label
- T2 positive รวม scam outboundก้อนแรก; T1 positiveเฉพาะเงินล่อที่ยืนยัน; T3 suspicious leadยังไม่ใช่confirmed positive
- ไม่มีรายงาน60วัน = MATURE_UNLABELED สำหรับ negative proxy ไม่ใช่confirmed legitimate; KYCผ่าน/ถอดสถานะ/กดไม่เกี่ยวข้องไม่ใช่negativeอัตโนมัติ
- Online state90วันประกอบด้วยbucket, summary, sketches และbounded evidence ไม่กล่าวว่าเป็นcounterนิรนาม; event buffer24ชั่วโมง, compact audit90วัน, full evidence365วันเป็น retention proposal
- สิทธิtraining/historyเป็นคนละinventoryกับonline TTL; ขออย่างน้อย6เดือนแต่ต้องเพียงพอกับwarm-up90วันและmaturation60วันจริง

**D34 🟡 แผนข้อมูลสองงาน** (เลือกแนวทางแทนคำถาม D6) · v3.3 §7.1
- Audit Berkaเพื่อnormal-history benchmarkและinjectionบนข้อมูลจริงตามที่รองรับ ไม่สุ่มbank codeแล้วอ้างเป็นswitchจริง
- ต้องตรวจlicense,คู่ขาเข้า/ออกที่เชื่อมกันได้และความละเอียดวัน ถ้าไม่ผ่านให้จำกัดเป็นdescriptive benchmarkและระบุว่าreal-data evaluationยังไม่สำเร็จ
- ใช้multi-bank simulatorสำหรับB/T3/on-us/adversarial; AMLworldเป็นทางเลือกหลังตรวจสิทธิ ไม่ใช้AML labelsแทนscam labels ผลเป็นlearnability
- Datasetที่เหมาะยังต้องผ่านM2 ไม่อ้างว่าโหลดหรือauditแล้วในงานออกแบบนี้

**D35 🟡 API หลังรู้ผู้รับและยอด, T1 เป็น bank-hosted webhook** (แก้ D21/D25/D29) · v3.3 §3, §5
- T2 `POST /v1/risk-check` ที่NITMX เมื่อresolved payee+amountพร้อม ไม่บังคับคู่ขนานLookup ถ้ายังไม่มียอดไม่score
- Bindingใช้intent_id+revision→event_id; retryไม่เพิ่มwarning ไม่restartdelay; แก้ยอด/ผู้รับต้องscoreใหม่ ผลมีอายุ120วินาที
- Deadlineฝั่งธนาคาร50ms, fail-openเฉพาะTP ไม่ข้ามcontrolเดิม; mTLS/member authorization/idempotency
- T1 `/v1/inbound-signal` hostที่ธนาคารผู้รับ NITMXpushหลังcompleted event; cap1ครั้ง/บัญชี/7วันและ2ครั้ง/30วัน ไม่มีผลลดT2
- `INSUFFICIENT_HISTORY`เป็นstatus; ประเมินไม่ได้ใช้signal_level=null ไม่ตอบNONEปลอม

**D36 🟡 เกณฑ์ประเมินฉบับใช้งานได้** (ปรับ D19/D22/D23/D27) · v3.3 §8
- คงnorth star value flagged before loss ไม่อ้างprevented loss; exposureนับmissed episodeด้วยE=L และใช้mean normalized exposureเป็นตัวหลักG8แทนmedianบาทอย่างเดียว
- T2 HIGH≤5/10k, warningรวม≤20/10k; T1เทียบกับT2-onlyใช้denominatorร่วมและtotal budget20/10k eligible inbound+intent เลือกallocationบนvalidation; จำนวนtestต่าง>5%ถือG8ยังสรุปไม่ได้ที่งบเท่ากัน
- คงG1–G3/G5/G7/G9หลักเดิม ปรับG4ให้PR-AUC≥0.99เป็นaudit triggerไม่ใช่หลักฐานleakageแน่นอน เพิ่มG10 hard negativesT1 upper95%CI≤0.5%แต่ละกลุ่ม และG11 capacity/review yieldของT3
- Bootstrap cluster ring/subject; prevalenceเป็นสมมติฐานและต้องแสดงsensitivity; unknown labelsห้ามนับเป็นconfirmed negativesทั้งหมด
- Gateตัวเลขเป็นข้อเสนอที่ต้องfreezeก่อนM5 ไม่อ้างว่าทีม/ธนาคารรับรองหรือผ่านแล้ว

**D37 🟡 LeadและEvidenceต้องสะท้อนสิทธิ/การแสดงผลจริง** (แก้ D26/D27) · v3.3 §3.3–§3.4, §9
- Seeder bankเห็นlocal evidence+permitted aggregates ไม่เห็นรายชื่อ/รายการเหยื่อต่างธนาคารโดยปริยาย; ไม่ส่งe-wallet leadก่อนรู้owning member
- Pilot cap10new leads/day/bank, triage1วันทำการ; suspicious→CFRเป็นคนละขั้นตามworkflowที่ได้รับสิทธิ
- CFR3รอบ/วันเป็นsimulation assumptionจากบันทึกเดิม ไม่ใช่SLAที่ยืนยันล่าสุด จำลองreview+propagationก่อนนับเหยื่อรายถัดไป
- Logแยกsent/ack/displayed/actions มีREAD_MORE/NO_ACTIONพร้อมobservation window; bankเป็นเจ้าของcase report
- Hash chainแบ่งpartitionและanchorภายนอก; samplingT1/T2แทนreviewทุกalert; canceled intentไม่เป็นpositive/negativeอัตโนมัติ

**D38 🟡 Production/businessต้องมีownerและgateที่ตรวจรับได้** (แก้ข้อเสนอราคา/ROIในv3.2) · v3.3 §10–§13
- เสนอdesign partnershipกับNITMXและ2ธนาคารก่อนค่าสมาชิกบริการ; ไม่อ้างราคาCFR/จำนวนสมาชิกผู้ซื้อหรือbreak-evenจากค่าเสียหายเฉลี่ยข่าว
- รวมbank integration, UX, Fraud Ops, security/legal/validationและinfraในต้นทุน; forecastต้องคูณwarning effectและdisplacement ไม่ตีflagged moneyเป็นเงินที่ธนาคารประหยัดได้
- Activity-level legal basis/controller roles/state/label sharing/retentionต้องรับรอง ไม่ถือว่าประกาศ57/2568หรือtokenizationอนุญาตทุกกิจกรรมแล้ว
- หน้าHTML BOTยืนยันกรอบทั่วไปได้ แต่ข้อกฎหมายเฉพาะ/ใบอนุญาตยังเป็นQ1; งานนี้ไม่อ่านPDF
- Q1–Q7ในv3.3คือexternal readiness gates ไม่บล็อกการพัฒนาprototypeที่ใช้ข้อมูลตามสิทธิ

**D39 🟡 Demoและข้ออ้างใช้ชุดเดียว** (แก้ D20/D27 และ Appendix เดิม) · v3.3 §14
- ลำดับ1,000ออก→200เข้า→5,000ออก→800เข้า→intent50,000; payout2ครั้งรวม1,000, escalation_vs_pair=10 ไม่ใช้25
- 4ฉากจากreplayจริง; refundจากร้านค้าบัญชีบุคคลเป็นhard negativeหลัก ไม่เขียนบทบังคับNONE
- ไม่อ้างว่าinbound warning/ML/network scoreเป็นนวัตกรรมที่คู่แข่งไม่มี; ชูสมมติฐานseed→escalationและวิธีพิสูจน์ในecosystemไทย

**D40 🟡 แยก “switch เห็น”, “feed ส่งให้ TP”, และ “ได้รับสิทธิใช้” ก่อนเปิด feature** (ขยาย D29/D33/D35; ตอบข้อทักท้วงกรรมการ) · v3.3 §4.1
- ข้อเท็จจริงที่ยืนยันได้จากแหล่งสาธารณะคือ NITMX ดำเนิน ITMX/PromptPay ข้ามธนาคารภายใต้การกำกับของ BOT; ยังไม่มี sample message, field catalog, transaction rows หรือ permission agreement สำหรับ TP ใน folder นี้
- Schema ใน D33 เป็น **target contract** ไม่ใช่ schema ของ switch ที่ตรวจแล้ว การมีข้อมูลใน payment flow ไม่ได้ยืนยันว่าดึงมาเก็บ 90 วัน วิเคราะห์ทุกคู่ หรือเปิดเผยสรุปให้สมาชิกได้
- T2 ที่ NITMX ต้องมี stable token ทั้งสองฝั่ง + เวลา/ยอด/event สำเร็จย้อนหลัง และยอด+ผู้รับของ current intent จากธนาคาร; ถ้าขาด stable pair token หรือ event สองทิศให้หยุด Relationship Trajectory Engine สำหรับ route นั้น ไม่ใช้ค่าเดาแทน
- T1 ต้องยืนยัน P2P/PERSON และเครดิตสำเร็จ; ถ้า UNKNOWN ไม่ส่ง pattern warning · B/T3 ต้องมี stable recipient token ข้ามสมาชิกและสิทธิคำนวณ/ส่ง aggregate · confirmed labels ต้องมีข้อตกลงแยก
- `escalation_vs_user` สำหรับ switch ถูกเรียกให้ตรงขอบเขตว่า `escalation_vs_observed_outbound`; Bank module ที่เห็นประวัติบัญชีครบจึงค่อยใช้ชื่อเดิม
- M1 ต้องส่ง data-visibility matrix ต่อ route: field มีจริง? พร้อมก่อนเวลาตัดสิน? มีสิทธิใช้/เก็บ/ส่ง? ถ้าข้อใดไม่ผ่าน ให้ปิด feature/route และรายงาน coverage แทนการส่ง NONE ที่ชวนเข้าใจผิด
- ตอนนี้มีเพียง design และเอกสารเคส ไม่มีข้อมูลธุรกรรมใน folder นี้; simulator/engine ยังต้องสร้าง ผล performance ยังไม่มี

**D41 🟡 Legal & data feasibility: แยกฐานรายกิจกรรม เริ่ม pilot จากส่วน A** (ขยาย D38/D40; ตอบข้อทักท้วงด้าน Data + Legal) · `product_design/trust-provenance-legal-data-pack.md`, `references/legal-primary-sources.md`
- ตรวจต้นฉบับแล้ว: 57/2568 ใช้กับ NITMX (เอกสารแนบ 5.3.2(2) + FAQ 5) แต่ไม่ยกเว้น PDPA · พ.ร.ก. ยกเว้น PDPA ที่ ม.12 เฉพาะการประมวลผลตาม พ.ร.ก. ส่วน ม.4 เริ่มเมื่อมีเหตุอันควรสงสัย · NITMX วางตัวเป็นผู้ประมวลผลของสมาชิก (ข้อตกลง 2565) · แก้ §11 ของ v3.3 เป็น v3.3.2
- แยก 13 กิจกรรม (A1-A ถึง A12) · ไม่ใช้ consent เป็นฐานของ T1/T2/T3/training เพราะใช้ข้อมูลคู่บัญชีที่ไม่ได้ยินยอมและถอนได้ · consent ใช้เฉพาะฟีเจอร์เสริมที่แยกที่เก็บ
- ฐานที่เสนอให้ Legal ตรวจ: ม.24(6) อิง 57/2568 / สำรอง ม.24(5) + LIA · ขั้นหลังสงสัยใช้ พ.ร.ก. ม.4 · ม.24(3) เป็นฐานเสริมเฉพาะข้อมูลของผู้โอนเอง · ไม่ใช้ ม.24(1)/(4)
- แยก A (ลูกค้าธนาคารที่สั่งงาน) ออกจาก B (คู่บัญชีกับบุคคลที่สาม): A น่าจะทำได้ใต้บทบาทผู้ประมวลผลเดิมด้วย addendum กับธนาคารนำร่อง (ตัวเลือก P, อนุมานรอ Legal) · B ต้องมีข้อตกลงร่วมของสมาชิก (ตัวเลือก J, จุดเริ่มเจรจา; PDPA ไม่มีสถานะ joint controller สมาชิกแต่ละรายยังเป็นผู้ควบคุมของตน) · NITMX เป็นผู้ควบคุมเอง (C) เป็นคำถามให้ Legal
- 🔴 ห้ามใช้ข้อมูลจริงจนกว่าจะ sign-off: A1-B บริบทข้ามสมาชิก, A5 T3 enrichment, A8 label จากเคส, A9 training
- Pilot data request: Tier 1 ธุรกรรม P2P ข้ามธนาคารของลูกค้าธนาคารนำร่อง 2 แห่ง 12 เดือน (ขั้นต่ำ 9) + label ถึง 60 วันหลังเหตุการณ์สุดท้าย · Tier 2 (1 hop) เมื่อ A1-B ผ่านเท่านั้น · ไม่ขอชื่อ/เบอร์/เลขบัตร/proxy/memo/อุปกรณ์/ยอดคงเหลือ
- T3 aggregate ไม่แสดงค่าที่นับจากผู้รับน้อยกว่า 5 ราย (ค่าให้ DPO ตั้ง) · label ระดับ L0–L6 · CFR/feedback/การยกเลิกไม่ใช่ label · label จากคดีอาจเป็นข้อมูลประวัติอาชญากรรมตามประกาศ คกก. 2566 ต้องให้ Legal ตัดสิน
- Gate G-0 ถึง G-4 รวมเงื่อนไขกฎหมาย ข้อมูล ความปลอดภัย และโมเดลจาก v3.3 §8/§11/§13 ไว้หน้าเดียว (G1–G11 และ Q1–Q7 ยังใช้ตามเดิม) · คำถามที่ยังไม่ทราบ U1–U16

**D42 🟡 หยิบวิธีคิดจาก ARIC Scam Detect / Visa A2A Protect: baseline รายบุคคลที่ scam ดันไม่ได้, กลุ่มคู่ใหม่รับการหมุนบัญชี, วัดผลแบบจับเพิ่มจาก control เดิม** (ขยาย D9/D32/D36 · แก้ demo ใน D39) · v3.3 §1.1, §4.1, §5.1, §6, §7.2, §8.4, §14 · research: `references/research/aric-scam-detect-deep-dive-2026-09-28.md`
- ข้อมูล AOC (29 ก.ย.): 14 เคสที่มีเงินล่อ ใช้บัญชีปลายทางมัธยฐาน 4 บัญชี (12/14 ≥ 2, 10/14 ≥ 3) กระจายมัธยฐาน 2 ธนาคาร (9/14 ≥ 2) · 7/14 เคสรายชื่อไม่ครบ ตัวเลขจึงเป็นขั้นต่ำ และเป็นเคสคัดเผยแพร่ ไม่ใช่ประชากร → เมื่อคนร้ายหมุนบัญชี `escalation_vs_pair` เป็น missing บ่อย และ p95 ของยอดออกทั้งหมดถูกยอด scam ก่อนหน้าดันสูงขึ้น (ปัญหาเดียวกับที่ ARIC เตือนว่า baseline ที่ปรับเร็วจะดูด fraud เป็นเรื่องปกติ)
- Feature A ใหม่: **กลุ่มคู่ใหม่** = ยอดออกใน 14 วันไปยังคู่ที่ ณ ตอนโอนเพิ่งสังเกตไม่เกิน 14 วัน (นิยามเดียวกับ seed-like) · `escalation_vs_new_cluster`, `new_cluster_return_ratio`, `new_cluster_payee_count_14d`, `ladder_steps` · **Established baseline** = `escalation_vs_established` ใช้เฉพาะยอดออกให้คู่ที่สังเกตมาเกิน 30 วัน (ตรงเกณฑ์ ≤ 30 วันของ D32) · `subject_return_baseline` ทำเมื่อ hard negatives ของ T1 ไม่ผ่าน G10
- Rule T2: seed-like ≥ 2 และยอด ≥ 3 × max(ยอดสูงสุดให้คู่เดิม, ยอดสูงสุดในกลุ่มคู่ใหม่) · grid เดิม
- Adapter แตก settled event เป็นสองมุม (payer OUT / payee IN) ตามแบบที่ Scam Detect ส่ง on-us เป็น 2 event · T1/T2/T3 ใช้ state ชุดเดียว
- §8.4 แยก arm: 0 control เดิม (rule) · 1 generic behavioral (LightGBM บน feature ทั่วไป) · 2 = 1 + trust provenance · 3 = 2 + B (simulator) · รายงาน episode ที่จับเพิ่มจาก arm 0 ที่ FP:TP 5:1 และ recall before largest · ถ้า arm 1 ได้เท่า arm 2 ต้องรายงานตามจริง · ผลทั้งหมดเป็น learnability
- Champion/challenger: ส่งผลของ engine ที่ผ่าน G1 และ log คะแนนของอีก engine ทุก decision
- Contract (ข้อเสนอ): response เพิ่ม `risk_score` (null เมื่อ engine=RULE) ให้ fraud engine ของธนาคารใช้เป็น input · feedback เพิ่ม `return_type`, `return_sub_type`, `original_event_id` ส่งรายวันไม่เกิน 48 ชม. หลังรับแจ้ง · ชั้น field F0/F1/F2 (ไม่ใช้ชื่อ Tier เพราะซ้ำกับ legal/data pack) · B เปิดแบบ opt-in รายสมาชิก
- Demo (แทน D39): V→B1 1,000 · S→V 200 · V→B2 5,000 · S→V 800 · V เตรียมโอน B3 50,000 → `escalation_vs_new_cluster` = 10 · คู่ V–B3 ไม่มีประวัติ
- ไม่หยิบ: RNN/ADBN, foundation model, transfer learning, unified score รวม T1–T3, multi-rail, device/session, peer group จากข้อมูลประชากร, time-of-day (Berka มีแค่วันที่) · ห้ามอ้าง "13 fields" หรือ "< 30 attributes" (ไม่พบในต้นฉบับ) และห้ามเรียกการ calibrate ใหม่รายธนาคารว่า transfer learning
- Positioning: TP เป็น typology signal ที่เสียบเข้า fraud engine ใดก็ได้ ไม่ใช่คู่แข่งของ Visa · T1 notification ยังอยู่หลัง gate ตาม D31 ไม่ยกเป็นพระเอก

**D43 ✅ ตรึง protocol ของ G-0 Lab (29 ก.ย. 2026)** · `docs/lab/G0_EXPERIMENT_PROTOCOL.md` (SHA-256 ใน `docs/lab/PROTOCOL_DEVIATIONS.md`)
- คำถามหลัก H1: arm 2 (GENERIC + TRUST) เตือนก่อนก้อนใหญ่สุดได้มากกว่า arm 1 (GENERIC) ที่งบเท่ากันไหม · ตัดสินด้วย paired 95% CI แบบ ring bootstrap บน family seed-payout ใน test ที่ไม่ใช่ holdout · budget หลัก ELEVATED+HIGH 20/10k (ทีมเลือก) · รายงาน 5/10k และ 1/10k
- ข้อมูล: simulator หลายธนาคารอย่างเดียว · ช่วงพารามิเตอร์ตั้งโดย generator agent ที่ไม่เห็น feature/threshold (`G0_GENERATOR_BRIEF.md`, `G0_SCENARIO_SPEC.md`) · family drain ไม่มีเงินล่อเก็บไว้เป็น placebo (ทีมเลือก) · มุมมอง switch = P2P ข้ามธนาคารเท่านั้น · Berka เป็น SHOULD
- Budget บนข้อมูลที่ scam หนาแน่น: เลือก threshold จากอัตราเตือนถ่วงที่ p = 1:5,000 (§8.2) · rule T2 ใช้ตัวคูณต่อเนื่องเพื่อให้ใช้งบเท่ากับ ML · arm 0 ไม่มี CFR mock จึงเป็นขอบบนของส่วนที่ TP ดีกว่า control
- SHOULD ตามลำดับ: H4 (mimicry + holdout) → H5 (arm 3) → ผลราย variant → sensitivity hard negatives → Berka → T1 + burden (ทีมเลือก H4 ก่อน)
- แก้หลังจากนี้ทาง `docs/lab/PROTOCOL_DEVIATIONS.md` เท่านั้น · ผลทั้งหมดเป็น learnability ไม่ใช่ production accuracy

**D44 🟡 Audit ก่อนเปิด test: ตรึงหลักฐานต้นทางและเปิดเผย label ของ validation ที่มาช้า** (29 ก.ย. 2026) · `docs/lab/G0_AUDIT.md`
- Manifest ต้อง hash source tables ที่ใช้สร้างผล, dataset profile, ชุด mimicry ที่จะประเมิน และตัวสร้างรายงาน; evaluation ปฏิเสธไฟล์ที่เปลี่ยนหรือชุด mimicry ที่ไม่ได้ตรึงก่อน test
- การเลือก early stopping, rule และ threshold ใน G-0 ใช้ ground truth ของ validation หลัง label mature ตาม D43; นับ positive ที่รู้ label ทัน cutoff วันที่ 330 และระบุในรายงานว่าเป็นการจูนย้อนหลัง ยังอ้างความเป็นไปได้ของการจูน ณ วัน 330 ไม่ได้
- ไม่เปลี่ยนสมมติฐาน H1, budget, split, arm หรือเกณฑ์ผ่านของ protocol ที่อนุมัติแล้ว; ถ้าจะเปลี่ยนวิธีเลือกโมเดลให้ใช้เฉพาะ label ที่มี ณ cutoff ต้องบันทึก deviation และเปิด test หลัง freeze ใหม่

**D45 ✅ ลงทะเบียนเพิ่มก่อนมีข้อมูล: แยกผลของเงินล่อด้วย arm 2e และปิดช่องเล่าผลหลังเห็นตัวเลข** (30 ก.ย. 2026) · `docs/lab/PROTOCOL_DEVIATIONS.md` #2 · `docs/lab/G0_DATA_CONTRACT.md` · `docs/lab/G0_AUDIT.md`
- TRUST แยกเป็นกลุ่มเงินล่อ/เงินคืน 7 ตัว (`TRUST_SEED`) และกลุ่มยอดไต่ 3 ตัว (`TRUST_ESCALATION`) · arm 2e = GENERIC + ยอดไต่ · **H1s = arm 2 − arm 2e** เป็นหลักฐานเดียวที่ใช้อ้างว่า "เงินล่อช่วยเตือน" ซึ่งเป็นจุดใหม่ของ TP เมื่อเทียบกับ fraud engine ทั่วไป · placebo เปลี่ยนเป็น arm 2 − arm 2e บน family D เพราะแบบเดิมให้ผลบวกจาก feature ยอดไต่ได้โดยไม่ใช่ artifact
- G2/G2b คำนวณจาก TPR เมื่อ FPR ถูกตั้งตามงบ (ผ่านเมื่อ TPR ≥ 0.42 / 0.48) จึงไม่ใช่หลักฐานภาระเตือนผิด · ภาระจริงต้องวัดบนธุรกรรมสุจริตจริง (ส่งต่อให้ M2)
- ตรึงกติกา ceiling (arm 1 บน validation ≥ 0.95), งบจริงไม่เท่ากัน (> 0.2 × งบ), G3 alert < 10, G4 audit บน validation · data contract ที่ `tp.dataset` ตรวจ และ rehearsal บน validation ก่อนเปิด test
- H1, budget หลัก 20/10k, split, arm เดิม และเกณฑ์ผ่านเดิมไม่เปลี่ยน

**D46 ✅ ไม่ fit แถว train วัน 90–119 เพราะ cold start** (30 ก.ย. 2026) · `docs/lab/PROTOCOL_DEVIATIONS.md` #3
- state เริ่มว่างที่วัน 0 ทำให้ seed-like ช่วงแรกค้างใน window 90 วันถึงราววัน 120 · warm-up 90 วันจึงสั้นกว่าที่ feature ต้องใช้ (window 90 วัน + เกณฑ์คู่ใหม่ 30 วัน)
- LightGBM ทุก arm fit เฉพาะวัน 120–269 · วัน 90–119 เป็น history อย่างเดียว · split, ring, label cutoff, validation และเกณฑ์เดิมไม่เปลี่ยน

**D47 ✅ ระบุความเป็นอิสระของ simulator ตามจริง** (30 ก.ย. 2026) · `docs/lab/PROTOCOL_DEVIATIONS.md` #4
- `G0_SCENARIO_SPEC.md` และช่วงพารามิเตอร์ถูกตรึงโดย generator agent แบบ detector-blind ก่อนมีข้อมูล; ส่วนท้ายของ `src/tp/sim.py` ที่ค้างถูกเขียนต่อโดยผู้ที่เห็นฝั่ง detector แล้ว
- ไม่แก้ช่วงพารามิเตอร์ตามผลโมเดลและยังไม่เปิดผล test; รายงานต้องระบุว่า **scenario design** blind แต่ **implementation** ไม่ blind ทั้งหมด จึงเป็นข้อจำกัดของหลักฐาน H1/H1s
