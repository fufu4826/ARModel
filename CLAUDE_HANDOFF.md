# ส่งต่องาน ARModel ให้ Claude ตรวจสอบ

วันที่จัดทำ: 16 ตุลาคม 2026 (Asia/Bangkok)

## 1. คำสั่งสำหรับ Claude

คุณรับช่วงเป็นผู้ตรวจงานโครงการนี้ ให้เริ่มจากอ่านโค้ดและรายงานข้อบกพร่องก่อน
อย่าแก้ไขอัตโนมัติจากข้อสงสัยที่ยังไม่มีหลักฐาน และอย่าอ้างว่าพร้อม production
เพียงเพราะ tests ผ่าน ผู้ใช้ต้องการรู้ว่างานที่ Codex ทำมีอะไรบ้างและบกพร่องตรงไหน

รูปแบบรายงานที่ต้องการ:

1. Findings เรียงระดับ P0/P1/P2/P3 พร้อมไฟล์ บรรทัด หลักฐาน ผลกระทบ และวิธีทำซ้ำ
2. แยกข้อบกพร่องที่พิสูจน์แล้วออกจากความเสี่ยง/สมมติฐานและสิ่งที่ยังไม่ทดสอบ
3. ระบุข้อมูลที่อาจสูญหายหรือยังไม่ได้ย้าย และเงื่อนไขก่อน cutover
4. สรุปผลทดสอบที่รันเองจริง ห้ามนำผลเก่ามาอ้างว่าเป็นการทดสอบรอบใหม่
5. เสนอแนวแก้ที่เล็กและตรงจุด แล้วรอผู้ใช้อนุมัติก่อนแก้หรือขึ้นระบบจริง

## 2. โฟลเดอร์นี้คืออะไร

โฟลเดอร์งานจริงสำหรับรีวิว:

`C:\Users\fufu\ARModel-review-20261016`

เป็นสำเนา shallow clone แยกจาก GitHub เพื่อปรับเว็บไซต์ศูนย์ภูพานและย้ายการเก็บข้อมูล
เว็บไซต์ใช้ Flask, Jinja, CSS/JavaScript, Swiper และ model-viewer สำหรับ 3D/AR
มีหน้าแหล่งเรียนรู้ รายการโมเดล รายละเอียดโมเดล เสียงบรรยาย และหน้าผู้ดูแลระบบ

- Remote: `https://github.com/fufu4826/ARModel.git`
- Branch ปัจจุบัน: `review/phuphan-content-admin-login`
- HEAD: `4108ead460a773904be7b0f6590d53561cd5b48a`
- Commit message: `Clarify production rollback documentation`
- งานทั้งหมดหลัง clone ยังเป็น uncommitted changes รวมไฟล์ untracked จำนวนมาก
- `git rev-list --count main..HEAD` เคยตรวจได้ 0 ยังไม่มี commit งานใหม่

โฟลเดอร์อื่นที่ต้องแยกให้ออก:

- `C:\Users\fufu\ARModel`: checkout เดิม อยู่ main ตรวจล่าสุดสะอาด ไม่ใช่ที่แก้ชุดนี้
- `C:\Users\fufu\ARModel-review-20261016-incomplete`: clone ครั้งแรกที่ไม่สำเร็จ
  ไม่ใช่งานปัจจุบัน การลบเคยถูก policy ปฏิเสธ อย่าลบ/ใช้แทนโดยพลการ
- เส้นทาง `F:\phuphan\ARModel` เป็นเส้นทางที่ผู้ใช้กล่าวถึงตอนต้น ไม่พบในเครื่องนี้

## 3. ข้อห้ามและการรักษางาน

