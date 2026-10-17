# รายงานตรวจและแก้งาน ARModel (D1/R2) โดย Claude — 16 ต.ค. 2026

ขอบเขต: `C:\Users\fufu\ARModel-review-20261016` branch `review/phuphan-content-admin-login`
HEAD `4108ead` ยังไม่มี commit ใหม่ งานทั้งหมดเป็น uncommitted changes
**ไม่มี commit, push, merge หรือ deploy และไม่ได้เขียนหรือลบข้อมูลใน Cloud D1/R2**

สถานะ: ✅ = แก้แล้วและมี regression test, ⚠️ = ยังเปิดอยู่

## 1. Findings และสถานะ

### P0-1 ✅ ใครก็ตั้งบัญชีผู้ดูแลครั้งแรกผ่านหน้าเว็บได้ โดยไม่มี CSRF และไม่มี rate limit

- เดิม: `/admin/login` ได้รับยกเว้น CSRF และ first-run บันทึก hash ลง D1 บน runtime ใดก็ได้ที่ไม่ใช่ Vercel
  แม้แต่พรีวิว 5017 ที่ต่อ `armodel-production`
- หลักฐาน: ทดสอบกับ SQLite แล้ว client ที่ไม่มี cookie แต่ส่ง `Origin: https://evil.example` สร้างบัญชีได้ (302)
  ส่วนบน Cloud D1 (อ่านแบบ SELECT เท่านั้น ตามที่ผู้ใช้อนุมัติ) พบบัญชี `test1234` ที่สร้างผ่านพรีวิวเวลา 15:56
- แก้แล้ว:
  - ตั้งบัญชีครั้งแรกผ่านเว็บได้เฉพาะตอน `TESTING` (`app.py` `first_run_setup_allowed`)
  - runtime จริงจะแสดงข้อความว่ายังไม่มีบัญชี และตอบ POST ด้วย 403
  - ฟอร์ม login มี CSRF token และหมุน token ใหม่หลังล็อกอินสำเร็จ
- Tests: `tests/test_review_fixes.py` 4 tests ใน `ReviewFixTests` (first-run, cross-site, CSRF)
- ⚠️ บัญชี `test1234` ยังอยู่ใน Cloud D1 ผู้ใช้ต้องตัดสินใจเองว่าจะเก็บหรือแทนที่ (ผมไม่ได้แตะ)

### P1-1 ✅ ไม่มีวิธีที่รองรับในการใส่บัญชีผู้ดูแลบน production

- `scripts/import_admin_to_d1.py` เพิ่ม `--cloud` (target IDs จาก `~/.armodel-secrets`, token จาก DPAPI)
  - ต้องระบุ username ที่ถูกรูปแบบเอง ไม่มีค่าเริ่มต้น `admin` อีกต่อไป
  - ปฏิเสธถ้ามีบัญชีอยู่แล้ว และไม่พิมพ์ hash
  - gateway ที่ไม่ใช่ loopback ยังถูกปฏิเสธ
- `scripts/import_d1_events.py` เพิ่ม `--cloud` สำหรับนำเข้าประวัติ รันซ้ำได้โดยไม่ซ้ำแถว (ID แบบ deterministic + INSERT OR IGNORE)
- **ยังไม่ได้รันกับ cloud**
- Tests: 3 tests ใน `ToolingFixTests`

### P1-2 ✅ (บางส่วน) หน้าเว็บเรียก D1 หลายรอบต่อการเปิดหน้า

- เดิม `/home` = 5 รอบ และ `/models` = 4 รอบ ผ่าน REST API
- แก้: เพิ่ม `Database.read_many` อ่านตารางเนื้อหาทั้ง 4 ใน batch เดียว ตอนนี้ทั้งสองหน้าเหลือ 1 รอบ (ไม่นับ analytics)
- Tests: round-trip count และเทียบผล `read_many` กับ `read`
- ✅ การบันทึก analytics ใช้ timeout 3 วินาที (`ANALYTICS_WRITE_TIMEOUT_SECONDS`) แทน 20 วินาที (มี test)
- ⚠️ ยังเหลือ: analytics ยังเขียนแบบ synchronous และยังไม่มี cache ข้าม request
  Cloudflare API มี rate limit ระดับผู้ใช้ (ยังไม่ได้ทดสอบ) จึงควรใช้ Worker binding ใน production

### P1-3 ✅ หน้ารายละเอียดโมเดลบนมือถือ: คำแนะนำ AR ดันตัวแสดง 3D ลงไปไกล

- ตรวจใน browser ที่ 360px: section "ดูโมเดลในพื้นที่จริงด้วย AR" ที่ Codex เพิ่ม ไม่มี CSS `order`
  ภายใน `display: contents` จึงไปอยู่บนสุด (y=246, สูง 624px) และ viewer ตกไปอยู่ y=891
- แก้: `.viewer-stage > .viewer-instructions { order: 7 }` ในบล็อก `max-width: 920px` ตอนนี้ viewer อยู่ที่ y=222
- ภาพ: `review-screenshots/claude-model-360-before.jpg`, `claude-model-360-after.jpg`

### P2-1 ✅ พรีวิว cloud เขียน analytics ลงฐานจริง

