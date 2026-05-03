"""
scorer.py — Extract karat/weight via Gemini LLM + Vision, calculate deal score 0-100
"""
import os
import json
import base64
import urllib.request
from google import genai
from gold_price import melt_value, get_spot_per_gram_cad, KARAT_PURITY
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_MODEL = "gemini-2.5-flash"
_LITE_MODEL = "gemini-2.5-flash"  # use same, swap to flash-lite if cost is concern


def extract_from_text(title, description):
    """Use Gemini to extract karat, weight, item type from listing text."""
    prompt = f"""
Analyze this gold/jewelry marketplace listing. Return ONLY valid JSON, no markdown, no explanation.

TITLE: {title}
DESCRIPTION: {description}

Return this exact JSON:
{{
    "weight_grams": null or float (ONLY if explicitly stated like "5g" or "3.2 grams" — do NOT guess),
    "karat": null or int (10/14/18/22/24 — from "18K", "750", "18ct", "18 karat"),
    "hallmark_in_text": null or string (exact stamp text like "750", "18KT", "585"),
    "item_type": null or string (ring/chain/bracelet/pendant/earrings/bangle/set),
    "condition": null or string (excellent/good/fair/poor — if mentioned),
    "confidence": float 0.0-1.0 (how confident you are in karat AND weight together)
}}

RULES:
- weight_grams: ONLY if explicitly stated. Do NOT guess from size/description.
- karat conversions: 375=9K, 417=10K, 585=14K, 750=18K, 916=22K, 999=24K
- If info is missing, return null — never guess.
- confidence should be high only if BOTH karat AND weight are clearly stated.
"""
    try:
        resp = _client.models.generate_content(model=_MODEL, contents=prompt)
        text = resp.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"[SCORER] Text extraction error: {e}")
        return {"weight_grams": None, "karat": None, "confidence": 0.1}


def extract_from_image(image_url):
    """Download image, send to Gemini Vision, read any hallmark stamps."""
    if not image_url:
        return {"hallmark_found": False, "confidence": 0.0}
    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            img_data = r.read()
            img_b64 = base64.b64encode(img_data).decode()
            # Determine mime type
            mime = "image/jpeg"
            if image_url.lower().endswith(".png"):
                mime = "image/png"
            elif image_url.lower().endswith(".webp"):
                mime = "image/webp"
    except Exception as e:
        print(f"[SCORER] Image download error: {e}")
        return {"hallmark_found": False, "confidence": 0.0}

    vision_prompt = """Look carefully at this jewelry photo for any stamps or hallmarks.
Common marks: 375(9K) 417(10K) 585(14K) 750(18K) 916(22K) 999(24K)
Also look for: 10K 14K 18K 22K 10KT 14KT 18KT PT950 925(silver)

Return ONLY valid JSON, no markdown:
{
    "hallmark_found": true or false,
    "hallmark_text": null or string (exactly what you see — e.g. "750"),
    "karat": null or int,
    "confidence": float 0.0-1.0,
    "notes": string (brief description of what you see in the image)
}"""
    try:
        from google.genai import types as genai_types
        resp = _client.models.generate_content(
            model=_MODEL,
            contents=[
                genai_types.Part.from_bytes(data=img_data, mime_type=mime),
                vision_prompt,
            ]
        )
        text = resp.text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"[SCORER] Vision extraction error: {e}")
        return {"hallmark_found": False, "confidence": 0.0}


def score_listing(listing):
    """
    Score a listing 0-100 based on deal quality.
    Returns (score: int, reasons: list[str])
    """
    score = 0
    reasons = []

    spot = get_spot_per_gram_cad()
    karat = listing.get("karat")
    grams = listing.get("weight_grams")
    price = listing.get("price_cad", 0) or 0

    # ── PRICE vs MELT VALUE ──────────────────────────────────────────────
    if karat and grams and price > 0:
        mv = melt_value(grams, karat, spot)
        ratio = price / mv  # < 1.0 means listed below melt = potential deal

        if ratio < 0.45:
            score += 55
            reasons.append(f"Price is {ratio:.0%} of melt — exceptional deal")
        elif ratio < 0.60:
            score += 40
            reasons.append(f"Price is {ratio:.0%} of melt — very good")
        elif ratio < 0.75:
            score += 28
            reasons.append(f"Price is {ratio:.0%} of melt — good")
        elif ratio < 0.90:
            score += 15
            reasons.append(f"Price is {ratio:.0%} of melt — fair")
        elif ratio < 1.00:
            score += 5
            reasons.append("Just under melt — low margin")
        else:
            score -= 10
            reasons.append(f"Price is {ratio:.0%} of melt — above melt, not a deal")

        # Store melt value for later
        listing["melt_value_cad"] = mv
    else:
        # Unknown weight/karat — still potentially worth asking
        score += 12
        reasons.append("Weight or karat unknown — needs verification via message")

    # ── CONFIDENCE BONUSES ───────────────────────────────────────────────
    if listing.get("hallmark_seen"):
        score += 18
        reasons.append("Hallmark confirmed in photo")

    if karat and grams:
        score += 10
        reasons.append("Both karat and weight are stated in listing")

    if listing.get("confidence", 0) > 0.8:
        score += 5

    if karat and int(karat) >= 18:
        score += 5
        reasons.append(f"High karat ({karat}K) — better resale value")

    # ── SANITY CHECKS ────────────────────────────────────────────────────
    if price < 40:
        score -= 20
        reasons.append("Price too low — likely not real gold")

    if price > 5000:
        score -= 5
        reasons.append("High price — harder deal to execute")

    # Cap between 0 and 100
    final = min(100, max(0, score))
    return final, reasons


def run_scorer_for_listing(listing):
    """
    Full scoring pipeline for one listing:
    text extraction → vision → merge → score
    Returns updated listing dict.
    """
    # Step 1: Text extraction
    extracted = extract_from_text(
        listing.get("title", ""),
        listing.get("description", "")
    )

    # Step 2: Vision on first image (if available)
    vision = {"hallmark_found": False, "confidence": 0.0}
    images = listing.get("images") or []
    if images and images[0]:
        vision = extract_from_image(images[0])

    # Step 3: Merge — vision karat fills in if text didn't get it
    if vision.get("karat") and not extracted.get("karat"):
        extracted["karat"] = vision["karat"]

    if vision.get("hallmark_found"):
        extracted["hallmark_seen"] = True
    else:
        extracted.setdefault("hallmark_seen", False)

    # Step 4: Build merged listing
    merged = {**listing}
    for k, v in extracted.items():
        if v is not None:
            merged[k] = v

    # Step 5: Score
    score, reasons = score_listing(merged)

    return score, merged, reasons