- ห้าม `git reset --hard`, `git clean`, checkout ทับไฟล์ หรือทิ้ง untracked files
- ห้าม commit, push, merge main, deploy Vercel/Worker หรือสลับเว็บจริงโดยไม่ได้รับอนุมัติ
- ห้ามแก้ production environment หรือหมุน/ลบ token เดิมของ R2
- ห้ามเปิดเผย token/password/hash ลง chat, report, screenshot, log หรือ Git
- ห้ามลบ JSON ต้นทางหรือไฟล์ R2 เดิม เพียงเพราะ runtime ใหม่ไม่ใช้ JSON แล้ว
- ห้ามรัน importer ซ้ำเพื่อเขียนทับ D1 ที่มีข้อมูลอยู่
- บัญชีผู้ดูแลต้องใช้ username + password hash ห้ามสร้าง default password เอง
- ตัวนับโครงการและโมเดลต้องคำนวณจากข้อมูล ไม่ hard-code 10 หรือ 41
- การอนุมัติสร้าง D1 และย้ายข้อมูลไม่ใช่การอนุมัติ deploy เว็บ

## 4. สิ่งที่ Codex ทำก่อนงานฐานข้อมูล

1. เพิ่มคำแนะนำเปิดไฟล์ GLB ด้วย Blender และขั้นตอน import glTF
2. เพิ่มข้อมูลสถานที่ เบอร์โทร ลิงก์แผนที่ และที่มาของข้อมูลศูนย์ภูพาน
3. เพิ่มบทสรุปบทบาท/ภารกิจของศูนย์ พร้อมแหล่งอ้างอิง กปร.
4. เพิ่มคำแนะนำ AR ขั้นตอนใช้งาน เงื่อนไขอุปกรณ์ และข้อความเมื่อใช้งานไม่ได้
5. ขยายคำอธิบายผ้าไหมย้อมคราม โดยแยกเรื่องเส้นไหมและการย้อมคราม
   และเติมคำอธิบายโมเดลต้นยางพาราที่ว่างอยู่
6. เปลี่ยนหน้าล็อกอินให้ตรวจ username และ password ฝั่ง server

ข้อที่ตั้งใจยังไม่แก้: เนื้อหาสไลด์กลางซ้ำกัน ตามที่ผู้ใช้ระบุว่ายังไม่แก้ข้อ 3
ไม่ได้ทำ factual audit ครบทุกโมเดล และไม่ได้สร้างเสียงบรรยายใหม่ให้ตรงคำอธิบายที่แก้
ข้อมูลเบอร์โทรเป็นข้อมูลจากแหล่งอ้างอิง ไม่ได้โทรยืนยันจริง
การทดสอบ AR บนอุปกรณ์จริงยังไม่ทำ อย่าสรุปจาก desktop/browser ว่า AR มือถือผ่าน
งาน mobile slider เป็นบริบทต้นเรื่อง ไม่ควรสรุปว่าปัญหาทุก viewport ได้รับการแก้ใหม่
ในรอบย้ายฐานข้อมูลนี้ ต้องตรวจ CSS และ screenshot ตามหลักฐานจริง

## 5. สถาปัตยกรรมใหม่

- D1: projects, models, slider_items, site_settings, admin_accounts, events
- events แยก analytics, audit และ login/rate-limit
- R2: GLB รูปภาพ เสียงบรรยาย และไฟล์เสียงร่าง
- Flask: render, auth, CSRF, validation, API และหน้าดู 3D/AR
- เชื่อม D1 ได้สองแบบ: private Worker gateway หรือ Cloudflare REST API โดยตรง
- credentials อยู่เฉพาะ server ไม่ส่งให้ frontend
- ลบ service บันทึกข้อมูลผ่าน GitHub แล้ว
- runtime ไม่อ่าน/เขียนไฟล์ JSON เป็นฐานข้อมูล และไม่มี JSON fallback
- path ชื่อ `*.json` ใน app.py บางแห่งยังเป็น compatibility table selectors
  ไม่ใช่การเปิดไฟล์จริง ให้ตรวจ call graph ไม่ตัดสินจากชื่อเพียงอย่างเดียว
