# 🧪 Gold Agent — Step-by-Step Testing Guide

Follow this EXACTLY in order. Do not skip steps.

---

## BEFORE ANYTHING — Fill in .env

Copy `.env.example` to `.env` and fill these in:

```
DATABASE_URL=postgresql://postgres:PASSWORD@HOST:PORT/railway
              ↑ Use DATABASE_PUBLIC_URL value from Railway (for local testing)

GEMINI_API_KEY=AIza...
              ↑ From aistudio.google.com → Get API Key

TELEGRAM_BOT_TOKEN=7123456789:AAF...
              ↑ From @BotFather on Telegram → /newbot

TELEGRAM_CHAT_ID=987654321
              ↑ See instructions below

CITIES=toronto

FB_EMAIL=your_secondary_fb@email.com
FB_PASSWORD=your_secondary_fb_password

KIJIJI_EMAIL=your_kijiji@email.com
KIJIJI_PASSWORD=your_kijiji_password
```

### Getting your Telegram Chat ID:
1. Message @BotFather → /newbot → follow prompts → copy token
2. Open your new bot in Telegram → press Start → send "hi"
3. Visit: https://api.telegram.org/bot{YOUR_TOKEN}/getUpdates
4. Find: "chat":{"id": 123456789} ← that number is your chat ID

---

## PHASE 1 — Install & Basic Checks

```bash
# Install everything
pip install -r requirements.txt
playwright install chromium

# Run the test suite
python test_setup.py
```

**Expected output:**
```
✅ PostgreSQL
✅ Gold Price API
✅ Gemini API
✅ Telegram
✅ Craigslist RSS
✅ Scorer (LLM)
```

**If anything fails:** Fix it before continuing. The error message tells you what's wrong.

---

## PHASE 2 — Test Craigslist Scraping (no login needed)

```bash
python -c "
import sys; sys.path.insert(0,'agent')
from dotenv import load_dotenv; load_dotenv()
import db; db.init_db()
import scraper
n = scraper.run_craigslist_scrape()
print(f'New listings: {n}')
listings = db.get_listings_by_status('new', limit=5)
for l in listings:
    print(f'  {l[\"platform\"]} | {l[\"price_cad\"]} | {l[\"title\"][:50]}')
"
```

**Expected:** 5-20 new listings from Craigslist toronto gold searches.

---

## PHASE 3 — Test Kijiji Scraping (no login needed)

```bash
python -c "
import sys; sys.path.insert(0,'agent')
from dotenv import load_dotenv; load_dotenv()
import db, scraper
n = scraper.run_kijiji_scrape()
print(f'New Kijiji listings: {n}')
listings = db.get_listings_by_status('new', limit=5)
kj = [l for l in listings if l['platform']=='kijiji']
for l in kj[:3]:
    print(f'  ${l[\"price_cad\"]} | {l[\"title\"][:50]}')
    print(f'  Desc: {(l.get(\"description\") or \"\")[:80]}')
"
```

**Expected:** 5-20 Kijiji listings with descriptions populated.

---

## PHASE 4 — Test Scoring on Real Listings

```bash
python -c "
import sys; sys.path.insert(0,'agent')
from dotenv import load_dotenv; load_dotenv()
import db, scorer
listings = db.get_listings_by_status('new', limit=10)
print(f'Scoring {len(listings)} listings...')
for l in listings[:5]:
    score, merged, reasons = scorer.run_scorer_for_listing(l)
    db.update_listing_score(l['id'], score, merged, reasons)
    status = 'queued_msg' if score>=70 else ('rejected' if score<20 else 'scored')
    db.update_listing_status(l['id'], status)
    print(f'  {score}/100 → {status} | {l[\"title\"][:40]}')
    print(f'  Reasons: {reasons[:2]}')
"
```

**Expected:** Listings scored 0-100. Some will be queued_msg (≥70), rest scored or rejected.

---

## PHASE 5 — Test Gold Price API

```bash
python -c "
import sys; sys.path.insert(0,'agent')
from dotenv import load_dotenv; load_dotenv()
from gold_price import get_spot_per_gram_cad, melt_value
spot = get_spot_per_gram_cad()
print(f'Gold spot: \${spot:.2f}/gram CAD')
print(f'10g of 18K = \${melt_value(10,18):.2f} CAD')
print(f'5g of 14K  = \${melt_value(5,14):.2f} CAD')
"
```

