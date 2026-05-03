"""
scraper.py — 4 platforms: Kijiji, Craigslist, Facebook, eBay Canada
Full fallback chains, price drop detection, cross-platform dedup, pre-filter before Gemini
"""
import os, re, json, asyncio, time, requests, feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import db
load_dotenv()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-CA,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.google.com/',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'cross-site',
}
KIJIJI_SEARCHES = [
    "18k-gold-ring",
    "14k-gold-ring",
    "gold-chain-toronto",
    "gold-bracelet-toronto",
    "22k-gold-jewellery",
    "gold-pendant-toronto",
]
CL_RSS = [
    "https://toronto.craigslist.org/search/jwa?query=gold+ring&format=rss",
    "https://toronto.craigslist.org/search/jwa?query=18k+gold+chain&format=rss",
    "https://toronto.craigslist.org/search/jwa?query=14k+gold&format=rss",
    "https://toronto.craigslist.org/search/jwa?query=gold+bracelet&format=rss",
    "https://toronto.craigslist.org/search/jwa?query=gold+pendant&format=rss",
]
FB_KEYWORDS = ["18k gold ring","gold chain selling","14k gold jewelry","gold bracelet","22k gold","gold pendant"]
EBAY_KEYWORDS = ["18k gold ring","14k gold chain","gold bracelet","gold pendant 18k","22k gold jewelry"]
EXCLUDE_HARD = ["silver","plated","filled","gold tone","costume","fashion","stainless","brass","vermeil","rolled gold","gold color","gold colour","fake","replica"]
EXCLUDE_PRICE_MIN = 25.0

def pre_filter(title, price, description=""):
    """Fast pre-filter BEFORE any Gemini API call. Saves 30-40% on API costs."""
    text = (title+" "+(description or "")).lower()
    if any(k in text for k in EXCLUDE_HARD):
        return False, f"excluded keyword in '{title[:30]}'"
    if price and price < EXCLUDE_PRICE_MIN:
        return False, f"price ${price} below minimum ${EXCLUDE_PRICE_MIN}"
    return True, "ok"

def extract_price(text):
    m = re.search(r'\$[\d,]+', str(text))
    return float(m.group().replace('$','').replace(',','')) if m else 0.0

def _safe_get(url, timeout=12, retries=2):
    """HTTP GET with retries and polite delay."""
    for attempt in range(retries):
        try:
            time.sleep(1.0 + attempt * 0.5)
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt == retries - 1:
                raise
    return None

# ── KIJIJI ────────────────────────────────────────────────────────────────────
def fetch_kijiji_detail(url):
    try:
        resp = _safe_get(url)
        soup = BeautifulSoup(resp.text,'html.parser')
        desc_el = soup.select_one('[class*="descriptionContainer"]') or soup.select_one('[itemprop="description"]')
        desc = desc_el.get_text(strip=True)[:1000] if desc_el else ""
        imgs = []
        for img in soup.select('img[src*="kijiji"]')[:5]:
            src = img.get('src','')
            if src and 'placeholder' not in src and src.startswith('http'):
                imgs.append(src)
        return desc, imgs
    except Exception as e:
        return "", []