- SQL บางคอลัมน์เป็น JSON สำหรับ structured details/gallery/events
  และ HTTP ใช้ JSON serialization ได้ ไม่ใช่การกลับไปใช้ไฟล์ JSON เก็บฐานข้อมูล
- SQLite/local media adapter เหลือไว้เฉพาะ TESTING ไม่ใช่ production fallback

กลไกที่เพิ่ม: parameter binding, FK, unique IDs/slugs, atomic batches,
dataset revision guard, stale-write HTTP 409, database failure HTTP 503,
login rate-limit failure แบบ fail closed และ signed audit event storage ใน D1

## 6. D1 บน Cloudflare ที่สร้างและนำเข้าแล้ว

- Account ID: `7166a0c3703b6e795739064e6ab3be35`
- Database name: `armodel-production`
- Database ID: `c9fc6704-2f9a-403d-a81a-62999457d21f`
- เป็นฐานใหม่ที่เตรียมไว้ ยังไม่ได้สลับเว็บ production มาใช้

นำเข้าจากไฟล์ใน clone นี้ครบ 4 ชุด:

| ชุดข้อมูล | จำนวน |
| --- | ---: |
| projects | 10 |
| models | 41 |
| site_settings | 31 |
| slider_items | 2 |

ตรวจอ่านกลับและเทียบทุก original field แล้ว ไม่ใช่แค่จำนวนแถว
รวมลำดับ ID ข้อความไทย รูป เสียง URL ค่า rotation/scale และ visibility
SHA-256 ต้นทางอยู่ใน `docs/D1_CLOUD_VERIFICATION.md`
ข้อมูลนี้รวมการแก้คำอธิบายสองโมเดลใน branch ไม่ใช่ fresh export ของเว็บจริง

การ import ครั้งแรกเจอ REST API bind boolean ทำให้ CHECK constraint ล้มเหลว
transaction rollback ทั้งชุด จากนั้นแก้ส่ง bool เป็น SQL integer และ import สำเร็จ
ตรวจ cloud FK rollback และ stale revision rollback แล้วไม่มี probe row ค้าง

สิ่งที่ยังไม่ได้ย้าย:

- บัญชีผู้ดูแลจริง: root config.json ว่าง ไม่มี credential ให้ import
- ประวัติ production analytics/audit/login ที่อาจอยู่ใน R2 หรือระบบเดิม
- ข้อมูลที่เว็บจริงเปลี่ยนหลัง clone ต้องตรวจ snapshot ล่าสุดก่อน cutover

อย่าเรียกสิ่งเหล่านี้ว่า migrated ครบโดยไม่มีหลักฐาน

## 7. Credentials และ R2

ไฟล์ secret อยู่นอก repository:

- `C:\Users\fufu\.armodel-secrets\cloudflare-d1-token.dpapi`
- `C:\Users\fufu\.armodel-secrets\d1-target.toml` มีเฉพาะ target IDs

D1 token ถูกเก็บด้วย Windows CurrentUser DPAPI ใช้ได้ภายใต้บัญชี Windows เดิม
โทเคนชื่อ `ARModel production D1`, D1 Write ระดับทั้งบัญชี อายุ 90 วัน
หมดอายุ 15 มกราคม 2027 เวลาไทย ไม่มีสิทธิ์ deploy Worker/DNS/R2
เคยตรวจ token verify และ list D1 ผ่าน อย่า print ค่าเพื่อเช็ค

R2 bucket เดิม: `phuphan-ar-assets` มี token production เดิม Active
แต่ยังไม่มี secret สำหรับอัปโหลดในเครื่อง และไม่ได้หมุน/ยกเลิก token เดิม
Public reads/CORS ผ่าน ไม่ใช่หลักฐานว่า R2 writes ผ่าน
การทดสอบ upload ใน integration ใช้ mock ต้องระบุให้ชัด

## 8. ไฟล์ที่ควรอ่านตามลำดับ