- `scripts/run_cloud_d1_review.py` ตั้ง `ARMODEL_ANALYTICS_ENABLED=0` แล้ว (มี test)
- ⚠️ ยังมี event ทดสอบเดิมใน Cloud D1: analytics 2 รายการ (15:49 และ 15:53) และ audit 1 รายการ (15:56)
  การล้างต้องได้รับอนุมัติเป็นการกระทำแยก

### P2-2 ✅ ยืนยันเสียงบรรยาย: บันทึกสำเร็จแต่แจ้งว่าล้มเหลว และลบเสียงเดิมใน R2 ทิ้ง

- เดิม: ถ้าการลบไฟล์ล้มหลัง DB commit จะขึ้นข้อความ "ไม่สำเร็จ ข้อมูลเดิมยังไม่ถูกแทนที่" และลบเสียงถาวรตัวเก่าใน R2
  (มี 3 โมเดลที่ใช้ `audio/narrations/`)
- แก้:
  - ลบไฟล์รอตรวจหลังบันทึกเสร็จเท่านั้น ถ้าลบไม่ได้ให้บันทึก warning ลง audit แต่ยังแจ้งว่าบันทึกสำเร็จ
  - **ไม่ลบเสียงเดิมใน R2** เพื่อให้ rollback ได้และตามข้อห้ามลบไฟล์ R2 เดิม
- Test: `test_narration_confirm_cleanup_failure_still_reports_saved`

### P2-3 ✅ Admin POST ที่ไม่ส่ง revision บันทึกทับข้อมูลได้โดยไม่ตรวจ

- แก้: `require_submitted_revision()` ใน `write_dataset`/`write_datasets` ถ้า POST ไปที่ `/admin/*` ไม่ส่ง
  `revision_<ชุดข้อมูล>` มา จะตอบ 409 โดยไม่บันทึก (ยกเว้น `/admin/login`)
- ตรวจแล้ว: admin POST forms ทุกฟอร์มเป็น `method="post"` และ JS ไม่ได้ส่ง POST เอง
- `tests/conftest.py`: test client ส่ง revision ปัจจุบันให้เหมือนฟอร์มที่ browser render มา โดยไม่ต้องแก้ test เดิม
- Tests: 3 tests (ไม่ส่ง revision → 409, ส่ง revision เก่า → 409, revision ปัจจุบัน → 302, ฟอร์มมี revision ครบ)
- ตรวจใน browser จริงบน 5018 แล้ว: ฟอร์มเก่าได้ 409 และโหลดหน้าใหม่แล้วบันทึกได้
- ⚠️ P3: หน้า 409 เป็นข้อความเปล่า และสิ่งที่พิมพ์ไว้ในฟอร์มจะหายไป

### P2-4 ✅ Tests อาจไปยิง Cloud D1 ถ้ามี env `D1_*` หรือ `.env`

- `d1_setting()`: ตอน TESTING จะอ่านเฉพาะ `app.config` ไม่อ่าน env (มี test)

### P2-5 ✅ Header บนมือถือกินพื้นที่ราว 1/3 ของจอ

- เดิม header แบบ sticky สูง 220px ที่ 320px และ 185px ที่ 390px เพราะชื่อเว็บยาว 5 บรรทัด
- แก้ CSS เฉพาะ ≤768px: ตัดชื่อเหลือ 2 บรรทัด ชื่อเต็มยังอยู่ใน `aria-label` และซ่อนบรรทัดรอง ตอนนี้ที่ 320px สูง 125px
- desktop ไม่เปลี่ยน (1280px header 116px และ hover panel ยังทำงาน)
- ภาพ: `claude-home-320-before.jpg`, `claude-home-320-after.jpg`

### P3

- ✅ ถ้า D1 ล้มตอนเตรียมฟอร์ม admin ตอนนี้ได้ 503 แทน 500 (มี test)
- ✅ `prepare_cloud_d1.py` init schema ให้ target ที่มีอยู่แล้วแต่ยังไม่มี schema และไม่ init ซ้ำถ้ามีแล้ว (มี 2 tests)
- ⚠️ อัปโหลดขึ้น R2 ก่อนบันทึก DB ถ้า DB ล้มจะเหลือไฟล์ค้างใน R2 (ไม่ทำให้ข้อมูลหาย)
- ⚠️ Worker ยกเว้น auth เมื่อ `LOCAL_DEVELOPMENT=true` ต้องห้ามตั้งค่านี้ตอน deploy
- ⚠️ `data/analytics_events.json` (27 events จาก localhost, gitignored) ขัดกับเอกสารเดิมที่ว่าไม่มีไฟล์นี้

## 2. ความครบถ้วนของข้อมูล Cloud D1 (ตรวจรอบนี้ อ่านอย่างเดียว)

`python scripts/verify_cloud_d1_readonly.py` (สคริปต์ใหม่ที่บล็อกทุกคำสั่งที่ไม่ใช่ SELECT/PRAGMA):

| ชุด | snapshot | D1 | revision | ผล |
| --- | ---: | ---: | ---: | --- |
| projects | 10 | 10 | 1 | ทุกฟิลด์และชนิดข้อมูลตรง ลำดับ ID ตรง |
| models | 41 | 41 | 1 | ตรงทั้งหมด และเชื่อมกับโครงการที่มีอยู่จริงครบ 41/41 |
| site_settings | 31 | 31 | 1 | ตรงทั้งหมด |
| slider_items | 2 | 2 | 1 | ตรงทั้งหมด |

