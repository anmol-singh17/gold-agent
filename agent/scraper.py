"""
scraper.py — Apify scraping. Input schema from official Apify code sample.

Kijiji:     automation-lab/kijiji-scraper (actor ID: V5XnYsUNkjXYrFvbc)
            Input: startUrls, searchQuery, category, location, maxListings, includeDetails

Craigslist: automation-lab/craigslist-scraper
            Input: searchQueries (array), city, category, maxResults, includeDetails

eBay:       Official Browse API — free, no Apify cost.
"""
import os, re, time, requests
from dotenv import load_dotenv
import db

load_dotenv()

APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
APIFY_BASE    = "https://api.apify.com/v2"
SCRAPE_LIMIT  = int(os.getenv("SCRAPE_LIMIT", "15"))

# Kijiji jewelry & watches category URLs for Toronto
# c133 = Jewelry & Watches, l1700273 = City of Toronto
KIJIJI_SEARCH_URLS = [
    "https://www.kijiji.ca/b-jewelry-watch/city-of-toronto/gold-ring/k0c133l1700273",
    "https://www.kijiji.ca/b-jewelry-watch/city-of-toronto/gold-chain/k0c133l1700273",
    "https://www.kijiji.ca/b-jewelry-watch/city-of-toronto/gold-bracelet/k0c133l1700273",
    "https://www.kijiji.ca/b-jewelry-watch/city-of-toronto/gold-pendant/k0c133l1700273",
    "https://www.kijiji.ca/b-buy-sell/city-of-toronto/22k-gold/k0c0l1700273",
]

CL_KEYWORDS = ["18k gold ring", "14k gold chain", "gold bracelet", "gold pendant"]

EXCLUDE_HARD = [
    "silver","plated","filled","gold tone","costume","fashion","stainless",
    "brass","vermeil","rolled gold","gold color","gold colour","fake","replica",
]
EXCLUDE_PRICE_MIN = 25.0

def pre_filter(title, price, description=""):
    text = (title + " " + (description or "")).lower()
    if any(k in text for k in EXCLUDE_HARD):
        return False, "excluded keyword"
    if price and price < EXCLUDE_PRICE_MIN:
        return False, f"price ${price} too low"
    return True, "ok"

def _parse_price(raw):
    if raw is None: return 0.0
    if isinstance(raw, (int, float)): return float(raw)
    cleaned = re.sub(r"[^\d.]", "", str(raw))
    return float(cleaned) if cleaned else 0.0

def _apify_run(actor_id, run_input, timeout_secs=240):
    if not APIFY_API_KEY:
        db.log_agent_event("scrape", "APIFY_API_KEY not set", level="error")
        return []
    url    = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": APIFY_API_KEY, "timeout": timeout_secs, "memory": 512}
    try:
        resp = requests.post(url, json=run_input, params=params, timeout=timeout_secs + 30)
        if resp.status_code in (200, 201):
            data = resp.json()
            if isinstance(data, list): return data
            if isinstance(data, dict): return data.get("items", data.get("data", []))
            return []
        else:
            db.log_agent_event("scrape",
                f"Apify {actor_id} HTTP {resp.status_code}: {resp.text[:400]}", level="error")
            return []
    except requests.exceptions.Timeout:
        db.log_agent_event("scrape", f"Apify {actor_id} timed out", level="warn")
        return []
    except Exception as e:
        db.log_agent_event("scrape", f"Apify {actor_id} error: {e}", level="error")
        return []

def _save_listing(data):
    ext_id = data.get("external_id", "")
    title  = data.get("title", "")
    price  = data.get("price_cad", 0) or 0
    if not ext_id or not title: return False
    ok, _ = pre_filter(title, price, data.get("description", ""))
    if not ok: return False
    existing = db.get_listing_price(ext_id)
    if existing:
        old_price, lid = existing
        if price and old_price and price < old_price * 0.95:
            db.update_listing_price(lid, price, old_price)
            db.log_agent_event("scrape", f"Price drop '{title[:35]}' ${old_price:.0f}→${price:.0f}")
        return False
    if db.get_duplicate_check(title, price): return False
    db.save_listing({
        "platform":    data["platform"],
        "external_id": ext_id,
        "url":         data.get("url", ""),
        "title":       title,
        "description": data.get("description", ""),
        "price_cad":   price,
        "city":        data.get("city", "toronto"),
        "images":      data.get("images", []),
        "image_url":   data.get("image_url", ""),
        "status":      "new",
    })
    return True

# ── KIJIJI ────────────────────────────────────────────────────────────────────
def run_kijiji_scrape():
    """
    Actor: automation-lab/kijiji-scraper (V5XnYsUNkjXYrFvbc)
    Schema confirmed from official Apify code sample:
      startUrls, searchQuery, category, location, maxListings, includeDetails
    """
    ACTOR = "V5XnYsUNkjXYrFvbc"   # automation-lab/kijiji-scraper
    total_new = 0

    for search_url in KIJIJI_SEARCH_URLS:
        slug = search_url.split("/")[-2]
        db.log_agent_event("scrape", f"Kijiji: '{slug}' limit={SCRAPE_LIMIT}")

        items = _apify_run(ACTOR, {
            "startUrls":      [{"url": search_url}],
            "searchQuery":    "",       # empty = use URL's built-in search
            "category":       "",       # empty = use URL's category
            "location":       "city-of-toronto",
            "maxListings":    SCRAPE_LIMIT,
            "includeDetails": True,
        }, timeout_secs=240)

        if not items:
            db.log_agent_event("scrape", f"Kijiji '{slug}': 0 results", level="warn")
            time.sleep(1)
            continue

        new = 0
        for item in items:
            try:
                url   = item.get("url","") or item.get("adUrl","")
                title = item.get("title","") or item.get("name","")
                price = _parse_price(item.get("price") or item.get("priceAmount"))
                imgs  = item.get("images",[]) or []
                if imgs and isinstance(imgs[0], dict):
                    imgs = [i.get("url","") or i.get("src","") for i in imgs]
                imgs   = [i for i in imgs if i]
                tail   = url.rstrip("/").split("/")[-1] if url else ""
                ext_id = f"kijiji_{tail}" if tail else ""
                if _save_listing({
                    "platform": "kijiji", "external_id": ext_id, "url": url,
                    "title": title,
                    "description": item.get("description","") or item.get("body",""),
                    "price_cad": price, "city": "toronto",
                    "images": imgs[:5], "image_url": imgs[0] if imgs else "",
                }): new += 1
            except Exception as e:
                db.log_agent_event("scrape", f"Kijiji parse err: {e}", level="warn")

        total_new += new
        db.log_agent_event("scrape", f"Kijiji '{slug}': {new} new (from {len(items)})")
        time.sleep(1)

    return total_new

