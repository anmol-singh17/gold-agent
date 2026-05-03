"""
messenger.py — Human-like messaging with full safety checks, auto-relogin, ban detection.
Every action goes through safety checks. Nothing sends without approval.
"""
import os, json, asyncio, random, base64
from google import genai
from dotenv import load_dotenv
import db, safety
from human_browser import human_delay, human_type, human_click, pre_action_warmup, reading_delay, get_random_user_agent
load_dotenv()
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_MODEL = "gemini-2.5-flash"

def _load_session(platform):
    local = f"sessions/{platform}_session.json"
    if os.path.exists(local): return local
    b64 = os.getenv(f"{platform.upper()}_SESSION_B64")
    if b64:
        os.makedirs("sessions",exist_ok=True)
        with open(local,'w') as f: f.write(base64.b64decode(b64).decode())
        return local
    return None

async def _auto_relogin(platform, playwright_instance):
    db.log_agent_event("session",f"{platform} session expired — auto re-login starting",level="warn")
    email    = os.getenv(f"{platform.upper()}_EMAIL","")
    password = os.getenv(f"{platform.upper()}_PASSWORD","")
    if not email or not password:
        db.log_agent_event("session",f"No credentials for {platform} in .env — cannot re-login",level="error")
        from handover import send_alert_telegram
        send_alert_telegram(f"❌ {platform} session expired and no credentials set. Add {platform.upper()}_EMAIL and {platform.upper()}_PASSWORD to .env")
        return False
    try:
        browser = await playwright_instance.chromium.launch(headless=True,
            args=["--no-sandbox","--disable-blink-features=AutomationControlled","--disable-dev-shm-usage"])
        ctx = await browser.new_context(viewport={"width":1280,"height":900},
            user_agent=get_random_user_agent())
        page = await ctx.new_page()
        if platform == "facebook":
            await page.goto("https://www.facebook.com",timeout=30000)
            await human_delay(2000,4000)
            try: await page.click('[data-cookiebanner="accept_button"]',timeout=4000)
            except: pass
            await human_delay(500,1000)
            await human_type(page,'#email',email)
            await human_type(page,'#pass',password)
            await human_delay(500,1200)
            await human_click(page,'[name="login"]')
            await human_delay(5000,8000)
            ok = "facebook.com" in page.url and "login" not in page.url
        elif platform == "kijiji":
            await page.goto("https://www.kijiji.ca/t-login.html",timeout=30000)
            await human_delay(2000,3500)
            await human_type(page,'#LoginEmailOrNickname',email)
            await human_type(page,'#login-password',password)
            await human_delay(800,1500)
            await human_click(page,'[data-testid="login-submit-button"]')
            await human_delay(4000,6000)
            ok = "kijiji.ca" in page.url and "login" not in page.url
        else:
            ok = False
        if ok:
            os.makedirs("sessions",exist_ok=True)
            await ctx.storage_state(path=f"sessions/{platform}_session.json")
            db.log_agent_event("session",f"{platform} auto re-login successful ✓")
        else:
            db.log_agent_event("session",f"{platform} auto re-login failed",level="error")
        await browser.close()
        return ok
    except Exception as e:
        db.log_agent_event("session",f"{platform} re-login error: {e}",level="error")
        return False

async def get_browser_context(platform, playwright_instance):
    session_path = _load_session(platform)
    browser = await playwright_instance.chromium.launch(headless=True,
        args=["--no-sandbox","--disable-blink-features=AutomationControlled","--disable-dev-shm-usage"])
    kwargs = {"viewport":{"width":1280,"height":900},"user_agent":get_random_user_agent()}
    if session_path and os.path.exists(session_path):
        kwargs["storage_state"] = session_path
    else:
        db.log_agent_event("session",f"No session for {platform} — run session_setup.py first",level="warn")
    return browser, await browser.new_context(**kwargs)

def generate_first_message(listing):
    missing = []
    if not listing.get('karat'):        missing.append("exact karat (10K, 14K, 18K etc.)")
    if not listing.get('weight_grams'): missing.append("weight in grams")
    if not listing.get('hallmark_seen'):missing.append("whether there's a hallmark or stamp")
    if not missing:                     missing.append("condition and why you're selling")
    prompt = f"""Write a short casual message to a gold jewelry seller on a local marketplace.
You are a genuine local buyer browsing listings. Sound human and curious.
LISTING: "{listing.get('title','?')}" at ${listing.get('price_cad','?')}
ASK ONLY ABOUT: {missing[0]}
Rules:
- Maximum 2 sentences. One question only.
- Casual tone. Vary the greeting every time.
- Do NOT mention price, offers, or negotiation.
- Do NOT say "I am interested in purchasing".
- Sound like a real person texting, not a form letter.
Return only the message text. No quotes. No explanation."""
    try:
        return _client.models.generate_content(model=_MODEL, contents=prompt).text.strip()
    except Exception as e:
        db.log_agent_event("message",f"Message generation error: {e}",level="error")
        return "Hey, still available? Do you know the karat on this piece?"