- `PRAGMA foreign_key_check`: 0 violations
- D1 เพิ่ม key เดียวคือ `visible: true` ใน projects ซึ่งเป็นค่าเดียวกับที่ runtime ใช้เป็นค่าเริ่มต้น
- `validate_zero_supabase_data.py`: URL ของ R2 121 รายการผ่าน HTTP/CORS สำหรับ origin production

**ย้ายประวัติผู้เข้าชม (ทำตามคำสั่งผู้ใช้ 16 ต.ค. 2026):**
- ดาวน์โหลด `analytics/analytics_events.json` จาก R2 public URL มาเก็บที่
  `C:\Users\fufu\ARModel-migration-sources\r2-analytics\` ขนาด 150,731 bytes,
  SHA-256 `e21485bfb6847c346c8b1359e5985d2d8a50ac1cb99ae318bf51ba46f03672e7` ไฟล์ใน R2 ไม่ได้ถูกลบหรือแก้
- 538 events ช่วง 11 ก.ค. – 9 ส.ค. 2026 นำเข้าด้วย `import_d1_events.py --cloud --kind analytics`
- ตรวจกลับแบบอ่านอย่างเดียว: พบครบ 538/538 และ payload ตรงทุกรายการ ตอนนี้ analytics ใน Cloud D1 มี 540 รายการ (รวม 2 รายการทดสอบเดิม)
- ทดลองบน SQLite ก่อน: รันซ้ำไม่เกิดแถวซ้ำ dashboard ณ 9 ส.ค. แสดงผู้เข้าชม 30 วัน = 390
- ไม่ได้นำเข้า `data/analytics_events.json` (27 events, country = LOCAL ทั้งหมด จากการเปิดพรีวิววันนี้ ไม่ใช่ผู้เข้าชมจริง) ไฟล์ยังเก็บไว้
- `config.json` เป็น `{}` ไม่มีข้อมูลให้ย้าย
- เนื้อหา 4 ชุดตรวจซ้ำหลังนำเข้า ยังตรงทุกฟิลด์ (revision ยังเป็น 1)

**ยังไม่ได้ย้าย:**
- events หลัง 9 ส.ค. ใน `analytics/events/` (เก็บไฟล์ละ event ต้องใช้ R2 credentials เพื่อ list)
- `analytics_events.json` ใน R2 อ่านได้จาก URL สาธารณะ ซึ่งเป็นปัญหาความเป็นส่วนตัวของระบบเดิม (P2)
- ประวัติ R2 (`analytics/`, `audit/`, `auth/login-failures/`)
- snapshot ล่าสุดของเว็บจริง (ข้อมูลใน D1 มาจาก clone + การแก้คำอธิบายใน branch)
- บัญชีผู้ดูแลจริง

## 3. ผลทดสอบที่รันเองจริงรอบนี้

| คำสั่ง | ผล |
| --- | --- |
| `python -m pytest -q --tb=short` | **158 passed, 82 subtests passed** (เดิม 135; เพิ่ม 23 tests ใน `tests/test_review_fixes.py`) |
| `git fetch origin main` | `origin/main` = `4108ead` เท่ากับฐานที่ clone มา ไม่มี commit ข้อมูลใหม่จากเว็บจริง |
| `export_d1_snapshot.py --cloud` (อ่านอย่างเดียว) | backup ที่ `C:\Users\fufu\ARModel-migration-sources\d1-export-20261016\` ได้ 10/41/31/2 แถว และ analytics 540 รายการ |
| browser บน 5018 | login ผ่าน CSRF, dashboard 12 เดือนแสดง 400 ผู้เข้าชม / 538 ครั้ง, ทดสอบ revision ชนกันแล้วได้ผลตามที่ควร |
| `node --test cloudflare/d1/worker.test.mjs` | 5 passed |
| `node --check` site-carousel / ar-viewer / admin-dashboard | ผ่าน |
| `git diff --check` | ผ่าน |
| `verify_cloud_d1_readonly.py` (cloud, อ่านอย่างเดียว) | ผ่านทุกข้อ |
| `validate_zero_supabase_data.py` (network read) | ผ่าน |

ตรวจ UI ใน browser ของแอป Claude บนพรีวิว 5018 (SQLite ที่ copy จาก snapshot ไม่ต่อ cloud):
- ไม่มี horizontal overflow ที่ 320, 360 และ 390px (ข้อ 15px ใน baseline เดิมไม่พบแล้ว)
- ลูกศรสไลด์ทำงาน (7→0 วนรอบ)
- mouse drag เปลี่ยนสไลด์ได้
- แตะสไลด์แล้ว popup เปิด โฟกัสไปที่ปุ่มปิดและล็อกการเลื่อนหน้า กด Esc แล้วปิดและปลดล็อก
- desktop hover panel ที่ 1280px ทำงาน
- landing ที่ 360px ไม่มี overflow
- หน้า login มี CSRF

ภาพหลักฐานอยู่ใน `docs/review-screenshots/claude-*.jpg`

**NOT TESTED:**
- การโหลดโมเดล 3D จริงบนพรีวิว: R2 CORS อนุญาตเฉพาะ `https://phuphan-ar.vercel.app` (ยืนยันด้วย curl)
- AR บนมือถือจริงและ touch swipe บนอุปกรณ์จริง (ใช้ mouse drag แทน)
- R2 write จริง
- การทำงานของ `validate_cloud_d1.py` (มีการเขียน)
- ความถูกต้องของเนื้อหาโมเดลและเบอร์โทร
- เสียงบรรยายเทียบกับคำอธิบายใหม่
- หน้า admin dashboard ผ่าน browser (ตรวจด้วย tests เท่านั้น)