# ── CRAIGSLIST ────────────────────────────────────────────────────────────────
def run_craigslist_scrape():
    """
    Actor: automation-lab/craigslist-scraper
    Schema confirmed: searchQueries (array), city, category, maxResults, includeDetails
    """
    ACTOR = "1b2gJ9AWuxa5WWlOQ"
    total_new = 0

    db.log_agent_event("scrape", f"CL: {len(CL_KEYWORDS)} keywords, limit={SCRAPE_LIMIT}")
    items = _apify_run(ACTOR, {
        "searchQueries":  CL_KEYWORDS,
        "city":           "toronto",
        "category":       "for_sale",
        "maxResults":     SCRAPE_LIMIT,
        "includeDetails": True,
    }, timeout_secs=240)

    if not items:
        db.log_agent_event("scrape", "CL: 0 results (toronto jewelry sparse — normal)", level="warn")
        return 0

    for item in items:
        try:
            url   = item.get("url","") or item.get("link","") or item.get("postUrl","")
            title = item.get("title","") or item.get("name","")
            price = _parse_price(item.get("price"))
            raw_id = url.rstrip("/").split("/")[-1].split(".")[0] if url else ""
            ext_id = f"cl_{raw_id}" if raw_id else ""
            imgs = item.get("images",[]) or []
            if imgs and isinstance(imgs[0], dict):
                imgs = [i.get("url","") or i.get("src","") for i in imgs]
            imgs = [i for i in imgs if i]
            if _save_listing({
                "platform": "craigslist", "external_id": ext_id, "url": url,
                "title": title,
                "description": item.get("description","") or item.get("body",""),
                "price_cad": price, "city": "toronto",
                "images": imgs[:5], "image_url": imgs[0] if imgs else "",
            }): total_new += 1
        except Exception as e:
            db.log_agent_event("scrape", f"CL parse err: {e}", level="warn")

    db.log_agent_event("scrape", f"CL: {total_new} new (from {len(items)} fetched)")
    return total_new

# ── EBAY CANADA ───────────────────────────────────────────────────────────────
def run_ebay_scrape():
    """Official eBay Browse API — free, zero Apify cost. Needs EBAY_APP_ID."""
    app_id = os.getenv("EBAY_APP_ID","")
    if not app_id:
        db.log_agent_event("scrape", "eBay skipped — EBAY_APP_ID not set (optional)")
        return 0
    import base64
    KEYWORDS = ["18k gold ring canada", "14k gold chain canada", "22k gold bracelet canada"]
    total_new = 0
    try:
        creds = base64.b64encode(
            f"{app_id}:{os.getenv('EBAY_CLIENT_SECRET','')}".encode()).decode()
        token = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={"Authorization": f"Basic {creds}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data="grant_type=client_credentials"
                 "&scope=https://api.ebay.com/oauth/api_scope/buy.item.summary",
            timeout=10).json().get("access_token","")
        if not token: return 0
    except: return 0
    for kw in KEYWORDS:
        try:
            items = requests.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers={"Authorization": f"Bearer {token}",
                         "X-EBAY-C-MARKETPLACE-ID": "EBAY_CA"},
                params={"q": kw, "category_ids": "281",
                        "filter": "price:[30..2000],priceCurrency:CAD,itemLocationCountry:CA",
                        "sort": "newlyListed", "limit": str(SCRAPE_LIMIT)},
                timeout=15).json().get("itemSummaries",[])
            new = 0
            for item in items:
                ext_id = f"ebay_{item['itemId']}"
                price  = float(item.get("price",{}).get("value",0))
                title  = item.get("title","")
                ok, _  = pre_filter(title, price)
                if not ok or db.listing_exists(ext_id): continue
                imgs = [item["image"]["imageUrl"]] if item.get("image") else []
                db.save_listing({"platform":"ebay","external_id":ext_id,
                    "url":item.get("itemWebUrl",""),"title":title,"description":"",
                    "price_cad":price,"city":"canada",
                    "images":imgs,"image_url":imgs[0] if imgs else "","status":"new"})
                new += 1
            total_new += new
            db.log_agent_event("scrape", f"eBay '{kw}': {new} new")
        except Exception as e:
            db.log_agent_event("scrape", f"eBay '{kw}' error: {e}", level="error")
    return total_new

# ── FACEBOOK ──────────────────────────────────────────────────────────────────
def run_fb_scrape():
    db.log_agent_event("scrape", "FB skipped — enable after Kijiji/CL confirmed working")
    return 0