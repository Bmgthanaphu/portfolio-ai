#!/usr/bin/env python3
"""
Portfolio AI - Main Analysis Script
Runs news scan, thesis analysis, and portfolio recommendations
Timezone: Asia/Bangkok (UTC+7) | Market: NYSE/NASDAQ (UTC-4/5)
"""

import os, json, sys, time, datetime, requests
from pathlib import Path
from google import genai
from google.genai import types

# ── Config ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
THESIS_DIR = BASE_DIR / "docs" / "thesis"
THESIS_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5731895043")
THB_RATE = float(os.environ.get("THB_RATE", "36"))  # USD/THB rate

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
GEMINI_MODEL = "gemini-2.0-flash-lite"

MODE = sys.argv[1] if len(sys.argv) > 1 else "scan"
# Modes: scan | weekly | quarterly | earnings


# ── Helpers ────────────────────────────────────────────────────────────────
def load_portfolio():
    with open(DATA_DIR / "portfolio.json") as f:
        return json.load(f)

def save_portfolio(data):
    with open(DATA_DIR / "portfolio.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_nav_history():
    with open(DATA_DIR / "nav_history.json") as f:
        return json.load(f)

def usd_thb(usd: float) -> str:
    """Format as USD with THB in brackets"""
    thb = usd * THB_RATE
    return f"${usd:,.2f} (฿{thb:,.0f})"

def bangkok_now():
    import pytz
    bkk = pytz.timezone("Asia/Bangkok")
    return datetime.datetime.now(bkk)

def send_telegram(message: str, urgent: bool = False):
    """Send message to Telegram"""
    if not TELEGRAM_TOKEN:
        print("No Telegram token, skipping...")
        return
    prefix = "🚨 " if urgent else "🤖 "
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": prefix + message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"Telegram sent: {message[:60]}...")
    except Exception as e:
        print(f"Telegram error: {e}")

def get_price(ticker: str) -> dict:
    """Get current price from Yahoo Finance"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        return {
            "ticker": ticker,
            "price": meta.get("regularMarketPrice", 0),
            "prev_close": meta.get("previousClose", 0),
            "change_pct": round((meta.get("regularMarketPrice", 0) / meta.get("previousClose", 1) - 1) * 100, 2)
        }
    except Exception as e:
        print(f"Price fetch error {ticker}: {e}")
        return {"ticker": ticker, "price": 0, "prev_close": 0, "change_pct": 0}

def get_news(ticker: str) -> list:
    """Get recent news from Yahoo Finance RSS"""
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:8]:
            title = item.findtext("title", "")
            desc = item.findtext("description", "")
            pub = item.findtext("pubDate", "")
            items.append({"title": title, "description": desc, "published": pub})
        return items
    except Exception as e:
        print(f"News fetch error {ticker}: {e}")
        return []

def get_spy_price() -> float:
    data = get_price("SPY")
    return data.get("price", 0)

def load_thesis(ticker: str) -> str:
    path = THESIS_DIR / f"{ticker}.md"
    if path.exists():
        return path.read_text()
    return ""

def save_thesis(ticker: str, content: str):
    path = THESIS_DIR / f"{ticker}.md"
    path.write_text(content)


# ── AI Calls ───────────────────────────────────────────────────────────────
def generate_thesis(ticker: str, price_data: dict) -> str:
    """Ask Gemini to generate thesis + kill conditions for a stock"""
    if not client:
        return f"# {ticker} Thesis\n**Error:** No GEMINI_API_KEY set."

    prompt = f"""You are a disciplined long-term investor (Nick Sleep style).
Analyze {ticker} at current price ${price_data['price']:.2f}.

Write a thesis file in this exact format:

# {ticker} Thesis
**Date:** {bangkok_now().strftime('%Y-%m-%d')}
**Status:** Active
**Price at thesis:** ${price_data['price']:.2f}
**Target hold:** 2-5 years

## Why own it
[2-3 clear reasons based on business fundamentals, not price]

## Key risks
[2-3 specific risks to monitor]

## Kill conditions (EXIT if ANY of these happen)
- KC1: [Specific measurable event that invalidates the thesis]
- KC2: [Specific measurable event that invalidates the thesis]
- KC3: [Specific measurable event that invalidates the thesis]

## Alert conditions (WATCH but don't panic)
- AC1: [Event worth monitoring but not selling]
- AC2: [Event worth monitoring but not selling]

## What to look for in earnings
- [Key metric 1]
- [Key metric 2]

## Notes
[Any additional context]

Be specific. No vague statements. If you don't know something, say so.
Base kill conditions on BUSINESS events, not price movements.
"""
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return response.text
    except Exception as e:
        return f"# {ticker} Thesis\n**Error generating thesis:** {e}"


def scan_news_for_urgency(ticker: str, news_items: list, existing_thesis: str) -> dict:
    """Ask Gemini if any news items are urgent or thesis-threatening"""
    if not news_items:
        return {"urgent": False, "alert": False, "summary": "No news found"}
    if not client:
        return {"urgent": False, "alert": False, "thesis_status": "intact",
                "summary": "No GEMINI_API_KEY — skipping AI analysis", "action": "none", "reason": ""}

    news_text = "\n".join([f"- {n['title']}: {n['description'][:200]}" for n in news_items])
    thesis_snippet = existing_thesis[:800] if existing_thesis else "No thesis yet"

    prompt = f"""You are monitoring {ticker} for a long-term investor.

CURRENT THESIS:
{thesis_snippet}

RECENT NEWS:
{news_text}

Classify this news. Reply in JSON only:
{{
  "urgent": true/false,
  "alert": true/false,
  "thesis_status": "intact" | "evolving" | "at_risk" | "invalidated",
  "summary": "1-2 sentence summary of what matters",
  "action": "none" | "monitor" | "review_thesis" | "consider_sell",
  "reason": "Why this classification"
}}

Urgent = kill condition may have been hit, need immediate attention.
Alert = something changed worth noting, not urgent.
Intact = thesis still valid. Evolving = thesis changing but not broken.
At risk = one or more kill conditions getting close. Invalidated = sell.
"""
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = response.text.strip()
        # Strip markdown code blocks if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"urgent": False, "alert": False, "thesis_status": "intact",
                "summary": f"Analysis error: {e}", "action": "none", "reason": ""}


def generate_weekly_recommendation(portfolio: dict, holdings_analysis: list) -> str:
    """Generate weekly portfolio recommendation"""
    if not client:
        return "Error: No GEMINI_API_KEY set — weekly recommendation skipped."

    now = bangkok_now()
    cash_usd = portfolio["cash"]["usd"]

    holdings_text = "\n".join([
        f"- {h['ticker']}: {h['weight_pct']:.1f}% | Status: {h.get('thesis_status','unknown')} | {h.get('news_summary','')}"
        for h in holdings_analysis
    ])

    watchlist_text = "\n".join([
        f"- {w['ticker']}: {w.get('reason','')}"
        for w in portfolio.get("watchlist", [])
    ])

    prompt = f"""You are a portfolio manager for a young Thai investor (long-term growth focus, NOT dividend/income).

DATE: {now.strftime('%Y-%m-%d %H:%M')} Bangkok time
CASH AVAILABLE: ${cash_usd:.2f} (฿{cash_usd*THB_RATE:.0f})
PHILOSOPHY: Buy and hold quality growth. No trading for trading's sake. Min hold 6 months.

CURRENT HOLDINGS:
{holdings_text}

WATCHLIST:
{watchlist_text}

Provide weekly recommendation in this EXACT format:

## Weekly Recommendation — {now.strftime('%d %b %Y')}

### Action this week
[HOLD ALL] or [specific action with timing]

If action needed, be VERY specific:
- What: exactly which stock
- When: "Today at market open (20:30 BKK time)" or "Wait until [event]"
- Size: how much in USD (฿THB)
- Why: 1-2 sentences

### Holdings status
[For each holding: INTACT / EVOLVING / AT RISK + one line why]

### Cash strategy
[What to do with ${cash_usd:.2f} (฿{cash_usd*THB_RATE:.0f}) — deploy now, wait, or accumulate]

### Watchlist trigger
[Which watchlist stock is closest to buy? What confirmation is needed?]

### This week's key events to watch
[Earnings, Fed, macro events relevant to portfolio]

Be direct. Give a clear recommendation. "Do nothing" is a valid recommendation if thesis is intact.
Never recommend based on price movement alone.
"""
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return response.text
    except Exception as e:
        return f"Error generating recommendation: {e}"


# ── Main Modes ──────────────────────────────────────────────────────────────
def run_scan():
    """Lightweight hourly scan — only alert if something urgent"""
    print(f"[{bangkok_now().strftime('%H:%M BKK')}] Running scan...")
    portfolio = load_portfolio()
    urgent_alerts = []
    alerts = []

    all_tickers = [h["ticker"] for h in portfolio["holdings"]] + \
                  [w["ticker"] for w in portfolio.get("watchlist", [])]

    for ticker in all_tickers:
        price_data = get_price(ticker)
        news = get_news(ticker)
        thesis = load_thesis(ticker)

        # Check for >5% move
        if abs(price_data["change_pct"]) >= 5:
            direction = "📈" if price_data["change_pct"] > 0 else "📉"
            msg = f"{direction} *{ticker}* moved {price_data['change_pct']:+.1f}% today"
            if price_data["change_pct"] < -5:
                urgent_alerts.append(msg)
            else:
                alerts.append(msg)

        # Scan news
        if news:
            analysis = scan_news_for_urgency(ticker, news, thesis)
            if analysis.get("urgent"):
                urgent_alerts.append(
                    f"🚨 *{ticker}* — {analysis['summary']}\nAction: {analysis['action']}"
                )
            elif analysis.get("alert"):
                alerts.append(
                    f"⚠️ *{ticker}* — {analysis['summary']}"
                )

        time.sleep(1)  # Rate limit

    if urgent_alerts:
        msg = "🚨 *URGENT — Portfolio Alert*\n\n" + "\n\n".join(urgent_alerts)
        send_telegram(msg, urgent=True)
    elif alerts and bangkok_now().hour in [8, 14, 20]:  # Only send non-urgent at key hours
        msg = "📋 *Portfolio Update*\n\n" + "\n\n".join(alerts)
        send_telegram(msg)

    print(f"Scan done. {len(urgent_alerts)} urgent, {len(alerts)} alerts.")
    update_dashboard_data(portfolio, [])


def run_weekly():
    """Full weekly analysis with recommendation"""
    print(f"[{bangkok_now().strftime('%H:%M BKK')}] Running weekly analysis...")
    portfolio = load_portfolio()
    holdings_analysis = []

    for holding in portfolio["holdings"]:
        ticker = holding["ticker"]
        print(f"  Analyzing {ticker}...")
        price_data = get_price(ticker)
        news = get_news(ticker)
        thesis = load_thesis(ticker)

        # Generate thesis if none exists or if previous attempt failed
        if not thesis or "Error generating thesis" in thesis:
            print(f"  Generating thesis for {ticker}...")
            thesis = generate_thesis(ticker, price_data)
            save_thesis(ticker, thesis)

        analysis = scan_news_for_urgency(ticker, news, thesis)

        holding["news_summary"] = analysis.get("summary", "")
        holding["thesis_status"] = analysis.get("thesis_status", "intact")
        holding["price"] = price_data["price"]
        holding["change_pct"] = price_data["change_pct"]
        holdings_analysis.append(holding)
        time.sleep(2)

    # Generate recommendation
    recommendation = generate_weekly_recommendation(portfolio, holdings_analysis)

    # Update portfolio data
    save_portfolio(portfolio)
    update_dashboard_data(portfolio, holdings_analysis, recommendation)

    # Send Telegram
    now = bangkok_now()
    short_rec = recommendation[:800] + "..." if len(recommendation) > 800 else recommendation
    msg = f"📊 *Weekly Portfolio Review*\n_{now.strftime('%d %b %Y, %H:%M BKK')}_\n\n{short_rec}"
    send_telegram(msg)
    print("Weekly analysis complete.")


def run_earnings(ticker: str):
    """Run after earnings release for a specific stock"""
    print(f"[{bangkok_now().strftime('%H:%M BKK')}] Running earnings check for {ticker}...")
    portfolio = load_portfolio()
    price_data = get_price(ticker)
    news = get_news(ticker)
    thesis = load_thesis(ticker)

    if not thesis:
        thesis = generate_thesis(ticker, price_data)
        save_thesis(ticker, thesis)

    analysis = scan_news_for_urgency(ticker, news, thesis)

    # Update thesis log
    log_entry = f"\n\n---\n## Earnings Check {bangkok_now().strftime('%Y-%m-%d')}\n"
    log_entry += f"**Status:** {analysis['thesis_status']}\n"
    log_entry += f"**Summary:** {analysis['summary']}\n"
    log_entry += f"**Action:** {analysis['action']}\n"
    save_thesis(ticker, thesis + log_entry)

    # Send Telegram
    status_emoji = {"intact": "✅", "evolving": "🔄", "at_risk": "⚠️", "invalidated": "🚨"}.get(
        analysis["thesis_status"], "❓"
    )
    msg = (
        f"{status_emoji} *{ticker} Earnings Check*\n\n"
        f"Thesis: *{analysis['thesis_status'].upper()}*\n"
        f"{analysis['summary']}\n\n"
        f"Recommended action: *{analysis['action']}*\n"
        f"_{analysis['reason']}_"
    )
    urgent = analysis["thesis_status"] in ["at_risk", "invalidated"]
    send_telegram(msg, urgent=urgent)


def update_dashboard_data(portfolio: dict, holdings_analysis: list, recommendation: str = ""):
    """Write analysis results to JSON for dashboard to read"""
    now = bangkok_now()

    # Get SPY for benchmark
    spy_price = get_spy_price()

    dashboard_data = {
        "last_updated": now.isoformat(),
        "last_updated_bkk": now.strftime("%d %b %Y, %H:%M น. (BKK)"),
        "nav_usd": portfolio["meta"]["total_nav_usd"],
        "nav_thb": portfolio["meta"]["total_nav_usd"] * THB_RATE,
        "cash_usd": portfolio["cash"]["usd"],
        "cash_thb": portfolio["cash"]["thb"],
        "spy_price": spy_price,
        "holdings": holdings_analysis if holdings_analysis else portfolio["holdings"],
        "watchlist": portfolio.get("watchlist", []),
        "recommendation": recommendation,
        "philosophy": portfolio.get("philosophy", {})
    }

    with open(DATA_DIR / "dashboard.json", "w") as f:
        json.dump(dashboard_data, f, indent=2, ensure_ascii=False)
    print("Dashboard data updated.")


# ── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if MODE == "scan":
        run_scan()
    elif MODE == "weekly":
        run_weekly()
    elif MODE == "earnings" and len(sys.argv) > 2:
        run_earnings(sys.argv[2].upper())
    else:
        print(f"Unknown mode: {MODE}")
        print("Usage: python analyze.py [scan|weekly|earnings TICKER]")