## 4. สิ่งที่ผู้ใช้ต้องทำหรืออนุมัติเอง

1. ตัดสินใจเรื่องบัญชี `test1234` ใน Cloud D1 (เก็บไว้ หรือลบแล้ว import hash จริงด้วย `import_admin_to_d1.py --cloud`)
2. อนุมัติการล้าง event ทดสอบ 3 รายการใน Cloud D1
3. หา R2 upload credentials หรืออนุมัติ token ใหม่ที่จำกัดสิทธิ์ แล้วทดสอบ upload จริง
4. Export ประวัติ analytics/audit/login จาก R2 เดิม แล้วอนุมัติ `import_d1_events.py --cloud`
5. กำหนดช่วง edit freeze แล้วเทียบ snapshot เว็บจริงล่าสุดก่อน cutover
6. ใช้ `SECRET_KEY` และ `AUDIT_LOG_SIGNING_KEY` เดิมให้คงที่ และทำแผน rollback (D1 → JSON export)
7. ทดสอบ AR บนมือถือจริงหลัง deploy บน origin ที่ R2 CORS อนุญาต
8. พิจารณาเปลี่ยนเป็น token ที่จำกัดเฉพาะฐานนี้ (token ปัจจุบันเขียนได้ทุก D1 ในบัญชี)

## 5. ระบบผู้ดูแลหลายคน (ทำและทดสอบในเครื่องแล้ว — รอผู้ใช้อนุมัติก่อนแก้ schema บน Cloud D1)

แบบที่ผู้ใช้อนุมัติ: มีเจ้าของคนเดียวเป็นผู้สร้างลิงก์เชิญ ไม่มีการสมัครเอง และมี 4 สิทธิ์

| สิทธิ์ | ทำได้ |
| --- | --- |
| เจ้าของ (1 คน) | ทุกอย่าง และจัดการผู้ใช้ (เชิญ เปลี่ยนสิทธิ์ ระงับ สร้างลิงก์ตั้งรหัสใหม่ ยกเลิกลิงก์) |
| ผู้ดูแล | ทุกอย่าง ยกเว้นจัดการผู้ใช้ ดู audit ได้ |
| ผู้แก้ไขเนื้อหา | บันทึกแหล่งเรียนรู้ โมเดล สไลด์ โมเดลแนะนำ และเสียงบรรยาย ดูหน้าตั้งค่าได้แต่ฟอร์มถูกปิด |
| ผู้ตรวจ | ดูหน้า admin ได้อย่างเดียว ทุก POST ตอบ 403 (ยกเว้น logout) และฟอร์มถูกปิด |

- **ลิงก์:** ใช้ครั้งเดียว หมดอายุใน 48 ชม. D1 เก็บแค่ SHA-256 ของ token และหน้าผู้ใช้แสดงลิงก์ให้เจ้าของเห็นครั้งเดียว
  - การรับคำเชิญต้องมี CSRF และรหัสผ่านยาว ≥ 12 ตัว
  - ระบบ "ใช้ลิงก์" กับ "สร้างผู้ใช้" ใน transaction เดียว ถ้า username ซ้ำ ลิงก์จะยังใช้ต่อได้
- **ตรวจสิทธิ์ทุก request:** อ่านผู้ใช้จาก D1 ใหม่ทุกครั้ง การเปลี่ยนสิทธิ์จึงมีผลทันที ส่วนการระงับและรีเซ็ตรหัสจะเพิ่ม
  `session_version` ทำให้ session เดิมหลุดทันที
- **เจ้าของ:** แก้หรือระงับผ่านหน้าเว็บไม่ได้ ต้องเปลี่ยนด้วย `import_admin_to_d1.py --replace-existing <ชื่อเดิม>` เท่านั้น
- **audit:** ทุกรายการบันทึก `actor` และ `actor_role` ส่วนการจัดการผู้ใช้อยู่ใน category `users`
- **ไฟล์ใหม่:**
  - `cloudflare/d1/migrations/0002_admin_users.sql` เป็นการเพิ่มเท่านั้น และ copy บัญชีเดิมใน `admin_accounts` ไปเป็นเจ้าของ
  - `armodel/repositories/admin_users.py`
  - `templates/admin_users.html`, `admin_account_link.html`, `_auth_styles.html`
  - `scripts/apply_d1_migrations.py` (ค่าเริ่มต้นเป็น dry-run), `scripts/make_admin_hash.py`
  - `tests/test_admin_users.py`, `tests/admin_session.py`
- **Tests:** 175 passed, 116 subtests และ Worker 6 passed ทุกเส้นทาง `/admin` ถูกทดสอบว่ามีสิทธิ์กำกับ
- **Browser (5018):**
  - เจ้าของสร้างลิงก์ผู้ตรวจ → รับคำเชิญ → เข้าระบบเป็นผู้ตรวจ ฟอร์มถูกปิด 57 ปุ่ม และไม่มีเมนู audit/ผู้ใช้
  - เปิดลิงก์ซ้ำได้ 410 และผู้ตรวจเปิด `/admin/users` ได้ 403
