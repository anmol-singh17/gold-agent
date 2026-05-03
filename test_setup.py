"""
test_setup.py — Run this to verify each component works before starting the agent.
Run from the project root: python test_setup.py

Tests: DB connection, gold price API, Gemini API, Telegram bot
"""
from dotenv import load_dotenv
load_dotenv()
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))
from dotenv import load_dotenv
load_dotenv()

def test_db():
    print("\n[TEST] PostgreSQL connection...")
    try:
        import db
        db.init_db()
        print("  ✅ DB connected and tables created.")
        return True
    except Exception as e:
        print(f"  ❌ DB failed: {e}")
        print("     → Check DATABASE_URL in your .env file")
        return False

def test_gold_price():
    print("\n[TEST] Gold price API (goldpricez.com)...")
    try:
        from gold_price import get_spot_per_gram_cad, melt_value
        spot = get_spot_per_gram_cad()
        mv = melt_value(10, 18, spot)
        print(f"  ✅ Spot: ${spot:.2f}/gram CAD")
        print(f"     Example: 10g of 18K gold = ${mv:.2f} CAD melt value")
        return True
    except Exception as e:
        print(f"  ❌ Gold price failed: {e}")
        return False

def test_gemini():
    print("\n[TEST] Gemini API...")
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Reply with only the word: WORKING"
        )
        text = resp.text.strip()
        if "WORKING" in text.upper():
            print(f"  ✅ Gemini API working. Response: {text}")
        else:
            print(f"  ✅ Gemini API responded: {text}")
        return True
    except Exception as e:
        print(f"  ❌ Gemini failed: {e}")
        print("     → Check GEMINI_API_KEY in your .env file")
        return False

def test_telegram():
    print("\n[TEST] Telegram bot...")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("  ⚠️  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping")
        return None
    try:
        import requests
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "🧪 Gold Agent test message — setup working!"},
            timeout=10
        )
        if resp.status_code == 200:
            print("  ✅ Telegram message sent! Check your phone.")
        else:
            print(f"  ❌ Telegram failed: {resp.status_code} — {resp.text}")
        return resp.status_code == 200
    except Exception as e:
        print(f"  ❌ Telegram error: {e}")
        return False

def test_craigslist():
    print("\n[TEST] Craigslist RSS feed...")
    try:
        import feedparser
        feed = feedparser.parse(
            "https://toronto.craigslist.org/search/jwa?query=gold+ring&format=rss"
        )
        count = len(feed.entries)
        print(f"  ✅ CL RSS working — {count} entries fetched")
        if feed.entries:
            print(f"     Sample: {feed.entries[0].get('title', 'no title')}")
        return True
    except Exception as e:
        print(f"  ❌ CL RSS failed: {e}")
        return False

def test_scorer():
    print("\n[TEST] Scorer (LLM text extraction)...")
    try:
        from scorer import extract_from_text
        result = extract_from_text(
            "18K gold chain 15g",
            "Selling my 18 karat gold chain, weighs 15 grams. Has 750 stamp. Asking $600."
        )
        print(f"  ✅ Scorer working: {result}")
        return True
    except Exception as e:
        print(f"  ❌ Scorer failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("  Gold Agent — Setup Test")
    print("=" * 50)

    results = {
        "PostgreSQL": test_db(),
        "Gold Price API": test_gold_price(),
        "Gemini API": test_gemini(),
        "Telegram": test_telegram(),
        "Craigslist RSS": test_craigslist(),
        "Scorer (LLM)": test_scorer(),
    }

    print("\n" + "=" * 50)
    print("  Results Summary")
    print("=" * 50)
    all_pass = True
    for name, result in results.items():
        if result is True:
            print(f"  ✅ {name}")
        elif result is False:
            print(f"  ❌ {name} — FIX THIS before running the agent")
            all_pass = False
        else:
            print(f"  ⚠️  {name} — skipped (not configured)")

    print()
    if all_pass:
        print("  🟢 All tests passed! You're ready to run the agent.")
        print("     Next: python session_setup.py both")
        print("     Then: python agent/main.py")
    else:
        print("  🔴 Fix the failed tests above, then re-run.")
    print()
