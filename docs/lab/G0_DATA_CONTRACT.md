# G-0 Data Contract — ผลลัพธ์ของ simulator ที่ pipeline รับ

> ลงทะเบียน 30 ก.ย. 2026 ก่อนมีข้อมูล (`PROTOCOL_DEVIATIONS.md` #2) · **schema อย่างเดียว** ไม่มีนิยาม feature, window หรือ threshold ของ detector
> Generator agent อ่านไฟล์นี้ได้เพิ่มจาก `G0_GENERATOR_BRIEF.md` (ขยาย knowledge boundary เฉพาะไฟล์นี้) · ถ้าขัดกับ brief ให้ยึดไฟล์นี้ · **generator ห้ามเปิด `PROTOCOL_DEVIATIONS.md` และไฟล์อื่นที่อ้างถึง** เพราะมีชื่อ feature
> `tp.dataset` ตรวจทุกข้อด้วย `check_contract()` และหยุดทันทีเมื่อไม่ตรง · `tp.evaluate` หยุดเมื่อ population ที่ลงทะเบียนไว้ว่าง

## 1. ไฟล์และคำสั่ง

- Folder: `data/processed/g0/m0/`, `data/processed/g0/m0.5/`, `data/processed/g0/m1/` (สะกดตรงตัว) · แต่ละ folder มี `events.parquet`, `labels.parquet`, `episodes.parquet`, `ring_accounts.parquet`, `hn_events.parquet`
- คำสั่ง: `PYTHONPATH=src .venv/bin/python -m tp.sim --seed 20261003 --mimicry <0|0.5|1> --out data/processed/g0/m<0|0.5|1>`
- สร้างครบ 3 ชุดก่อน `tp.train` เพราะชุด mimicry ที่ไม่ได้ตรึงตอน train จะใช้ประเมินไม่ได้
- บันทึกคำสั่ง, seed, SHA-256 ของ `src/tp/sim.py` และของทั้ง 15 ไฟล์ใน `data/SOURCES.md` (AGENTS.md ข้อ 2)

## 2. ตาราง

คอลัมน์ในตารางนี้บังคับ ส่วนคอลัมน์อื่นตาม brief ใส่เพิ่มได้ · เวลาเป็น int64 วินาที UTC ทุกคอลัมน์ · วันที่ 0 = epoch 1735664400

| ตาราง | คอลัมน์ | ชนิด / ค่าที่อนุญาต |
|---|---|---|
| `events` | `event_id` | str ไม่ซ้ำ |
| | `ts` | int64 |
| | `payer_token`, `payee_token` | str ไม่ว่าง |
| | `amount_thb` | > 0 ทศนิยมไม่เกิน 2 ตำแหน่ง |
| | `txn_type` | `P2P` · `MERCHANT` · `BILL` · `PAYROLL` |
| | `payer_type`, `payee_type` | `PERSON` · `MERCHANT` · `BILLER` · `EMPLOYER` · `UNKNOWN` |
| | `route_scope` | `CROSS_BANK` · `ON_US` |
| | `event_status` | `SETTLED` · `FAILED` |
| | `is_synthetic` | 1 ทุกแถว |
| `labels` | `event_id` | ต้องมีใน `events` · หนึ่ง event มีได้หนึ่ง label |
| | `label` | `CONFIRMED_SCAM` |
| | `subject_token` | token ของเหยื่อ |
| | `episode_id` | ต้องมีใน `episodes` |
| | `event_role` | `SIGNUP_FEE` · `STEP` · `UNLOCK_FEE` · `SEED_INFLOW` · `GROOMING_OUT` · `GROOMING_IN` |
| | `label_effective_ts` | int64 |
| `episodes` | `episode_id`, `ring_id`, `victim_token` | str |
| | `split` | `train` · `val` · `test` |
| | `family` | `A` (seed-payout ladder) · `D` (drain ไม่มีเงินล่อ) |
| | `variant` | `""` หรือ token จาก `SPLIT` · `LONG_GAP` · `ON_US_HOP` · `FRAGMENTED_SEED` · `AGED_RECEIVER` คั่นด้วย `\|` เช่น `SPLIT\|ON_US_HOP` |
| | `is_holdout`, `mimicry_applied` | int 0/1 |
| | `loss_thb` | float |
| `ring_accounts` | `ring_id`, `token` | str |
| | `role` | `SEEDER` · `RECEIVER` · `SINK` · `RING_MERCHANT` |
| `hn_events` | แทน list `event_ids` ใน brief | หนึ่งแถวต่อหนึ่ง event ของ hard negative |
| | `event_id` | ต้องมีใน `events` |
| | `hn_id`, `subject_token` | str |
| | `group` | `SHOP_PARTIAL_REFUND` · `FRIEND_LOAN_REPAID` · `BILL_SPLIT` · `FAMILY` · `DEPOSIT_RETURNED` · `LEGIT_ESCALATION` |
| | `step` | `OUT` = เงินออกครั้งแรกของ subject · `IN` = เงินเข้าหา subject (คืน ทอน หรือส่วนแบ่ง) · `NEXT` = เงินออกครั้งถัดไปของ subject |
| | `split` | แนะนำให้ใส่ |

## 3. กติกาข้ามตาราง

1. `is_holdout = 1` เมื่อและเฉพาะเมื่อเป็น family A, split `test` และ `variant` มี `FRAGMENTED_SEED` หรือ `AGED_RECEIVER`
2. ทุก split ต้องมี family A ที่ไม่ใช่ holdout, family D, family A ของแต่ละ variant (`SPLIT`, `LONG_GAP`, `ON_US_HOP`, ไม่มี variant) · test ต้องมี holdout ทั้งสองแบบ · hard negative ทั้ง 6 กลุ่มต้องมีเงินออกของ subject ใน val และ test · ขนาดขั้นต่ำตาม brief
3. ชุด m0.5 และ m1 ต่างจาก m0 ได้เฉพาะ event ของ episode ที่ถูก mimic ในช่วง test (spec §2.5) · rehearsal ตรวจว่าแถวก่อนวันที่ 330 เหมือนกันทุกค่า
4. บัญชี ring เป็น token ใหม่ที่อยู่เฉพาะ split ของ ring นั้น (brief)