- **Cloud D1 dry-run** (อ่านอย่างเดียว): ยังขาด `admin_users`, `admin_invites` **ยังไม่ได้ apply**
- **ผลหลัง apply:** บัญชี `test1234` จะกลายเป็นเจ้าของ แต่ผู้ใช้ลืมรหัส จึงต้องตั้งเจ้าของใหม่ด้วย `make_admin_hash.py` +
  `import_admin_to_d1.py --cloud --replace-existing test1234` (ต้องอนุมัติเช่นกัน)

### อัปเดต: apply migration 0002 บน Cloud D1 แล้ว (ผู้ใช้อนุมัติให้รัน 1 ครั้ง, 16 ต.ค. 2026)

- backup ก่อนรัน (อ่านอย่างเดียว): `C:\Users\fufu\ARModel-migration-sources\d1-export-before-0002\`
- รัน `python scripts/apply_d1_migrations.py --apply` 1 ครั้ง ผล: `Applied all migrations; owner: test1234`
- ตรวจกลับ:
  - เนื้อหาทั้ง 4 ชุดตรงกับ snapshot ทุกฟิลด์และชนิดข้อมูล (`verify_cloud_d1_readonly.py` PASS) และ FK 0 violations
  - export หลังรัน (`d1-export-after-0002`) มี SHA-256 **ตรงกับก่อนรันทุกไฟล์** ได้แก่ projects/models/site_settings/slider_items
    และ events analytics 540, audit 1, login 0
  - `dataset_versions` ทุกชุดยังเป็น 1 (ไม่มีการเขียนเนื้อหา) และ `admin_accounts` เดิมยังอยู่
- ตารางใหม่: `admin_users` มี 1 แถว (`test1234`, owner, active) ส่วน `admin_invites` มี 0 แถว
- ⚠️ ผู้ใช้ลืมรหัส `test1234` ต้องตั้งเจ้าของใหม่ด้วย `make_admin_hash.py` + `import_admin_to_d1.py --cloud --replace-existing test1234`
  ขั้นนี้ต้องอนุมัติแยก

### อัปเดต: ตั้งเจ้าของใหม่แทน test1234 (ผู้ใช้สั่งให้ Claude ทำแทน, 16 ต.ค. 2026)

- สุ่มรหัส 24 ตัวด้วย `secrets.token_urlsafe`
  - hash เก็บที่ `~/.armodel-secrets/admin-account.json`
  - รหัสสำหรับผู้ใช้เก็บที่ `~/.armodel-secrets/owner-login.txt`
  - ไม่ได้พิมพ์รหัสหรือ hash ใน chat หรือ log
- รัน `import_admin_to_d1.py --cloud --replace-existing test1234` 1 ครั้ง ได้เจ้าของคนใหม่คือ `phuphan-owner`
  - ใช้ row เดิม (`legacy-owner`) ต่อ
  - `session_version` เพิ่มเป็น 2 ทำให้ session เก่าหลุดทันที
- ตรวจกลับ:
  - รหัสใหม่ใช้ล็อกอินได้ และ `test1234` ใช้ไม่ได้แล้ว
  - เนื้อหาทั้ง 4 ชุดยังตรงทุกฟิลด์ และ `admin_accounts` เดิมยังอยู่ (runtime ไม่ใช้แล้ว)

## 6. เว็บทดสอบสำหรับทีมงาน (deploy แล้วตามที่ผู้ใช้อนุมัติ, 16 ต.ค. 2026)

- **ข้อมูลโปรเจกต์:**
  - Vercel project ใหม่ `phuphan-ar-review` (team `nitipat-s-projects`) สร้างและ deploy ผ่าน CLI
  - ไม่ได้ผูกกับ GitHub และ **ไม่ได้แตะโปรเจกต์หลัก `ar-model`** (https://phuphan-ar.vercel.app ยังตอบ 200)
  - URL: **https://phuphan-ar-review.vercel.app**
  - deployment `dpl_CYTAJTNay2mauzfVsgTLs4BbRsXA`
- **Env (production ของโปรเจกต์ใหม่ เข้ารหัสทั้งหมด และไม่แสดงค่า):**
  - `D1_ACCOUNT_ID`, `D1_DATABASE_ID`, `D1_API_TOKEN` (token DPAPI เดิมตามที่ผู้ใช้เลือก)
  - `SECRET_KEY`, `AUDIT_LOG_SIGNING_KEY` (สุ่มใหม่)
  - `SITE_BASE_URL=https://phuphan-ar-review.vercel.app`, `ARMODEL_STAGING=1`, `ARMODEL_ANALYTICS_ENABLED=0`