async def send_message_facebook(listing_url, message_text, playwright_ctx, playwright_instance=None):
    """Send FB message with safety checks, human behavior, ban detection, retry on session expiry."""
    # Safety check first
    safe, reason = safety.check_message_safety("facebook")
    if not safe:
        db.log_agent_event("message",f"FB message blocked by safety: {reason}",level="warn")
        return False, ""

    # First-run warning
    safety.warn_facebook_first_run()

    from browser_use import Agent
    from langchain_google_genai import ChatGoogleGenerativeAI
    bu_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash",google_api_key=os.getenv("GEMINI_API_KEY"))

    # Human pre-delay (reading time on the listing)
    await reading_delay(len(listing_url))
    await human_delay(8000,22000)

    agent = Agent(
        task=f"""Navigate to this Facebook Marketplace listing: {listing_url}
I am already logged in to Facebook. DO NOT try to log in.
1. Wait for page to fully load (5 seconds).
2. Scroll down slightly to read the listing (looks natural).
3. Find the "Message" button and click it.
4. Wait for message input box to appear.
5. Type this EXACT message character by character (do not paste):
---
{message_text}
---
6. Pause 2-3 seconds after typing.
7. Click the Send button.
8. Wait 2 seconds to confirm message appears in the chat thread.
9. Return "sent:URL" where URL is the current conversation URL.
   If URL didn't change, return "sent:unknown".
   If anything fails, return "failed:SPECIFIC_REASON".""",
        llm=bu_llm, browser_context=playwright_ctx, max_actions_per_step=8)

    try:
        result = await agent.run(max_steps=30)
        text = (result.final_result() or "").strip()

        # Check result for ban signals
        if safety.check_browser_response_for_bans(text,"facebook"):
            return False, ""

        if text.startswith("sent:"):
            url = text[5:].strip()
            db.log_agent_event("message",f"FB message sent successfully to {listing_url[:60]}")
            return True, url if url.startswith("http") else ""

        # Session may have expired
        if "login" in text.lower() or "not logged" in text.lower():
            db.log_agent_event("session","FB session appears expired — attempting auto re-login",level="warn")
            if playwright_instance:
                relogged = await _auto_relogin("facebook", playwright_instance)
                if relogged:
                    db.log_agent_event("session","Re-login successful — skipping this message (will retry next cycle)")
            return False, ""

        db.log_agent_event("message",f"FB message failed: {text}",level="warn")
        return False, ""
    except Exception as e:
        db.log_agent_event("message",f"FB message exception: {e}",level="error")
        return False, ""

async def send_message_kijiji(listing_url, message_text, playwright_ctx, playwright_instance=None):
    """Send Kijiji message with safety checks and human behavior."""
    safe, reason = safety.check_message_safety("kijiji")
    if not safe:
        db.log_agent_event("message",f"Kijiji message blocked by safety: {reason}",level="warn")
        return False, ""

    from browser_use import Agent
    from langchain_google_genai import ChatGoogleGenerativeAI
    bu_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash",google_api_key=os.getenv("GEMINI_API_KEY"))

    await human_delay(5000,15000)

    agent = Agent(
        task=f"""Navigate to this Kijiji listing: {listing_url}
I am logged in to Kijiji. DO NOT log in again.
1. Wait for page to load.
2. Scroll down to read the listing first.
3. Find the Reply / Email Seller / Contact button.
4. Click it. Wait for message form to appear.
5. In the message text box, type:
---
{message_text}
---
6. Click Send or Submit.
7. Return "sent" if successful. Return "failed:REASON" if anything failed.""",
        llm=bu_llm, browser_context=playwright_ctx, max_actions_per_step=8)

    try:
        result = await agent.run(max_steps=20)
        text = (result.final_result() or "").strip()

        if safety.check_browser_response_for_bans(text,"kijiji"):
            return False, ""

        if "login" in text.lower() and playwright_instance:
            await _auto_relogin("kijiji", playwright_instance)
            return False, ""

        ok = text.lower().startswith("sent")
        if ok:
            db.log_agent_event("message",f"Kijiji message sent to {listing_url[:60]}")
        else:
            db.log_agent_event("message",f"Kijiji send failed: {text}",level="warn")
        return ok, ""
    except Exception as e:
        db.log_agent_event("message",f"Kijiji message exception: {e}",level="error")
        return False, ""