**Expected:** Live gold price and example melt values.

---

## PHASE 6 — Test Kijiji Session & Messaging

```bash
# Capture Kijiji session (auto-login)
python session_setup.py kijiji
```

Browser opens, logs in automatically. Should take ~30 seconds.
Then test sending one message manually:

```bash
python -c "
import sys, asyncio; sys.path.insert(0,'agent')
from dotenv import load_dotenv; load_dotenv()
import db, messenger
from playwright.async_api import async_playwright

async def test():
    listings = db.get_listings_by_status('queued_msg', limit=1)
    if not listings:
        print('No queued listings yet. Run phases 1-5 first.')
        return
    listing = listings[0]
    print(f'Testing message to: {listing[\"title\"][:50]}')
    msg = messenger.generate_first_message(listing)
    print(f'Generated message: {msg}')
    async with async_playwright() as p:
        browser, ctx = await messenger.get_browser_context('kijiji', p)
        ok, url = await messenger.send_message_kijiji(listing['url'], msg, ctx)
        print(f'Send result: {ok} | URL: {url}')
        await ctx.close(); await browser.close()

asyncio.run(test())
"
```

---

## PHASE 7 — Test Telegram

```bash
python -c "
import sys; sys.path.insert(0,'agent')
from dotenv import load_dotenv; load_dotenv()
from handover import send_alert_telegram
send_alert_telegram('Test message from Gold Agent — setup working!')
print('Check your Telegram!')
"
```

**Expected:** Message arrives on your phone within 5 seconds.

---

## PHASE 8 — Run the Full Dashboard

```bash
# Terminal 1
python agent/main.py

# Terminal 2
streamlit run dashboard/app.py
```

Open http://localhost:8501 — you should see:
- Brain Overview with job status
- Pipeline counts
- Activity feed populating as the agent runs

---

## PHASE 9 — Full Test Cycle (fastest way to test everything)

```bash
python agent/main.py --test
```

This runs one complete scrape → score → message → poll cycle immediately.
No waiting 20-45 minutes. Takes about 5-10 minutes to complete.
Then open the dashboard to see all results.

---

## PHASE 10 — Facebook (when you have secondary account)

```bash
python session_setup.py facebook
```

Then re-run `python agent/main.py --test` and FB listings will appear.

---

## DEPLOY TO RENDER (when local testing is done)

1. Push to a private GitHub repo
   ```bash
   git init
   git add .
   git commit -m "Gold Agent v2"
   git remote add origin https://github.com/YOUR_USERNAME/gold-agent.git
   git push -u origin main
   ```

2. Go to render.com → New → Web Service → connect your repo

3. Settings:
   - **Build Command:** `pip install -r requirements.txt && playwright install chromium && playwright install-deps chromium`
   - **Start Command:** `python agent/main.py`
   - **Plan:** Starter ($7/month) or Standard ($25/month)

4. Add all env vars from your .env file in Render's Environment tab
   - Include FACEBOOK_SESSION_B64 (from sessions/facebook_session_b64.txt)
   - Include KIJIJI_SESSION_B64 (from sessions/kijiji_session_b64.txt)

5. Create a second Render service for the dashboard:
   - Same repo, same env vars
   - **Start Command:** `streamlit run dashboard/app.py --server.port $PORT --server.address 0.0.0.0`

6. Share the dashboard URL with your friend. Done.

---

## Common Issues & Fixes

| Problem | Fix |
|---------|-----|
| `psycopg2 connection error` | Check DATABASE_URL — use PUBLIC url for local |
| `Gemini API error` | Check GEMINI_API_KEY — rotate if compromised |
| Kijiji login fails | Check KIJIJI_EMAIL/PASSWORD in .env |
| No listings scraped | Kijiji may have changed selectors — check logs |
| Dashboard shows nothing | Run `python agent/main.py --test` first |
| Telegram not sending | Check BOT_TOKEN and CHAT_ID, send /start to bot first |