1. `README.md`
2. `docs/D1_CLOUD_VERIFICATION.md`: สถานะล่าสุด หลักฐานและ release gates
3. `app.py`: เส้นทาง runtime/auth/upload/analytics/audit/error handling
4. `armodel/repositories/database.py`: gateway/direct REST/SQL/test adapter
5. `cloudflare/d1/migrations/0001_initial.sql`: schema/index/trigger
6. `cloudflare/d1/worker.mjs` และ `worker.test.mjs`: gateway policy
7. `armodel/repositories/content.py`, `armodel/services/audit.py`
8. `scripts/migrate_to_d1.py`, `prepare_cloud_d1.py`, `validate_cloud_d1.py`
9. `scripts/import_admin_to_d1.py`, `import_d1_events.py`
10. `tests/test_database_repository.py`, `test_production_admin_writes.py`,
    `test_site_management.py`, `test_audit_service.py`, `test_admin_dashboard.py`
11. templates/CSS/JS และ data/models.json ใน diff สำหรับงานเนื้อหาก่อนหน้า

เอกสารเก่า `docs/D1_R2_MIGRATION.md` อธิบายช่วง local emulation และมี notice
ให้ใช้รายงาน cloud ล่าสุดแทน ส่วน `docs/REVIEW_20261016.md` เป็นงาน UI ระยะก่อนหน้า
เอกสาร production เก่าที่กล่าวถึง JSON/GitHub persistence เป็นประวัติ ไม่ใช่คู่มือ deploy ใหม่นี้

## 9. ระบบพรีวิวที่เปิดอยู่ ณ เวลาส่งต่อ

ตรวจ listener ล่าสุด:

| URL/Port | หน้าที่ | PID ที่ตรวจพบ |
| --- | --- | ---: |
| http://127.0.0.1:5017/home | Flask อ่าน Cloud D1 จริง | 5988 |
| http://127.0.0.1:5016/home | Flask อ่าน Wrangler local D1 รุ่นก่อน | 22952 |
| http://127.0.0.1:8787 | Wrangler local Worker/D1 | 18968 |

PID อาจเปลี่ยนได้ ต้องตรวจ command line ก่อนหยุด process ใด ๆ
พรีวิวหลักล่าสุดคือ 5017 ไม่ใช่ 5016; โค้ดที่ server 5016 โหลดอาจเก่ากว่าไฟล์ปัจจุบัน
5017 ใช้ ephemeral Flask session secret สำหรับรีวิว ไม่ใช่ production secret
Log: `%TEMP%\armodel-cloud-review-5017.out.log` และ `.err.log`

เปิดใหม่ถ้า server หยุดแล้ว:

```powershell
Set-Location C:\Users\fufu\ARModel-review-20261016
python scripts\run_cloud_d1_review.py
```

อย่าเปิดซ้ำทับ port ที่ใช้อยู่ อย่าตั้ง debug=True บน cloud credential

## 10. ผลทดสอบที่ Codex รันจริง

- `python -m pytest -q --tb=short`: 135 passed, 79 subtests passed
- `node --test cloudflare\d1\worker.test.mjs`: 5 passed
- `node --check static\js\site-carousel.js`: ผ่าน
- `python scripts\validate_zero_supabase_data.py`: ผ่าน และ R2 URLs 121 รายการผ่าน
- `python scripts\validate_cloud_d1.py`: ทุก source field ผ่าน, FK/stale batch rollback ผ่าน
- Flask 7 routes ผ่านขณะบล็อก JSON/JSONL file access: `/`, `/home`, `/models`,
  `/admin/login`, `/health`, model detail และ project detail อย่างละหนึ่ง
- `/health` ล่าสุด: database=d1, media_storage=r2, status=ok
  label media_storage ระบุ backend ไม่ได้ตรวจ credential/write R2
- `git diff --check`: ผ่าน
- checkout เดิมสะอาด และยังไม่มี commit/push/deploy

คำสั่งที่รันซ้ำได้แบบ local:

```powershell
python -m pytest -q --tb=short
node --test cloudflare\d1\worker.test.mjs
node --check static\js\site-carousel.js
git diff --check
```

`validate_cloud_d1.py` ใช้ cloud จริง มี deliberate failing write transactions
เพื่อพิสูจน์ rollback ไม่ใช่ read-only ล้วน ให้ขออนุมัติก่อนทดสอบ cloud ซ้ำ
ตัวตรวจ URL ใช้ network HEAD/GET ส่วน import scripts มีผลเขียนข้อมูลจริง
อย่ารัน `prepare_cloud_d1.py --create --import-snapshot` ซ้ำโดยไม่ตรวจปลายทาง

## 11. หลักฐานภาพ

อยู่ใน `docs/review-screenshots/`:

- `cloud-d1-home-5017.png`: หน้าเว็บอ่าน Cloud D1 ล่าสุด
- `cloudflare-d1-token-active.png`: สถานะ token ไม่มี secret
- `d1-home-runtime.png`: พรีวิว local D1 ระยะก่อนหน้า
- `home-360.png`, `home-390.png`, `home-480.png`, `home-1280.png`
- `model-ar-360.png`, `model-file-360.png`, `admin-login-360.png`

ภาพชุดก่อนหน้า home/model ใช้ Opera Chromium CDP; admin-login ใช้ IAB
ภาพ cloud-D1 ใช้ GPT in-app browser ไม่ใช่ Chrome mobile emulation หรือมือถือจริง
Screenshot ไม่ได้พิสูจน์ popup/swipe/AR แบบ end-to-end
เคยพบ horizontal overflow ประมาณ 15px ที่ 320px ใน baseline เดิมด้วย ยังไม่ได้แก้

## 12. จุดเสี่ยงที่ขอให้ Claude ตรวจเป็นพิเศษ

รายการนี้เป็น review targets ไม่ใช่ยืนยันว่าทุกข้อเป็น bug:

1. ความครบถ้วนของ migration: compare field/type/order, foreign keys และไฟล์สื่ออ้างอิง
2. Runtime path ทุกจุดต้องไม่กลับไปอ่าน/เขียน JSON หรือ GitHub โดยเฉพาะ error paths
3. Direct D1 REST: partial failure, ambiguous timeout, malformed response, parameter types,
   transaction atomicity และการแยก config ระหว่าง gateway/direct/test
4. Lost updates: revision guard ครอบคลุม HTML forms, AJAX และ multi-dataset mutations หรือไม่
5. Login/setup: username check, rate limiting, CSRF, session และความเสี่ยง first setup
   โดยเฉพาะการเปิด localhost preview ที่เชื่อมฐาน cloud แต่ยังไม่มี admin account
6. ตรวจว่า token/hash ไม่รั่วผ่าน exception chain, subprocess, template, JS หรือ logs
7. R2 upload/delete/draft lifecycle: ไม่มี local fallback และไม่ลบไฟล์จริงก่อน DB commit
8. Audit: failure หลัง content save, signature compatibility, retention และ history import
9. Batch scaling: Worker จำกัด 500 statements แต่ repository ยังบันทึกทั้ง collection
10. Analytics อ่านล่าสุด 10,000 events ไม่ใช่ SQL aggregation สำหรับข้อมูลปริมาณมาก
11. Admin import scripts CLI ยังจำกัด loopback gateway แม้ runtime direct REST รองรับ cloud
    ต้องตรวจ release tooling ไม่สรุปว่า cloud account migration พร้อมแล้ว
12. ตรวจ schema initialization/recovery หาก provisioning ล้มหลังสร้าง DB ก่อนบันทึก metadata
13. ตรวจ freshness ของข้อมูลจริงก่อน cutover และวิธี rollback โดยไม่สูญข้อมูลที่เขียนใหม่
14. UI mobile/title/slider arrows/popup/swipe, desktop hover และ landing regression
15. เนื้อหาบางโมเดลยังอาจมีข้อกล่าวอ้างที่ต้องตรวจหลักฐาน เสียงเดิมอาจไม่ตรงคำอธิบายใหม่

