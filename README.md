# 🥇 Gold Deal Hunter Agent v2.0

## What This Does
Scrapes Kijiji, Craigslist, and Facebook Marketplace for gold/jewelry listings 24/7.
Scores every listing by melt value. Auto-messages high-score sellers. Reads replies.
Sends you a Telegram alert when a deal is ready. You just approve or reject.

---

## STEP 1 — Install dependencies (on your computer)

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## STEP 2 — Fill in your .env file

Copy `.env.example` to `.env` then fill in these 6 things:

```
DATABASE_URL=       ← from Railway PostgreSQL (Variables tab)
GEMINI_API_KEY=     ← from aistudio.google.com → Get API Key
TELEGRAM_BOT_TOKEN= ← from @BotFather on Telegram → /newbot
TELEGRAM_CHAT_ID=   ← visit api.telegram.org/bot{TOKEN}/getUpdates after starting bot
FB_EMAIL=           ← your SECONDARY Facebook account email
FB_PASSWORD=        ← your secondary Facebook account password
KIJIJI_EMAIL=       ← your Kijiji email
KIJIJI_PASSWORD=    ← your Kijiji password
```

---

## STEP 3 — Test everything works

```bash
python test_setup.py
```

All tests should pass before continuing.

---

## STEP 4 — Capture browser sessions (one time only)

```bash
python session_setup.py both
```

This opens a browser, automatically logs in to Facebook and Kijiji using your
credentials from .env, and saves the session files. Takes about 60 seconds.

If Facebook asks for 2FA, complete it in the browser window, then press ENTER.

---

## STEP 5 — Run locally to test

```bash
# Terminal 1 — agent
python agent/main.py

# Terminal 2 — dashboard
streamlit run dashboard/app.py
```

Open http://localhost:8501 to see the dashboard.

---

## STEP 6 — Deploy to Railway

1. Push your code to a private GitHub repo
   (sessions/ and .env are gitignored — never committed)

2. Go to railway.app → New Project → Deploy from GitHub repo

3. Add PostgreSQL: click + → Database → PostgreSQL

4. Add environment variables in Railway dashboard:
   - All the same values from your .env file
   - FACEBOOK_SESSION_B64 = contents of sessions/facebook_session_b64.txt
   - KIJIJI_SESSION_B64 = contents of sessions/kijiji_session_b64.txt

5. Railway auto-deploys. Check logs to confirm agent started.

6. Share the dashboard URL with your friend — they just need that URL.

---

## How Your Friend Uses It

They get a Telegram message like this when a deal is found:
  "🏆 GOLD DEAL — Score 87/100
   18K gold chain, 12g, asking $280 CAD
   Melt value $720 — profit est. $440
   [View Listing] [View Chat]"

They open the dashboard URL → see the deal card → click "I'm Buying It" or "Pass".
That's literally it. No code, no terminal, nothing technical.

---

## Dashboard Pages

- 🧠 Brain Overview — live job status, pipeline counts, activity feed, message cap
- 🏆 Deals Ready — handover cards with full details + approve/reject buttons
- 💬 Conversations — every seller conversation with full message thread
- 👻 Ghosted — sellers who haven't replied in 48h
- 📋 All Listings — filterable table of everything scraped
- 📊 Stats — weekly chart, platform breakdown, reply rate

---

## Ongoing Maintenance (after deployment)

| Task | When | Time |
|------|------|------|
| Re-run session_setup.py facebook | Every 5-14 days | 5 min |
| Check Railway logs | Weekly | 5 min |
| Review handover deals | As Telegram alerts arrive | 2 min |

The agent Telegram-alerts you when the FB session expires.

---

## Cost (~$43-52/month)
- Railway Pro: ~$20/month (includes $20 credit)
- Railway compute: ~$10-15/month
- Gemini API: ~$12-15/month (free during testing)
- Everything else: FREE