def run_kijiji_scrape():
    # Try Scrapling first (stealth), fall back to requests
    try:
        from scrapling.fetchers import StealthyFetcher
        fetcher = StealthyFetcher()
        use_scrapling = True
        db.log_agent_event("scrape","Kijiji: using Scrapling stealth fetcher")
    except ImportError:
        use_scrapling = False
        db.log_agent_event("scrape","Kijiji: Scrapling not available, using requests fallback")

    total_new = 0
    for s in KIJIJI_SEARCHES:
        try:
            url = f"https://www.kijiji.ca/b-buy-sell/toronto/{s}/k0c0l1700273"
            try:
                if use_scrapling:
                    page = fetcher.fetch(url)
                    html = page.html
                else:
                    html = _safe_get(url).text
            except Exception as e:
                db.log_agent_event("scrape", f"Kijiji fetch failed '{s}', trying requests fallback: {e}", level="warn")
                try:
                    html = _safe_get(url).text
                except Exception as e2:
                    db.log_agent_event("scrape", f"Kijiji both methods failed '{s}': {e2}", level="error")
                    continue

            soup = BeautifulSoup(html,'html.parser')
            cards = soup.select('ul[class*="results"] li') or soup.select('div[data-ad-id]')

            if not cards:
                db.log_agent_event("scrape", f"Kijiji '{s}': no cards found — selectors may need update", level="warn")
                continue

            new = 0
            for card in cards[:40]:
                try:
                    title_el = card.select_one('a[href*="/v-"] h3') or card.select_one('h3')
                    link_el  = card.select_one('a[href*="/v-"]')
                    price_el = card.select_one('[data-testid="listing-price"]') or card.select_one('[class*="price"]')
                    if not title_el or not link_el: continue
                    title = title_el.get_text(strip=True)
                    href  = link_el.get('href','')
                    if not href.startswith('http'): href = 'https://www.kijiji.ca' + href
                    ext_id = f"kijiji_{href.split('/')[-1]}"
                    price  = extract_price(price_el.get_text() if price_el else '')

                    # Pre-filter (fast, no API)
                    ok, reason = pre_filter(title, price)
                    if not ok: continue

                    # Price drop detection
                    existing = db.get_listing_price(ext_id)
                    if existing:
                        old_price, lid = existing
                        if price and old_price and price < old_price * 0.95:
                            db.update_listing_price(lid, price, old_price)
                            db.log_agent_event("scrape", f"Price drop: '{title[:35]}' ${old_price:.0f}→${price:.0f}")
                        continue

                    # Cross-platform dedup
                    if db.get_duplicate_check(title, price): continue

                    # Fetch detail page
                    desc, imgs = fetch_kijiji_detail(href)
                    db.save_listing({'platform':'kijiji','external_id':ext_id,'url':href,
                        'title':title,'description':desc,'price_cad':price,
                        'city':'toronto','images':imgs,'status':'new'})
                    new += 1
                except: continue

            total_new += new
            db.log_agent_event("scrape", f"Kijiji '{s}': {new} new listings")
        except Exception as e:
            db.log_agent_event("scrape", f"Kijiji search error '{s}': {e}", level="error")
        time.sleep(2)  # polite delay between keyword requests

    return total_new

# ── CRAIGSLIST ────────────────────────────────────────────────────────────────
def fetch_cl_detail(url):
    try:
        resp = _safe_get(url)
        soup = BeautifulSoup(resp.text,'html.parser')
        desc_el = soup.select_one('#postingbody')
        desc = desc_el.get_text(strip=True)[:800] if desc_el else ""
        imgs = []
        for img in soup.select('img.thumb')[:5]:
            src = img.get('src','')
            if src and src.startswith('http'): imgs.append(src.replace('50x50','600x450'))
        return desc, imgs
    except:
        return "", []

def run_craigslist_scrape():
    total_new = 0
    for feed_url in CL_RSS:
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                db.log_agent_event("scrape", f"CL RSS returned empty feed: {feed_url}", level="warn")
                continue
            new = 0
            for entry in feed.entries:
                try:
                    raw_id = entry.get('id','') or entry.get('link','')
                    ext_id = f"cl_{raw_id.split('/')[-1].split('.')[0]}"
                    if not ext_id or ext_id=='cl_': continue
                    title = entry.get('title','')
                    price = extract_price(title)
                    ok, reason = pre_filter(title, price)
                    if not ok or db.listing_exists(ext_id): continue
                    link = entry.get('link','')
                    desc, imgs = fetch_cl_detail(link)
                    db.save_listing({'platform':'craigslist','external_id':ext_id,'url':link,
                        'title':title,'description':desc,'price_cad':price,
                        'city':'toronto','images':imgs,'status':'new'})
                    new += 1
                except: continue
            total_new += new
            db.log_agent_event("scrape", f"Craigslist RSS: {new} new listings")
        except Exception as e:
            db.log_agent_event("scrape", f"CL RSS error: {e}", level="error")
    return total_new