## 13. แหล่งบริบทเพิ่มเติม

Codex session transcript ในเครื่อง:

`C:\Users\fufu\.codex\sessions\2026\07\12\rollout-2026-07-12T01-39-59-019f527a-ada2-7383-97b0-d9bd60ba9823.jsonl`

คำเตือน: transcript อาจมีข้อมูลลับจากผลหน้าเว็บ อย่า paste/upload ทั้งไฟล์
ให้ใช้ไฟล์ส่งต่อนี้และโค้ดก่อน อ่าน transcript เฉพาะส่วนที่จำเป็นและห้ามเผยแพร่ credentials

## 14. เกณฑ์จบการตรวจ

รายงานข้อบกพร่องพร้อมหลักฐานให้ผู้ใช้ตัดสินใจ ไม่ deploy แทนผู้ใช้
ต้องกล่าวตรง ๆ ว่า local tests ผ่านส่วนใด cloud ผ่านส่วนใด และอะไร NOT TESTED
ขณะส่งต่อนี้: ย้าย snapshot ขึ้น D1 แล้ว แต่ยังไม่ใช่ production cutover ที่เสร็จสมบูรณ์

## 15. อัปเดตจาก Claude (16 ต.ค. 2026, หลังตรวจรอบแรก)

รายละเอียดเต็มอยู่ใน `docs/CLAUDE_REVIEW_20261016.md`; ส่วนนี้แก้ข้อความด้านบนที่ไม่ตรงความจริงแล้ว

- **ข้อ 6/§14 ไม่ตรงแล้ว:** Cloud D1 มีบัญชีผู้ดูแล `test1234` ซึ่งสร้างผ่าน first-run ของพรีวิว 5017
  เวลา 15:56 น. (ยืนยันด้วย SELECT แบบอ่านอย่างเดียว ไม่ได้อ่าน hash) ยังไม่ได้แตะบัญชีนี้
- Cloud D1 มี event ทดสอบจาก localhost: analytics 2 รายการ และ audit 1 รายการ ยังไม่ได้ล้าง
- **§9 ไม่ตรงแล้ว:**
  - พรีวิว 5017 ถูกหยุดแล้ว (PID 5988 ตรวจ command line ก่อนหยุด)
  - พรีวิวใหม่สำหรับตรวจ UI อยู่ที่ http://127.0.0.1:5018 (`scripts/run_snapshot_review.py` ใช้ SQLite ชั่วคราว ไม่ต่อ cloud)
  - 5016 และ 8787 (local D1) ยังรันอยู่ แต่โหลดโค้ดรุ่นเก่า
- แก้แล้ว:
  - ปิด first-run ผ่านเว็บนอก TESTING และใส่ CSRF ให้ login
  - เพิ่ม `--cloud` ให้ import scripts
  - อ่านตารางเนื้อหาด้วย batch เดียว
  - ปิด analytics ในพรีวิว cloud
  - แก้ narration cleanup และไม่ลบเสียงเดิมใน R2
  - แยก env ของ tests
  - D1 ล้มตอนเตรียมฟอร์ม admin ตอบ 503
  - schema recovery
  - header มือถือ
  - ลำดับคำแนะนำ AR บนมือถือ
