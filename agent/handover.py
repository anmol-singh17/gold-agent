"""
handover.py — Profit calculation, handover decision, Telegram notifications (with two-way reply)
"""
import os, requests, json
from gold_price import melt_value, get_spot_per_gram_cad, KARAT_PURITY
from dotenv import load_dotenv
load_dotenv()

def check_handover(listing, parsed):
    from scorer import score_listing
    merged = {**listing}
    if parsed.get('confirmed_karat'):  merged['karat']        = parsed['confirmed_karat']
    if parsed.get('confirmed_grams'):  merged['weight_grams'] = parsed['confirmed_grams']
    if parsed.get('hallmark_confirmed'): merged['hallmark_seen'] = True
    final_score, _ = score_listing(merged)
    has_weight   = bool(merged.get('weight_grams'))
    has_karat    = bool(merged.get('karat'))
    no_flags     = len(parsed.get('red_flags', [])) == 0
    seller_ok    = parsed.get('seller_reliability', 3) >= 3
    if final_score >= 80 and has_weight and has_karat and no_flags and seller_ok:
        return True, final_score
    if final_score >= 70 and has_weight and has_karat and parsed.get('seller_reliability',3) >= 4:
        return True, final_score
    if final_score >= 85 and parsed.get('seller_reliability',3) >= 4:
        return True, final_score
    return False, final_score

def calc_profit(grams, karat, asking_price):
    if not grams or not karat:
        return {"melt_value_cad":None,"asking_price_cad":asking_price,
                "gross_margin_cad":None,"margin_pct":None,
                "dealer_buyback_profit":None,"private_sale_profit":None}
    spot = get_spot_per_gram_cad()
    mv   = melt_value(float(grams), int(karat), spot)
    return {
        "melt_value_cad":       mv,
        "asking_price_cad":     asking_price,
        "gross_margin_cad":     round(mv - asking_price, 2),
        "margin_pct":           round((mv - asking_price) / mv * 100, 1) if mv > 0 else 0,
        "dealer_buyback_profit":round(mv * 0.85 - asking_price, 2),
        "private_sale_profit":  round(mv * 0.95 - asking_price, 2),
        "spot_per_gram":        round(spot, 2),
        "purity_pct":           round(KARAT_PURITY.get(int(karat),0)*100, 1),
        "weight_grams":         grams,
        "karat":                karat,
    }

def _post_telegram(msg):
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(f"[TELEGRAM] Not configured. Would send:\n{msg[:200]}")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id":chat_id,"text":msg,"parse_mode":"Markdown",
                  "disable_web_page_preview":False}, timeout=10)
        if r.status_code != 200:
            print(f"[TELEGRAM] Error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[TELEGRAM] Error: {e}")

def send_handover_telegram(listing, conv, parsed, profit, score):
    karat  = parsed.get('confirmed_karat') or listing.get('karat','?')
    grams  = parsed.get('confirmed_grams') or listing.get('weight_grams','?')
    flags  = ', '.join(parsed.get('red_flags',[])) or 'None ✓'
    mv     = profit.get('melt_value_cad')
    margin = profit.get('gross_margin_cad')
    pct    = profit.get('margin_pct')

    profit_line = (f"Melt: *${mv:.2f} CAD*\nProfit: *${margin:.2f} ({pct:.1f}%)*\n"
                   f"→ Dealer: ${profit.get('dealer_buyback_profit'):.2f}\n"
                   f"→ Private: ${profit.get('private_sale_profit'):.2f}"
                   ) if mv else "Cannot calculate — missing weight/karat"

    msg = (f"🏆 *GOLD DEAL — SCORE {score}/100*\n\n"
           f"*{listing.get('title','?')[:60]}*\n"
           f"📍 {listing.get('platform','').upper()} | Toronto\n"
           f"💰 Asking: *${listing.get('price_cad','?')} CAD*\n\n"
           f"*✅ Confirmed:*\n"
           f"Karat: {karat}K | Weight: {grams}g\n"
           f"Condition: {parsed.get('condition','?')}\n"
           f"Reason selling: {parsed.get('reason_selling','not stated')}\n\n"
           f"*📊 Profit:*\n{profit_line}\n\n"
           f"Seller: {parsed.get('seller_reliability','?')}/5 | Flags: {flags}\n\n"
           f"[🔗 Listing]({listing.get('url','')})")
    if conv and conv.get('conversation_url'):
        msg += f" | [💬 Chat]({conv['conversation_url']})"
    msg += f"\n\n_Reply *buy {listing['id']}* or *pass {listing['id']}* to decide_"
    _post_telegram(msg)

def send_alert_telegram(message):
    _post_telegram(f"⚠️ *Gold Agent Alert*\n\n{message}")

def send_daily_summary_telegram(stats):
    _post_telegram(
        f"📋 *Gold Agent — Daily Summary*\n\n"
        f"🔍 Found today: {stats.get('found',0)}\n"
        f"⭐ Score ≥70: {stats.get('high_score',0)}\n"
        f"💬 Messages sent: {stats.get('messages_sent',0)}\n"
        f"📬 Awaiting reply: {stats.get('awaiting_reply',0)}\n"
        f"🏆 Handovers: {stats.get('handovers',0)}\n"
        f"👻 Ghosted: {stats.get('ghosted',0)}\n\n"
        f"_Agent running normally_ ✓"
    )

# ── TWO-WAY TELEGRAM: poll for buy/pass replies ───────────────────────────────
def check_telegram_replies():
    """
    Poll Telegram for 'buy {id}' or 'pass {id}' replies from your friend.
    Returns list of (action, listing_id) tuples.
    """
    import db
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token: return []
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                         params={"timeout":0,"offset":-10}, timeout=10)
        updates = r.json().get("result", [])
        actions = []
        for upd in updates:
            text = upd.get("message",{}).get("text","").strip().lower()
            if text.startswith("buy "):
                try:
                    lid = int(text.split()[1])
                    actions.append(("approved", lid))
                except: pass
            elif text.startswith("pass "):
                try:
                    lid = int(text.split()[1])
                    actions.append(("rejected", lid))
                except: pass
        for action, lid in actions:
            try:
                db.update_listing_status(lid, action)
                _post_telegram(f"✅ Listing {lid} marked as *{action}*")
                db.log_agent_event("telegram", f"Reply action: {action} listing {lid}")
            except: pass
        return actions
    except Exception as e:
        print(f"[TELEGRAM] Reply check error: {e}")
        return []