- **ฐานข้อมูล:** ใช้ Cloud D1 `armodel-production` ตามที่ผู้ใช้เลือก ทีมแก้ข้อมูลในหน้า admin จะกลายเป็นข้อมูลจริงทันที
- **`.vercelignore`:** ไม่อัปโหลด data/, docs/, tests/, scripts/, cloudflare/, *.md, config*.json และ .env
- **ตรวจหลัง deploy:**
  - `/`, `/home`, `/models`, หน้ารายละเอียดโมเดลและโครงการ, `/sitemap.xml`, `/api/settings`, `/admin/login` ตอบ 200
  - `/admin` ตอบ 302 ไปหน้า login
  - `/health` ได้ `{"database":"d1","media_storage":"r2","status":"ok"}`
  - `X-Robots-Tag: noindex, nofollow` และ robots `Disallow: /`
  - แถบ "เว็บไซต์ทดสอบ" เอาออกแล้วตามคำขอผู้ใช้ และ deploy ใหม่เป็น `phuphan-ar-review-p3kv6e755` แต่ยังกัน search engine index เหมือนเดิม
  - canonical และ og URL ชี้ไปที่โดเมน review
  - analytics ใน D1 ยังเป็น 540 หลังเปิดหน้า แปลว่าไม่บันทึกสถิติจากเว็บทดสอบ
- ⚠️ **โมเดล 3D ยังไม่โหลด:** R2 CORS ไม่ส่ง `Access-Control-Allow-Origin` ให้ `https://phuphan-ar-review.vercel.app`
  (ตรวจด้วย curl) ผู้ใช้ต้องเพิ่ม origin นี้ใน R2 bucket `phuphan-ar-assets` → Settings → CORS
- ⚠️ อัปโหลดไฟล์และสร้างเสียงบรรยายใช้ไม่ได้ เพราะยังไม่มี R2 credentials และ Gemini key ในโปรเจกต์นี้
- ⚠️ ยังไม่ได้ทดสอบการล็อกอินบนเว็บทดสอบ เพราะ Claude ไม่กรอกรหัสบนเว็บที่ไม่ใช่ localhost
  ผู้ใช้ต้องล็อกอินเองด้วยรหัสใน `~/.armodel-secrets/owner-login.txt`

## 7. ปรับ UI หน้าผู้ดูแลระบบใหม่ทั้งหมด (16 ต.ค. 2026) — แก้เฉพาะ template, CSS และ JS ฝั่งหน้าจอ

**ขอบเขต:** ไม่แก้ `app.py`, repository, route, ชื่อฟิลด์ฟอร์ม หรือ data-attribute ที่ script ใช้
(ยืนยันด้วยรายการไฟล์ที่เปลี่ยนในรอบนี้: `static/css/admin.css`, `static/js/admin-shell.js` (ใหม่),
`admin-read-only.js`, `admin-dashboard.js` (เปลี่ยนแค่คำ) และ template admin)