- Tests ล่าสุดที่รันเอง: 153 passed, 82 subtests; Worker 5 passed
- Cloud D1 เทียบ snapshot ทุกฟิลด์และชนิดข้อมูลด้วย `scripts/verify_cloud_d1_readonly.py`: ผ่าน
- ยังไม่มี commit, push, merge, deploy หรือการเขียนลง cloud
- ย้าย analytics ประวัติจาก R2 `analytics/analytics_events.json` (538 events, 11 ก.ค.–9 ส.ค. 2026) เข้า Cloud D1 แล้ว
  ตามคำสั่งผู้ใช้ ตรวจกลับครบ 538/538 สำเนาต้นทางอยู่ที่ `C:\Users\fufu\ARModel-migration-sources\r2-analytics\`
  JSON ใน repository และ R2 ยังเก็บไว้ครบ runtime ไม่อ่านไฟล์เหล่านี้ ยังขาด events หลัง 9 ส.ค. ที่ต้องใช้ R2 credentials
- รอบเตรียมขึ้นจริง (ยังไม่ deploy ตามที่ผู้ใช้สั่ง — Vercel มีงานหลักที่ใช้งานอยู่ ห้ามทับ):
  - บังคับ revision ทุก admin save (P2-3)
  - analytics timeout เหลือ 3 วินาที
  - เพิ่ม `scripts/export_d1_snapshot.py` สำหรับ rollback/backup (อ่านอย่างเดียว ไม่ export hash)
  - `origin/main` ยังเป็น `4108ead` เว็บจริงจึงไม่มี commit ข้อมูลใหม่หลัง clone
  - Tests: 158 passed, 82 subtests
- Vercel: CLI ติดตั้งแล้วแต่ยังไม่ล็อกอิน และไม่มี token ในเครื่อง ผู้ใช้ต้องล็อกอินเอง และต้องอนุมัติแยกก่อน deploy
- ระบบผู้ดูแลหลายคน (เจ้าของ/ผู้ดูแล/ผู้แก้ไขเนื้อหา/ผู้ตรวจ ใช้ลิงก์เชิญจากเจ้าของ) ทำและทดสอบในเครื่องเสร็จแล้ว (175 passed)
  migration `0002_admin_users.sql` ยังไม่ apply บน Cloud D1 ต้องรออนุมัติ (`scripts/apply_d1_migrations.py --apply`)
- Vercel CLI ล็อกอินเป็น kafu4826-2401 แล้ว ห้าม logout ยังไม่ได้สร้างโปรเจกต์ `phuphan-ar-review` และยังไม่ deploy
- Cloud D1: apply migration 0002 แล้ว (admin_users/admin_invites) เนื้อหาและ events มี hash ตรงกับก่อน apply ตอนนี้เจ้าของคือ test1234 (ผู้ใช้ลืมรหัส)
- เจ้าของ Cloud D1 ตอนนี้คือ phuphan-owner (รหัสอยู่ใน ~/.armodel-secrets/owner-login.txt) แทน test1234 แล้ว
- Staging: https://phuphan-ar-review.vercel.app (Vercel project phuphan-ar-review ไม่ผูก Git) ใช้ Cloud D1 จริง ARMODEL_STAGING=1 analytics ปิด โปรเจกต์หลัก ar-model ไม่ได้แตะ ยังต้องเพิ่ม R2 CORS ให้โดเมนนี้
- เอาแถบ 'เว็บไซต์ทดสอบ' ออกจากเว็บทดสอบแล้ว (ยังคง noindex) และ deploy ใหม่เฉพาะ phuphan-ar-review
- ปรับ UI หน้า admin ใหม่ทั้งหมด (template/CSS/JS เท่านั้น ไม่แตะ backend) แล้ว deploy เฉพาะ phuphan-ar-review รายละเอียดอยู่ในหัวข้อ 7 ของ docs/CLAUDE_REVIEW_20261016.md
- แดชบอร์ด: summary ไม่รอ R2 แล้ว (0.03s) มี /admin/api/dashboard/storage ตรวจไฟล์เบื้องหลัง cache 30 นาที และเอา metric Supabase ออก deploy แล้วเฉพาะ phuphan-ar-review
- ข้อ 6: บันทึกคำอธิบายโมเดล 26 รายการจากข้อมูลศูนย์ภูพานลง Cloud D1 แล้ว (description อย่างเดียว ตรวจกลับแล้ว) รายละเอียดอยู่ในหัวข้อ 8 ของ docs/CLAUDE_REVIEW_20261016.md