# ── EBAY CANADA ───────────────────────────────────────────────────────────────
def run_ebay_scrape():
    """eBay Canada via Browse API (free, official). Needs EBAY_APP_ID in .env."""
    app_id = os.getenv("EBAY_APP_ID","")
    if not app_id:
        db.log_agent_event("scrape","eBay skipped — EBAY_APP_ID not set in .env (optional)")
        return 0

    total_new = 0
    for keyword in EBAY_KEYWORDS:
        try:
            resp = requests.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers={
                    "Authorization": f"Bearer {_get_ebay_token(app_id)}",
                    "X-EBAY-C-MARKETPLACE-ID": "EBAY_CA",
                    "Content-Type": "application/json",
                },
                params={
                    "q": keyword,
                    "category_ids": "281",  # Jewelry & Watches
                    "filter": "price:[30..2000],priceCurrency:CAD,itemLocationCountry:CA,conditionIds:{1000|1500|2000|2500}",
                    "sort": "newlyListed",
                    "limit": "20",
                },
                timeout=15
            )
            if resp.status_code != 200:
                db.log_agent_event("scrape", f"eBay API error: {resp.status_code}", level="warn")
                continue

            items = resp.json().get("itemSummaries", [])
            new = 0
            for item in items:
                try:
                    ext_id = f"ebay_{item['itemId']}"
                    if db.listing_exists(ext_id): continue
                    title = item.get('title','')
                    price = float(item.get('price',{}).get('value',0))
                    ok, _ = pre_filter(title, price)
                    if not ok: continue
                    imgs = [item['image']['imageUrl']] if item.get('image') else []
                    db.save_listing({'platform':'ebay','external_id':ext_id,
                        'url':item.get('itemWebUrl',''),'title':title,'description':'',
                        'price_cad':price,'city':'canada','images':imgs,'status':'new'})
                    new += 1
                except: continue
            total_new += new
            db.log_agent_event("scrape", f"eBay '{keyword}': {new} new")
            time.sleep(0.5)
        except Exception as e:
            db.log_agent_event("scrape", f"eBay error '{keyword}': {e}", level="error")
    return total_new

_ebay_token_cache = {"token": None, "expires": None}
def _get_ebay_token(app_id):
    import base64, datetime as dt
    if _ebay_token_cache["token"] and _ebay_token_cache["expires"] and \
       dt.datetime.now() < _ebay_token_cache["expires"]:
        return _ebay_token_cache["token"]
    client_secret = os.getenv("EBAY_CLIENT_SECRET","")
    creds = base64.b64encode(f"{app_id}:{client_secret}".encode()).decode()
    resp = requests.post("https://api.ebay.com/identity/v1/oauth2/token",
        headers={"Authorization":f"Basic {creds}","Content-Type":"application/x-www-form-urlencoded"},
        data="grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope/buy.item.summary",
        timeout=10)
    token = resp.json().get("access_token","")
    expires_in = resp.json().get("expires_in", 7200)
    import datetime as dt2
    _ebay_token_cache["token"] = token
    _ebay_token_cache["expires"] = dt2.datetime.now() + dt2.timedelta(seconds=expires_in - 60)
    return token

# ── FACEBOOK ──────────────────────────────────────────────────────────────────
async def run_fb_scrape(playwright_ctx, keyword="gold ring"):
    """FB Marketplace scraping via Browser Use with Gemini. Falls back gracefully."""
    try:
        from browser_use import Agent
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=os.getenv("GEMINI_API_KEY"))
        agent = Agent(
            task=f"""Go to: https://www.facebook.com/marketplace/toronto/search/?query={keyword.replace(' ','%20')}
I am already logged in to Facebook. DO NOT try to log in.
Wait for page to fully load. Scroll down slowly twice.
Extract up to 20 non-sponsored listings. For each collect:
  title, price (number in CAD only, no $ sign), url (full Facebook URL), image (thumbnail URL)
Return ONLY a valid JSON array — no other text, no markdown:
[{{"title":"...","price":0,"url":"...","image":"..."}}]""",
            llm=llm, browser_context=playwright_ctx)
        result = await agent.run(max_steps=20)
        raw = (result.final_result() or "[]").strip().replace('```json','').replace('```','').strip()
        # Safety check — scan response for ban signals
        from safety import check_browser_response_for_bans
        if check_browser_response_for_bans(raw, "facebook"):
            return 0
        items = json.loads(raw)
        new = 0
        for item in items:
            try:
                item_url = item.get('url','')
                if not item_url: continue
                parts = item_url.rstrip('/').split('/')
                item_id = parts[-1] if parts[-1] else parts[-2]
                ext_id = f"fb_{item_id}"
                title = item.get('title','')
                price = float(item.get('price') or 0)
                ok, _ = pre_filter(title, price)
                if not ok or db.listing_exists(ext_id): continue
                if db.get_duplicate_check(title, price): continue
                db.save_listing({'platform':'facebook','external_id':ext_id,'url':item_url,
                    'title':title,'description':'','price_cad':price,'city':'toronto',
                    'images':[item['image']] if item.get('image') else [],'status':'new'})
                new += 1
            except: continue
        db.log_agent_event("scrape", f"Facebook '{keyword}': {new} new")
        return new
    except Exception as e:
        db.log_agent_event("scrape", f"FB scrape error '{keyword}': {e}", level="error")
        return 0

async def run_all_fb_scrapes(playwright_ctx):
    total = 0
    for kw in FB_KEYWORDS:
        total += await run_fb_scrape(playwright_ctx, kw)
        await asyncio.sleep(random.uniform(3,7))
    return total

import random