**หลักการที่ใช้ (อ้างอิง):**
- เมนูซ้ายแนวตั้งแบบเห็นตลอด จัดกลุ่ม ใช้ไอคอนคู่ข้อความ และไม่ซ่อนเมนูบน desktop
  ([NN/g Vertical Navigation](https://www.nngroup.com/videos/vertical-navigation/),
  [GitLab navigation sidebar](https://design.gitlab.com/patterns/navigation-sidebar/))
- ป้ายอยู่เหนือช่องกรอก ฟอร์มคอลัมน์เดียว ยกเว้นฟิลด์สั้นที่เกี่ยวข้องกันบนจอกว้าง
  ([NN/g Web Form Design](https://www.nngroup.com/articles/web-form-design/),
  [NN/g Form White Space](https://www.nngroup.com/articles/form-design-white-space/))
- WCAG 2.2 AA: ขนาดเป้ากด ≥ 24px (ใช้ 40–44px), focus ที่มองเห็นได้, ตัวอักษร contrast ≥ 4.5:1
  ([Deque WCAG 2.2](https://dequeuniversity.com/resources/wcag-2.2/))

**สิ่งที่เปลี่ยน:**
- **โครงหน้าใหม่ทุกหน้า admin:**
  - เมนูซ้ายจัดกลุ่มเป็น ภาพรวม / เนื้อหา / หน้าตาเว็บไซต์ / ระบบ
  - ท้ายเมนูมีการ์ดผู้ใช้ ปุ่มดูเว็บไซต์ และปุ่มออกจากระบบ ซึ่งตอนนี้เห็นตลอด (เดิมตกขอบจอที่ความสูง 900px)
- **มือถือ (≤ 960px):** มีแถบบนพร้อมปุ่มเมนู เปิดเป็นลิ้นชักพร้อมฉากหลัง ปิดได้ด้วย Esc หรือแตะนอกเมนู
  (เดิมเป็นแถบแนวนอนที่เห็นเมนูเดียว)
- **หน้าโมเดล/แหล่งเรียนรู้ (`/admin`):**
  - ตัดกล่องลิงก์ด่วน 4 กล่องที่ซ้ำกับเมนูออก
  - แบ่งเป็นแท็บ: รายการโมเดล, รายการแหล่งเรียนรู้, เพิ่มโมเดล, เพิ่มแหล่งเรียนรู้
  - มีปุ่มหลัก "เพิ่มโมเดล" ที่หัวหน้า
  - ความสูงหน้า desktop ลดจาก 10,796 px เหลือ 5,018 px และมือถือลดจาก 12,995 px เหลือ 11,046 px
- **ตาราง:**
  - ค้นหาได้ทันที และคำอธิบายแสดงไม่เกิน 2 บรรทัด
  - URL ไฟล์ยาวถูกตัดให้อยู่บรรทัดเดียว (ซ่อนบนมือถือ)
  - บนมือถือแสดงเป็นการ์ดที่มีชื่อคอลัมน์กำกับ
- **โมเดลแนะนำ:** เพิ่มช่องค้นหาและ "แสดงเฉพาะที่เลือกไว้" ทำงานฝั่งหน้าจอเท่านั้น ข้อมูลที่ส่งไปบันทึกยังเหมือนเดิม
- **ผู้ใช้และสิทธิ์:** แก้ปัญหาล้นจอแนวนอน (เดิมล้น 278px บน desktop และ 503px บนมือถือ) และฟอร์มเชิญมีป้ายกำกับครบ
- **ระบบดีไซน์เดียวทั้งหน้า admin:**
  - ปุ่ม 3 ระดับ: หลัก / รอง / ลบ
  - กล่องข้อความ 4 แบบ: สำเร็จ / ผิดพลาด / คำเตือน / ดูอย่างเดียว
  - ไอคอน SVG ชุดใหม่แทนไอคอนที่วาดด้วย CSS
- **ข้อความ:**
  - หัวข้อและป้ายเปลี่ยนเป็นภาษาไทย คงคำอังกฤษไว้ในวงเล็บเฉพาะศัพท์เทคนิค
  - คำว่า "โครงการ" เปลี่ยนเป็น "แหล่งเรียนรู้"
  - ลบข้อความเก่าที่ผิด ("บันทึกลงไฟล์ JSON", "บันทึกกลับไปยัง GitHub", "data/*.json … deploy ใหม่")
    แล้วใช้ข้อความสถานะที่ตรงความจริงเพียงชุดเดียว

**ผลตรวจ:**
- pytest 175 passed, 116 subtests และ Worker 6 passed
- `node --check` ผ่านทุกไฟล์
- Playwright ถ่ายภาพ 13 หน้า × 2 ขนาด (1440 / 390) ไม่มีหน้าไหนล้นจอแนวนอน
- ลิ้นชักเมนูเปิดและปิดด้วย Esc ได้
- ภาพเปรียบเทียบอยู่ใน `docs/review-screenshots/admin-ui/` (`*-before.jpg` / `*-after.jpg`)
- Deploy: `phuphan-ar-review-9mpc0tbuh` ขึ้น https://phuphan-ar-review.vercel.app แล้ว
  โดยไม่แตะโปรเจกต์หลัก `ar-model` (`admin.css` ของเว็บหลักยังเป็นไฟล์เดิม)
- ⚠️ ยังไม่ได้ทดสอบหน้า admin หลังล็อกอินบนเว็บทดสอบ ภาพทั้งหมดมาจากพรีวิว 5018 ในเครื่องที่ใช้โค้ดเดียวกัน

**ข้อเสนอที่ต้องแก้ backend (ยังไม่ทำ รอผู้ใช้อนุมัติ):**
1. แดชบอร์ดโหลดช้า (เกิน 4 วินาทีในเครื่อง) เพราะทุกครั้งจะตรวจ URL ใน R2 ทั้ง 121 รายการด้วย HEAD
   ควรตรวจเบื้องหลังหรือเก็บผลไว้นานกว่าเดิม
2. แดชบอร์ดยังมีตัวเลข "URL ของ Supabase" ที่เลิกใช้แล้ว ควรเอาออกจาก summary
3. หน้า 409 (มีคนแก้ก่อน) เป็นข้อความเปล่า และสิ่งที่กรอกไว้หายไป ควรกลับไปที่ฟอร์มพร้อมข้อความเตือนและเก็บค่าที่กรอกไว้
4. ฟอร์มโมเดลยังมีช่อง "Path ไฟล์โมเดลในเครื่อง" และ "Path รูปภาพปกหลัก" ซึ่งระบบ R2 อย่างเดียวไม่ใช้แล้ว
   เสนอให้ซ่อนหรือเอาออก แต่ backend ยังรับค่านี้อยู่ จึงต้องตัดสินใจร่วมกัน
5. ถ้ารายการโมเดลเกิน 200 รายการ ควรทำแบ่งหน้าฝั่ง server
6. หน้าต่างยืนยันการลบตอนนี้ใช้ `confirm()` ของ browser ถ้าต้องการให้เข้ากับดีไซน์ ทำเป็น dialog ฝั่ง UI ได้โดยไม่ต้องแก้ backend

### อัปเดต: แดชบอร์ดเร็วขึ้นและเอา metric Supabase ออก (ข้อเสนอ 1–2, ผู้ใช้อนุมัติ 16 ต.ค. 2026)

**เปลี่ยนใน backend (`app.py`):**
- `/admin/api/dashboard/summary` **ไม่ยิง HEAD ไป R2 แล้ว** ใช้เฉพาะผลที่ยังอยู่ใน cache (`dashboard_asset_cached`)
  และบอก `storage.pending_count` / `storage.checks_complete` ว่ายังเหลือไฟล์ที่รอตรวจกี่ไฟล์
- endpoint ใหม่ `/admin/api/dashboard/storage` (ต้องล็อกอิน ทุกสิทธิ์ที่ดูแดชบอร์ดได้) ตรวจไฟล์ R2 แล้วเก็บผลลง cache
- cache อยู่ได้ 30 นาที (เดิม 5 นาที) และตรวจพร้อมกันได้สูงสุด 24 ไฟล์ (เดิม 10)
- เอา `assets.supabase_urls` และ health `supabase_url_cleanliness` ออก
- refactor เป็น `dashboard_tracked_assets`, `dashboard_asset_checks`, `dashboard_storage_report` ใช้ร่วมกันทั้งสอง endpoint

**เปลี่ยนใน UI (`admin-dashboard.js`, `admin_dashboard.html`):**
- แสดงแดชบอร์ดทันที แผงพื้นที่จัดเก็บขึ้น "กำลังตรวจ…" ระหว่างรอ แล้วเรียก storage endpoint มาเติมทีหลัง
- ถ้าตรวจไม่สำเร็จ จะแสดงข้อความแจ้งในแผงนั้น ส่วนอื่นของหน้ายังใช้งานได้
- ไม่มีแถวและการ์ด Supabase แล้ว

**ผลวัดจริง (พรีวิว 5018 ข้อมูลจริง 121 ไฟล์ R2):**

| | ก่อน | หลัง |
| --- | ---: | ---: |
| summary ตอน cache ว่าง | 5.66 s | **0.03 s** |
| หน้าแดชบอร์ดแสดงผล (cache ว่าง) | ~5.7 s (รอทั้งหมด) | **0.26 s** |
| ตรวจไฟล์ R2 ครบ (ทำเบื้องหลัง) | 5.66 s (บล็อกหน้า) | 2.6–3.4 s |
| อายุ cache | 5 นาที | 30 นาที |

**Tests:** 178 passed, 117 subtests และ Worker 6 passed เพิ่ม test ที่ยืนยันว่า:
- summary ไม่เรียก HEAD เลย และบอก pending
- storage endpoint ตรวจครบแล้วเติม cache ได้
- cache หมดอายุที่ 30 นาที
- หน้า dashboard ชี้ไปที่ storage endpoint และ JS ไม่มีคำว่า supabase

**Deploy:**
- `phuphan-ar-review-6dy0jf9qz` ขึ้น https://phuphan-ar-review.vercel.app แล้ว
- API ทั้งสองตัวต้องล็อกอินก่อน (ส่งต่อไปหน้า login ด้วย 302)
- ไม่ได้แตะโปรเจกต์หลัก `ar-model`
- ⚠️ ยังไม่ได้ทดสอบหลังล็อกอินบนเว็บทดสอบ
- ⚠️ cache อยู่ในหน่วยความจำของแต่ละ instance บน Vercel ถ้า instance เริ่มใหม่ การตรวจไฟล์จะเริ่มใหม่
  แต่ไม่ทำให้หน้าเว็บช้าแล้ว เพราะทำเบื้องหลัง

## 8. ข้อ 6 ของอาจารย์: คำอธิบายโมเดลจากข้อมูลศูนย์ภูพานเท่านั้น (17 ต.ค. 2026)

- **แหล่งข้อมูล:** ใช้เฉพาะเว็บและเอกสารของศูนย์บน puparn.rid.go.th รายละเอียดและหน้าที่มาอยู่ใน `docs/MODEL_DESCRIPTIONS_DRAFT.md`
- **บันทึกลง Cloud D1 แล้ว (ผู้ใช้อนุมัติ):**
  - เขียนใหม่ 19 โมเดล
  - เติมประโยคเสริม 7 โมเดลเห็ด
  - ไม่รวมไก่ดำภูพาน 3 และ 4
  - ใช้ `scripts/apply_model_descriptions.py --cloud --apply` ซึ่งมี revision guard และตรวจซ้ำในตัว
- **backup:**
  - ก่อนบันทึก: `C:\Users\fufu\ARModel-migration-sources\d1-export-before-descriptions-20261017\`
  - หลังบันทึก: `C:\Users\fufu\ARModel-migration-sources\d1-export-after-descriptions-20261017\`
- **ตรวจกลับ:**
  - projects, site_settings และ slider_items เหมือนเดิมทุก byte
  - models เปลี่ยนเฉพาะฟิลด์ `description` 26 รายการ (revision 1 → 2) ลำดับและ ID เหมือนเดิม
  - เครดิตรูปเดิม (สุกรภูพาน, ปลานิลแดง) ยังอยู่
  - หน้าเว็บทดสอบแสดงข้อความใหม่ 8/8 หน้าที่สุ่มตรวจ
- **Tests:** 179 passed, 117 subtests
- ⚠️ `data/models.json` (snapshot) ไม่ได้แก้ตามข้อห้าม ดังนั้น `verify_cloud_d1_readonly.py`
  จะแจ้งว่า description 26 รายการไม่ตรงกับ snapshot ซึ่งเป็นผลที่ตั้งใจ
- ⚠️ มี 3 โมเดลที่ข้อความสั้นลง (ข้าวภูพาน 1, รวงข้าวสกลนคร, ต้นยางพารา) เพราะตัดข้อความที่หาที่มาในเอกสารศูนย์ไม่ได้ออก
- ⚠️ เสียงบรรยายเดิมของโมเดลที่เปลี่ยนจะไม่ตรงกับข้อความใหม่ ต้องสร้างเสียงใหม่ (ต้องมี Gemini key)
- **รอยืนยันกับศูนย์:** ไก่ดำภูพาน 3/4, ไหมนางสิ่ว/นางตุ่ย, กระต่ายดำ
- **ไม่มีข้อมูลในแหล่งของศูนย์:** มะไฟ, กระเป๋าผ้าไหม 2 แบบ, เห็ดนางรมทอง, เห็ดพื้นเมือง 6 ชนิด

