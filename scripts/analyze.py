#!/usr/bin/env python3
"""
Portfolio AI - Main Analysis Script
Timezone: Asia/Bangkok (UTC+7) | Market: NYSE/NASDAQ (UTC-4/5)
"""

import os, json, sys, time, datetime, requests
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
DATA_DIR   = BASE_DIR / "data"
THESIS_DIR = BASE_DIR / "docs" / "thesis"
THESIS_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5731895043")
THB_RATE        = float(os.environ.get("THB_RATE", "36"))
OPENAI_MODEL    = "gpt-4o-mini"
THAI            = "ตอบเป็นภาษาไทยทุกส่วน ยกเว้น ticker หุ้น ตัวเลข และคำศัพท์เทคนิคเช่น thesis, kill condition, bull/bear case"

MODE = sys.argv[1] if len(sys.argv) > 1 else "scan"


# ── AI ───────────────────────────────────────────────────────────────────────
def call_ai(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return "Error: ไม่มี OPENAI_API_KEY"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload  = {"model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3}
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions",
                          headers=headers, json=payload, timeout=40)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error: {e}"


# ── Helpers ──────────────────────────────────────────────────────────────────
def load_portfolio():
    with open(DATA_DIR / "portfolio.json") as f:
        return json.load(f)

def save_portfolio(data):
    with open(DATA_DIR / "portfolio.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_ai_portfolio():
    path = DATA_DIR / "ai_portfolio.json"
    if not path.exists():
        my = load_portfolio()
        ai = {
            "meta": {
                "inception_date": datetime.date.today().isoformat(),
                "inception_nav_usd": my["meta"]["total_nav_usd"],
                "last_updated": datetime.date.today().isoformat()
            },
            "nav_approx_usd": my["meta"]["total_nav_usd"],
            "cash_usd": my["cash"]["usd"],
            "holdings": [
                {"ticker": h["ticker"], "weight_pct": h["weight_pct"],
                 "cost_basis_usd": None, "note": h.get("note", "")}
                for h in my["holdings"]
            ],
            "decisions": []
        }
        save_ai_portfolio(ai)
        return ai
    with open(path) as f:
        return json.load(f)

def save_ai_portfolio(data):
    with open(DATA_DIR / "ai_portfolio.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_nav_history():
    p = DATA_DIR / "nav_history.json"
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {"snapshots": []}

def save_nav_history(data):
    with open(DATA_DIR / "nav_history.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def usd_thb(usd: float) -> str:
    return f"${usd:,.2f} (฿{usd * THB_RATE:,.0f})"

def bangkok_now():
    import pytz
    return datetime.datetime.now(pytz.timezone("Asia/Bangkok"))

def next_scan_bkk() -> str:
    """Return next scheduled scan time as readable string"""
    now = bangkok_now()
    h, m = now.hour, now.minute
    # Scans run every hour 09-23 BKK; key scans at 08, 20
    scan_hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
    for sh in scan_hours:
        if sh > h or (sh == h and m < 55):
            return f"{sh:02d}:00 น. (BKK)"
    # Next morning
    tom = now + datetime.timedelta(days=1)
    return tom.strftime("%d %b") + " 08:00 น. (BKK)"

def send_telegram(message: str, urgent: bool = False):
    if not TELEGRAM_TOKEN:
        print("No Telegram token, skipping...")
        return
    prefix = "🚨 " if urgent else "🤖 "
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": prefix + message,
               "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"Telegram sent: {message[:60]}...")
    except Exception as e:
        print(f"Telegram error: {e}")

def get_price(ticker: str) -> dict:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        meta = r.json()["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev  = meta.get("previousClose", 1)
        return {"ticker": ticker, "price": price, "prev_close": prev,
                "change_pct": round((price / prev - 1) * 100, 2)}
    except Exception as e:
        print(f"Price error {ticker}: {e}")
        return {"ticker": ticker, "price": 0, "prev_close": 0, "change_pct": 0}

def get_news(ticker: str) -> list:
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.content)
        return [{"title": i.findtext("title",""),
                 "description": i.findtext("description",""),
                 "published": i.findtext("pubDate","")}
                for i in root.findall(".//item")[:8]]
    except Exception as e:
        print(f"News error {ticker}: {e}")
        return []

def get_spy_price() -> float:
    return get_price("SPY").get("price", 0)

def load_thesis(ticker: str) -> str:
    p = THESIS_DIR / f"{ticker}.md"
    return p.read_text() if p.exists() else ""

def save_thesis(ticker: str, content: str):
    (THESIS_DIR / f"{ticker}.md").write_text(content)


# ── AI Calls ─────────────────────────────────────────────────────────────────
def generate_thesis(ticker: str, price_data: dict) -> str:
    prompt = f"""{THAI}

คุณคือนักลงทุนระยะยาวสไตล์ Nick Sleep วิเคราะห์ {ticker} ราคา ${price_data['price']:.2f}

เขียน thesis ในรูปแบบนี้:

# {ticker} Thesis
**วันที่:** {bangkok_now().strftime('%Y-%m-%d')}
**สถานะ:** Active
**ราคาตอนเขียน:** ${price_data['price']:.2f}
**เป้าหมาย hold:** 2-5 ปี

## ทำไมถึงถือ
[2-3 เหตุผลจากพื้นฐานธุรกิจ ไม่ใช่ราคา]

## ความเสี่ยงหลัก
[2-3 ความเสี่ยงที่ต้องติดตาม]

## Kill Conditions (ขายทันทีถ้าเกิดขึ้น)
- KC1: [เหตุการณ์ที่วัดได้ชัดเจน]
- KC2: [เหตุการณ์ที่วัดได้ชัดเจน]
- KC3: [เหตุการณ์ที่วัดได้ชัดเจน]

## Alert Conditions (ดูไว้ ยังไม่ขาย)
- AC1: [สิ่งที่ควรติดตาม]
- AC2: [สิ่งที่ควรติดตาม]

## สิ่งที่ต้องดูในงบรายไตรมาส
- [metric หลัก 1]
- [metric หลัก 2]

## หมายเหตุ
[บริบทเพิ่มเติม]

ระบุให้ชัด Kill conditions ต้องเป็น business events ไม่ใช่ราคา
"""
    result = call_ai(prompt)
    if result.startswith("Error:"):
        return f"# {ticker} Thesis\n**Error generating thesis:** {result}"
    return result


def scan_news_for_urgency(ticker: str, news_items: list, existing_thesis: str) -> dict:
    if not news_items:
        return {"urgent": False, "alert": False, "summary": "ไม่พบข่าว"}
    if not OPENAI_API_KEY:
        return {"urgent": False, "alert": False, "thesis_status": "intact",
                "summary": "ไม่มี API key", "action": "none", "reason": ""}

    news_text    = "\n".join([f"- {n['title']}: {n['description'][:200]}" for n in news_items])
    thesis_snip  = existing_thesis[:800] if existing_thesis else "ยังไม่มี thesis"

    prompt = f"""{THAI}

คุณกำลังติดตาม {ticker} สำหรับนักลงทุนระยะยาว

Thesis ปัจจุบัน:
{thesis_snip}

ข่าวล่าสุด:
{news_text}

จำแนกข่าวนี้ ตอบเป็น JSON เท่านั้น (ไม่ต้องมี ```):
{{
  "urgent": true/false,
  "alert": true/false,
  "thesis_status": "intact" | "evolving" | "at_risk" | "invalidated",
  "summary": "สรุป 1-2 ประโยคภาษาไทย",
  "action": "none" | "monitor" | "review_thesis" | "consider_sell",
  "reason": "เหตุผลภาษาไทย"
}}

urgent = kill condition อาจถูก trigger แล้ว
alert = มีสิ่งน่าสังเกต
intact = thesis ยังดี | evolving = thesis กำลังเปลี่ยน | at_risk = ใกล้ kill condition | invalidated = ขาย
"""
    text = call_ai(prompt).strip()
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"urgent": False, "alert": False, "thesis_status": "intact",
                "summary": f"วิเคราะห์ไม่ได้: {e}", "action": "none", "reason": ""}


def generate_weekly_recommendation(portfolio: dict, holdings_analysis: list) -> str:
    if not OPENAI_API_KEY:
        return "Error: ไม่มี OPENAI_API_KEY"

    now      = bangkok_now()
    cash_usd = portfolio["cash"]["usd"]

    holdings_text  = "\n".join([
        f"- {h['ticker']}: {h['weight_pct']:.1f}% | {h.get('thesis_status','?')} | {h.get('news_summary','')}"
        for h in holdings_analysis])
    watchlist_text = "\n".join([
        f"- {w['ticker']}: {w.get('reason','')}"
        for w in portfolio.get("watchlist", [])])

    prompt = f"""{THAI}

คุณคือผู้จัดการพอร์ตสำหรับนักลงทุนไทยอายุน้อย (เน้น growth ระยะยาว ไม่ใช่ปันผล)

วันที่: {now.strftime('%Y-%m-%d %H:%M')} เวลาไทย
เงินสด: {usd_thb(cash_usd)}
Philosophy: ซื้อและถือคุณภาพ ไม่เทรด min hold 6 เดือน

Holdings:
{holdings_text}

Watchlist:
{watchlist_text}

เขียนคำแนะนำในรูปแบบนี้:

## คำแนะนำสัปดาห์นี้ — {now.strftime('%d %b %Y')}

### การตัดสินใจ
[HOLD ทั้งหมด] หรือ ระบุการกระทำ:
- หุ้น / เวลา / ขนาด / เหตุผล

### สถานะ Holdings
[แต่ละตัว: INTACT / EVOLVING / AT RISK + สาเหตุ 1 บรรทัด]

### กลยุทธ์เงินสด
[จะทำอะไรกับ {usd_thb(cash_usd)}]

### Watchlist — ใกล้ซื้อแล้วไหม
[ตัวไหนใกล้ที่สุด ต้องรออะไร]

### เหตุการณ์สำคัญสัปดาห์นี้
[Earnings, Fed, macro]

ตรงไปตรงมา ห้ามแนะนำตามราคา "ไม่ทำอะไร" เป็นคำตอบที่ถูกต้องได้
"""
    return call_ai(prompt)


def ai_make_trading_decision(ai_portfolio: dict, holdings_analysis: list, watchlist: list) -> list:
    """AI ตัดสินใจซื้อ/ขายใน paper portfolio"""
    if not OPENAI_API_KEY:
        return []

    now      = bangkok_now()
    cash_usd = ai_portfolio.get("cash_usd", 0)

    holdings_text  = "\n".join([
        f"- {h['ticker']}: {h.get('weight_pct',0):.1f}% | {h.get('thesis_status','?')} | {h.get('news_summary','')}"
        for h in holdings_analysis])
    watchlist_text = "\n".join([f"- {w['ticker']}: {w.get('reason','')}" for w in watchlist])

    prompt = f"""{THAI}

คุณคือ AI fund manager ดูแลพอร์ต paper trading สไตล์ Nick Sleep
วันที่: {now.strftime('%Y-%m-%d %H:%M')} เวลาไทย
เงินสด: {usd_thb(cash_usd)}
Philosophy: quality growth min hold 6 เดือน max 10 positions max cash 40%

Holdings ปัจจุบัน:
{holdings_text}

Watchlist:
{watchlist_text}

ตัดสินใจว่าจะซื้อหรือขายอะไรไหม ตอบเป็น JSON array เท่านั้น (ไม่มี ```):
[
  {{
    "action": "BUY" | "SELL",
    "ticker": "TICKER",
    "reason_th": "เหตุผลภาษาไทย 2-3 ประโยค",
    "size_pct": 5,
    "urgency": "today" | "this_week" | "wait"
  }}
]

กฎ:
- thesis_status = invalidated → SELL
- thesis_status = at_risk → พิจารณา SELL
- watchlist มี signal + เงินสดพอ → พิจารณา BUY
- ถ้าไม่มีอะไรน่าทำ → ส่ง [] กลับ
- action ไม่เกิน 2 รายการต่อครั้ง
"""
    text = call_ai(prompt).strip()
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        decisions = json.loads(text.strip())
        return [d for d in decisions if d.get("action") in ["BUY", "SELL"]]
    except Exception as e:
        print(f"AI trading error: {e}")
        return []


def execute_ai_decision(ai_portfolio: dict, decision: dict, price: float):
    """Simulate trade execution in AI portfolio"""
    ticker    = decision["ticker"]
    action    = decision["action"]
    nav       = ai_portfolio.get("nav_approx_usd", 3142)
    size_pct  = max(2, min(decision.get("size_pct", 5), 30))
    trade_usd = nav * size_pct / 100

    if action == "SELL":
        ai_portfolio["holdings"] = [h for h in ai_portfolio["holdings"]
                                    if h["ticker"] != ticker]
        ai_portfolio["cash_usd"] = ai_portfolio.get("cash_usd", 0) + trade_usd

    elif action == "BUY" and ai_portfolio.get("cash_usd", 0) >= trade_usd:
        existing = next((h for h in ai_portfolio["holdings"] if h["ticker"] == ticker), None)
        if existing:
            existing["weight_pct"] += size_pct
        else:
            ai_portfolio["holdings"].append({
                "ticker": ticker, "weight_pct": size_pct,
                "cost_basis_usd": price, "note": decision.get("reason_th", "")
            })
        ai_portfolio["cash_usd"] = ai_portfolio.get("cash_usd", 0) - trade_usd

    log = {
        "date":     bangkok_now().strftime("%Y-%m-%d %H:%M"),
        "action":   action,
        "ticker":   ticker,
        "price":    price,
        "usd":      trade_usd,
        "reason":   decision.get("reason_th", ""),
        "urgency":  decision.get("urgency", "")
    }
    ai_portfolio.setdefault("decisions", []).append(log)
    return ai_portfolio


def discover_watchlist_candidates(portfolio: dict, holdings_analysis: list) -> list:
    """AI หาหุ้นใหม่ที่น่าเพิ่มเข้า watchlist"""
    if not OPENAI_API_KEY:
        return []

    skip = [h["ticker"] for h in portfolio["holdings"]] + \
           [w["ticker"] for w in portfolio.get("watchlist", [])]
    themes = "\n".join([f"- {h['ticker']}: {h.get('note','')}" for h in portfolio["holdings"]])

    prompt = f"""{THAI}

คุณคือนักวิเคราะห์สำหรับนักลงทุนสไตล์ Nick Sleep

พอร์ตปัจจุบัน (ไม่ต้องแนะนำซ้ำ): {', '.join(skip)}

Themes ที่มีอยู่:
{themes}

Philosophy: quality growth ระยะยาว ไม่ใช่ปันผล min hold 6 เดือน

หาหุ้นใหม่ 1-3 ตัวที่น่าสนใจ (business model แข็ง moat ชัด เติบโตได้ 5+ ปี)
ตอบเป็น JSON array (ไม่มี ```):
[
  {{
    "ticker": "TICKER",
    "name": "ชื่อบริษัท",
    "thesis_short": "ทำไมน่าสนใจ 2-3 ประโยคภาษาไทย",
    "kill_condition": "เหตุการณ์ที่จะทำให้ thesis เสีย",
    "priority": "high" | "medium" | "low"
  }}
]

ถ้าไม่มีอะไรน่าสนใจพิเศษ ส่ง [] กลับ
"""
    text = call_ai(prompt).strip()
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        print(f"Watchlist discovery error: {e}")
        return []


# ── Dashboard ────────────────────────────────────────────────────────────────
def update_dashboard_data(portfolio: dict, holdings_analysis: list,
                           recommendation: str = "", ai_portfolio: dict = None,
                           ai_suggested: list = None):
    now     = bangkok_now()
    nav_his = load_nav_history()

    dashboard = {
        "last_updated":     now.isoformat(),
        "last_updated_bkk": now.strftime("%d %b %Y, %H:%M น. (BKK)"),
        "spy_price":        get_spy_price(),
        "next_scan_bkk":   next_scan_bkk(),
        "my": {
            "nav_usd":        portfolio["meta"]["total_nav_usd"],
            "nav_thb":        portfolio["meta"]["total_nav_usd"] * THB_RATE,
            "cash_usd":       portfolio["cash"]["usd"],
            "cash_thb":       portfolio["cash"]["thb"],
            "holdings":       holdings_analysis if holdings_analysis else portfolio["holdings"],
            "recommendation": recommendation,
        },
        "ai": {
            "nav_usd":         (ai_portfolio or {}).get("nav_approx_usd", portfolio["meta"]["total_nav_usd"]),
            "cash_usd":        (ai_portfolio or {}).get("cash_usd", portfolio["cash"]["usd"]),
            "holdings":        (ai_portfolio or portfolio).get("holdings", []),
            "recent_decisions": (ai_portfolio or {}).get("decisions", [])[-5:],
        },
        "watchlist":    portfolio.get("watchlist", []),
        "ai_suggested": ai_suggested or [],
        "philosophy":   portfolio.get("philosophy", {}),
        "nav_history":  nav_his.get("snapshots", [])
    }

    with open(DATA_DIR / "dashboard.json", "w") as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)
    print("Dashboard updated.")


# ── Modes ────────────────────────────────────────────────────────────────────
def run_scan():
    print(f"[{bangkok_now().strftime('%H:%M BKK')}] Running scan...")
    portfolio     = load_portfolio()
    urgent_alerts = []
    alerts        = []
    scan_rows     = []

    all_tickers = [h["ticker"] for h in portfolio["holdings"]] + \
                  [w["ticker"] for w in portfolio.get("watchlist", [])]

    for ticker in all_tickers:
        price_data = get_price(ticker)
        news       = get_news(ticker)
        thesis     = load_thesis(ticker)

        row = {"ticker": ticker,
               "price": price_data["price"],
               "change_pct": price_data["change_pct"]}

        if abs(price_data["change_pct"]) >= 5:
            arrow = "📈" if price_data["change_pct"] > 0 else "📉"
            msg   = f"{arrow} *{ticker}* เคลื่อนไหว {price_data['change_pct']:+.1f}%"
            (urgent_alerts if price_data["change_pct"] < -5 else alerts).append(msg)

        if news:
            analysis = scan_news_for_urgency(ticker, news, thesis)
            row["summary"] = analysis.get("summary", "")
            if analysis.get("urgent"):
                urgent_alerts.append(f"🚨 *{ticker}* — {analysis['summary']}")
            elif analysis.get("alert"):
                alerts.append(f"⚠️ *{ticker}* — {analysis['summary']}")

        scan_rows.append(row)
        time.sleep(1)

    # ── ส่ง Telegram ทุก scan ──
    now       = bangkok_now()
    next_time = next_scan_bkk()

    if urgent_alerts:
        msg = ("🚨 *แจ้งเตือนด่วน*\n\n" + "\n\n".join(urgent_alerts) +
               f"\n\n⏰ scan ถัดไป: {next_time}")
        send_telegram(msg, urgent=True)
    else:
        lines = []
        for r in scan_rows:
            c = r.get("change_pct", 0)
            arrow = "📈" if c > 0 else "📉" if c < 0 else "➡️"
            lines.append(f"{arrow} *{r['ticker']}* {c:+.1f}%  ${r['price']:.2f}")

        alert_txt = ("\n⚠️ " + "\n⚠️ ".join(alerts)) if alerts else "✅ ทุกตัว thesis ปกติ"
        msg = (f"📡 *Scan — {now.strftime('%d %b %Y %H:%M น.')}*\n\n"
               f"{chr(10).join(lines)}\n\n"
               f"{alert_txt}\n\n"
               f"⏰ scan ถัดไป: *{next_time}*")
        send_telegram(msg)

    print(f"Scan done. {len(urgent_alerts)} urgent, {len(alerts)} alerts.")
    update_dashboard_data(portfolio, [])


def run_weekly():
    print(f"[{bangkok_now().strftime('%H:%M BKK')}] Running weekly...")
    portfolio    = load_portfolio()
    ai_portfolio = load_ai_portfolio()
    holdings_analysis = []

    for holding in portfolio["holdings"]:
        ticker     = holding["ticker"]
        price_data = get_price(ticker)
        news       = get_news(ticker)
        thesis     = load_thesis(ticker)

        if not thesis or "Error generating thesis" in thesis:
            print(f"  Generating thesis {ticker}...")
            thesis = generate_thesis(ticker, price_data)
            save_thesis(ticker, thesis)

        analysis = scan_news_for_urgency(ticker, news, thesis)
        holding["news_summary"]  = analysis.get("summary", "")
        holding["thesis_status"] = analysis.get("thesis_status", "intact")
        holding["price"]         = price_data["price"]
        holding["change_pct"]    = price_data["change_pct"]
        holdings_analysis.append(holding)
        time.sleep(2)

    # ── AI paper trading ──
    decisions = ai_make_trading_decision(ai_portfolio, holdings_analysis,
                                         portfolio.get("watchlist", []))
    for d in decisions:
        ticker     = d["ticker"]
        action     = d["action"]
        price_data = get_price(ticker)
        action_th  = "ซื้อ" if action == "BUY" else "ขาย"
        urgency_th = {"today": "วันนี้", "this_week": "สัปดาห์นี้", "wait": "รอดูก่อน"}.get(
                      d.get("urgency", ""), "")

        send_telegram(
            f"🤖 *AI Portfolio — {action_th} {ticker}*\n\n"
            f"*การตัดสินใจ:* {action_th} {ticker} {urgency_th}\n"
            f"*เหตุผล:* {d.get('reason_th','')}\n"
            f"*ขนาด:* ~{d.get('size_pct',0)}% ของพอร์ต\n\n"
            f"_คุณสามารถทำตามใน My Portfolio ได้ถ้าเห็นด้วย_"
        )
        ai_portfolio = execute_ai_decision(ai_portfolio, d, price_data["price"])
        time.sleep(1)

    # ── Watchlist discovery ──
    suggested = discover_watchlist_candidates(portfolio, holdings_analysis)
    if suggested:
        lines = []
        for s in suggested:
            emoji = {"high": "🔥", "medium": "👀", "low": "📌"}.get(s.get("priority","low"), "📌")
            lines.append(f"{emoji} *{s['ticker']}* — {s.get('name','')}\n{s.get('thesis_short','')}")
        send_telegram("💡 *AI แนะนำเข้า Watchlist*\n\n" + "\n\n".join(lines))

    # ── Weekly recommendation ──
    recommendation = generate_weekly_recommendation(portfolio, holdings_analysis)

    save_portfolio(portfolio)
    ai_portfolio["meta"]["last_updated"] = datetime.date.today().isoformat()
    save_ai_portfolio(ai_portfolio)
    update_dashboard_data(portfolio, holdings_analysis, recommendation, ai_portfolio, suggested)

    now       = bangkok_now()
    next_time = next_scan_bkk()
    short_rec = recommendation[:600] + "..." if len(recommendation) > 600 else recommendation
    send_telegram(
        f"📊 *Weekly Review — {now.strftime('%d %b %Y %H:%M น.')}*\n\n"
        f"{short_rec}\n\n⏰ scan ถัดไป: *{next_time}*"
    )
    print("Weekly done.")


def run_earnings(ticker: str):
    print(f"[{bangkok_now().strftime('%H:%M BKK')}] Earnings check {ticker}...")
    portfolio  = load_portfolio()
    price_data = get_price(ticker)
    news       = get_news(ticker)
    thesis     = load_thesis(ticker)

    if not thesis or "Error generating thesis" in thesis:
        thesis = generate_thesis(ticker, price_data)
        save_thesis(ticker, thesis)

    analysis = scan_news_for_urgency(ticker, news, thesis)
    log = (f"\n\n---\n## Earnings {bangkok_now().strftime('%Y-%m-%d')}\n"
           f"**สถานะ:** {analysis['thesis_status']}\n"
           f"**สรุป:** {analysis['summary']}\n"
           f"**แนะนำ:** {analysis['action']}\n")
    save_thesis(ticker, thesis + log)

    emoji     = {"intact":"✅","evolving":"🔄","at_risk":"⚠️","invalidated":"🚨"}.get(analysis["thesis_status"],"❓")
    next_time = next_scan_bkk()
    send_telegram(
        f"{emoji} *{ticker} — งบรายไตรมาส*\n\n"
        f"Thesis: *{analysis['thesis_status'].upper()}*\n"
        f"{analysis['summary']}\n\n"
        f"แนะนำ: *{analysis['action']}*\n"
        f"_{analysis['reason']}_\n\n"
        f"⏰ scan ถัดไป: *{next_time}*",
        urgent=analysis["thesis_status"] in ["at_risk","invalidated"]
    )


# ── Entry ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if MODE == "scan":
        run_scan()
    elif MODE == "weekly":
        run_weekly()
    elif MODE == "earnings" and len(sys.argv) > 2:
        run_earnings(sys.argv[2].upper())
    else:
        print(f"Mode ไม่รู้จัก: {MODE}")
        print("Usage: python analyze.py [scan|weekly|earnings TICKER]")
