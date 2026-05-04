"""
test_apify.py — Input schema from official Apify code sample (confirmed working).
Kijiji actor ID: V5XnYsUNkjXYrFvbc (automation-lab/kijiji-scraper)
Run: python test_apify.py  (~$0.05 max for 5 items)
"""
import os, json, requests
from dotenv import load_dotenv
load_dotenv()

KEY  = os.getenv("APIFY_API_KEY","")
BASE = "https://api.apify.com/v2"

if not KEY:
    print("❌  APIFY_API_KEY not in .env"); exit(1)
print(f"✅  Key: {KEY[:25]}... ({len(KEY)} chars)\n")

def run_actor(actor_id, run_input, timeout=240, label=""):
    print(f"{'='*60}\n🧪  {label}")
    print(f"    Input: {json.dumps(run_input)[:300]}")
    url    = f"{BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": KEY, "timeout": timeout, "memory": 512}
    try:
        resp = requests.post(url, json=run_input, params=params, timeout=timeout+30)
        print(f"    HTTP: {resp.status_code}")
        if resp.status_code in (200, 201):
            data  = resp.json()
            items = data if isinstance(data, list) else data.get("items", data.get("data",[]))
            print(f"    ✅  {len(items)} items returned")
            if items:
                print(f"    Keys: {list(items[0].keys())}")
                for k,v in list(items[0].items())[:5]:
                    print(f"      {k:20s}: {str(v)[:80]}")
            else:
                print("    ⚠️  Actor ran OK but 0 items (try broader search URL)")
            return items
        elif resp.status_code == 404:
            print(f"    ❌  404 — actor not found")
        elif resp.status_code == 402:
            print(f"    ❌  402 — out of Apify credits")
        elif resp.status_code == 400:
            print(f"    ❌  400 — bad input: {resp.text[:400]}")
        else:
            print(f"    ❌  {resp.status_code}: {resp.text[:300]}")
        return []
    except requests.exceptions.Timeout:
        print(f"    ⚠️  Timed out — check console.apify.com for run status")
        return []
    except Exception as e:
        print(f"    ❌  {e}"); return []

# TEST 1 — KIJIJI
# Exact input from official Apify code sample for this actor
kj = run_actor(
    "V5XnYsUNkjXYrFvbc",   # automation-lab/kijiji-scraper
    {
        "startUrls":      [{"url": "https://www.kijiji.ca/b-jewelry-watch/city-of-toronto/gold/k0c133l1700273"}],
        "searchQuery":    "",
        "category":       "",
        "location":       "city-of-toronto",
        "maxListings":    5,
        "includeDetails": False,   # faster for test
    },
    label="Kijiji — V5XnYsUNkjXYrFvbc (automation-lab/kijiji-scraper)"
)

# TEST 2 — CRAIGSLIST
cl = run_actor(
    "1b2gJ9AWuxa5WWlOQ",
    {
        "searchQueries":  ["gold ring"],
        "city":           "toronto",
        "category":       "for_sale",
        "maxResults":     5,
        "includeDetails": False,
    },
    label="Craigslist — automation-lab/craigslist-scraper"
)

print(f"\n{'='*60}")
print(f"📊  Kijiji: {len(kj)} items  |  CL: {len(cl)} items")
total = len(kj) + len(cl)
if total > 0:
    print("\n✅  WORKING. Next steps:")
    print("   1. Railway → Variables: APIFY_API_KEY + SCRAPE_LIMIT=15")
    print("   2. git add -A && git commit -m 'apify verified' && git push")
else:
    print("\n⚠️  Still 0. Paste this output and we'll fix it.")