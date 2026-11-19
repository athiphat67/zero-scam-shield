# SOURCES — G-0 synthetic data

- วันที่สร้าง: 30 ก.ย. 2026
- แหล่ง: simulator ของโครงการ `src/tp/sim.py` ตาม `docs/lab/G0_SCENARIO_SPEC.md` (ใช้สถิติ AOC 191 เคสเพื่อกำหนด scenario; ไม่ใช้แถวธุรกรรมจริง)
- License: โค้ดและข้อมูลจำลองเป็นผลงานภายในโครงการ; ไม่ใช่ข้อมูล NITMX หรือธนาคาร
- ข้อจำกัด: synthetic learnability เท่านั้น; ยังไม่มีการประเมินบนพฤติกรรมปกติจริง
- Seed: `20261003` · generator SHA-256: `2086773bab465b0ed94ac96273cde2a0f581059f4c52e45268bae353413b14cb`
- คำสั่ง: `PYTHONPATH=src .venv/bin/python -m tp.sim --seed 20261003 --mimicry <0|0.5|1> --out data/processed/g0/m<0|0.5|1>`

| ไฟล์ | SHA-256 |
|---|---|
| `data/processed/g0/m0/events.parquet` | `01c4ada5d53a989d6eb5a3a147cc9109e7f50d6a3726e45ceb2390542589f42a` |
| `data/processed/g0/m0/labels.parquet` | `8ea09ba2bd6211f746fb2403b80a5e9c1c33693cd36a8904a9b7402f180803d2` |
| `data/processed/g0/m0/episodes.parquet` | `019b481a22e5450dd07ae0e95e62ba84fe53ded441c9b4dd84d680ab33282c88` |
| `data/processed/g0/m0/ring_accounts.parquet` | `435b9d22832ed286862f390574f66da9afd9adb32febf98ad91cfe4069cca706` |
| `data/processed/g0/m0/hn_events.parquet` | `7d4a4e5424b1943a0720804bd2584b8897b53cc4e273600628b4961b700f4f4d` |
| `data/processed/g0/m0.5/events.parquet` | `09cc51c5138ef89c3f1eb9d739c19d83a32f3905321eb94345ad7dbfc5d14d29` |
| `data/processed/g0/m0.5/labels.parquet` | `0f2647101f4864c5f9547c771afe7984e0ff385897e7bd0884b207a20c02dbf2` |
| `data/processed/g0/m0.5/episodes.parquet` | `e50727d0ad23d753d40bce7a80f1cad92e7d8bb978676e0c4c36e10563fbec57` |
| `data/processed/g0/m0.5/ring_accounts.parquet` | `435b9d22832ed286862f390574f66da9afd9adb32febf98ad91cfe4069cca706` |
| `data/processed/g0/m0.5/hn_events.parquet` | `7d4a4e5424b1943a0720804bd2584b8897b53cc4e273600628b4961b700f4f4d` |
| `data/processed/g0/m1/events.parquet` | `b1c78c3f23c8cca1af95809746b4ff6b96cb78e203072aebde84340059616286` |
| `data/processed/g0/m1/labels.parquet` | `eaeaf5914068accc61c644842f57460862d06caf316e0c31e49d7962dd812365` |
| `data/processed/g0/m1/episodes.parquet` | `307005e25aaf28cf26ec13ea7e8088f700960843fd6cb1487f3a5d3eedc6aa94` |
| `data/processed/g0/m1/ring_accounts.parquet` | `435b9d22832ed286862f390574f66da9afd9adb32febf98ad91cfe4069cca706` |
| `data/processed/g0/m1/hn_events.parquet` | `7d4a4e5424b1943a0720804bd2584b8897b53cc4e273600628b4961b700f4f4d` |
