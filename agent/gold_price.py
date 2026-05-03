"""
gold_price.py — Fetch live gold spot price from goldpricez.com (free, no API key)
Cached every 15 minutes to avoid unnecessary calls.
"""
import requests
from datetime import datetime, timedelta

_cache = {"price": None, "at": None}

KARAT_PURITY = {
    9:  0.375,
    10: 0.417,
    14: 0.585,
    18: 0.750,
    22: 0.917,
    24: 1.000,
}

def get_spot_per_gram_cad():
    """Returns CAD price per gram of pure 24K gold. Cached 15 min."""
    if _cache["price"] and _cache["at"] and datetime.now() - _cache["at"] < timedelta(minutes=15):
        return _cache["price"]
    try:
        r = requests.get("https://data-asg.goldpricez.com/dbXRates/CAD", timeout=10)
        data = r.json()
        per_gram = float(data["xauPrice"]) / 31.1035  # troy oz → grams
        _cache["price"] = per_gram
        _cache["at"] = datetime.now()
        print(f"[GOLD PRICE] ${per_gram:.2f}/gram CAD (24K spot)")
        return per_gram
    except Exception as e:
        print(f"[GOLD PRICE] ERROR fetching price: {e}")
        # Return a fallback so the agent doesn't crash
        fallback = _cache["price"] or 100.0
        return fallback

def melt_value(grams, karat, spot_per_gram=None):
    """Calculate melt value in CAD for given grams and karat."""
    if not spot_per_gram:
        spot_per_gram = get_spot_per_gram_cad()
    purity = KARAT_PURITY.get(int(karat), 0)
    return round(grams * purity * spot_per_gram, 2)

def melt_per_gram(karat):
    """How much is 1 gram of this karat worth right now."""
    spot = get_spot_per_gram_cad()
    return round(KARAT_PURITY.get(int(karat), 0) * spot, 2)

if __name__ == "__main__":
    spot = get_spot_per_gram_cad()
    print(f"\nGold Spot Price (CAD):")
    print(f"  24K: ${spot:.2f}/gram")
    for k in [10, 14, 18, 22]:
        print(f"  {k}K: ${melt_per_gram(k):.2f}/gram  (purity {KARAT_PURITY[k]*100:.1f}%)")
    print(f"\nExample: 10g of 18K gold = ${melt_value(10, 18):.2f} CAD melt value")
