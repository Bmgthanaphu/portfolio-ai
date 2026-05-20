# Portfolio AI 🤖

ระบบ AI วิเคราะห์หุ้น สไตล์ Nick Sleep — ตัดสินใจแทน บอกชัดว่าซื้อ/ขาย/ถือ

## Setup (ทำครั้งเดียว)

### 1. Fork repo นี้
กด Fork ที่มุมขวาบน

### 2. ตั้ง GitHub Secrets
ไปที่ `Settings → Secrets and variables → Actions → New repository secret`

| Secret | ค่า |
|--------|-----|
| `GEMINI_API_KEY` | Gemini API key ของคุณ |
| `TELEGRAM_TOKEN` | Token จาก @BotFather (สร้างใหม่หลัง revoke) |
| `TELEGRAM_CHAT_ID` | Chat ID ของคุณ (จาก @userinfobot) |

### 3. เปิด GitHub Pages
`Settings → Pages → Source: Deploy from branch → Branch: main → / (root)`

### 4. รัน workflow ครั้งแรก
`Actions → Portfolio AI → Run workflow → mode: weekly`

### 5. เปิด dashboard
`https://[username].github.io/[repo-name]/`

---

## การใช้งาน

### Dashboard
- **Cash**: กรอกเงินสดที่มีแล้วกด Update — ระบบจะคำนวณให้
- **Holdings**: คลิก row เพื่อดู thesis + kill conditions
- **Watchlist**: เพิ่ม/ลด ticker ได้เองบน dashboard

### Telegram
ระบบจะแจ้งอัตโนมัติเมื่อ:
- มีคำแนะนำรายสัปดาห์ (เสาร์ 09:00 น.)
- มีข่าวด่วนที่กระทบ thesis
- หุ้นในพอร์ตขึ้น/ลงเกิน 5%
- Earnings ออก

### รัน manual
`Actions → Portfolio AI → Run workflow`
- `scan` — เช็คข่าวด่วน
- `weekly` — วิเคราะห์เต็มรูปแบบ
- `earnings` + ticker — เช็คหลัง earnings ออก

---

## Schedule (เวลาไทย)

| เวลา | วัน | Mode |
|------|-----|------|
| 08:00 น. | จ-ศ | Overnight news scan |
| 20:00 น. | จ-ศ | Pre-market briefing |
| 03:30 น. | จ-ศ | After-market summary |
| ทุกชั่วโมง | จ-ศ | Lightweight scan |
| 09:00 น. | เสาร์ | Weekly review |

---

## ⚠️ สำคัญ
- ระบบนี้ให้คำแนะนำเท่านั้น ไม่ได้เชื่อมกับ broker โดยตรง
- คุณต้องกดซื้อ/ขายเองผ่าน broker
- ไม่ใช่คำแนะนำทางการเงินอย่างเป็นทางการ
