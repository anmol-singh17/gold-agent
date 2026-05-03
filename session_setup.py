"""
session_setup.py — Auto-login to Facebook and Kijiji using credentials from .env
Run once before deploying: python session_setup.py both
"""
import asyncio, os, sys, base64
from dotenv import load_dotenv
load_dotenv()

async def auto_login_facebook():
    from playwright.async_api import async_playwright
    email    = os.getenv("FB_EMAIL","")
    password = os.getenv("FB_PASSWORD","")
    if not email or not password:
        print("❌ FB_EMAIL or FB_PASSWORD not set in .env")
        return False

    print("\n[FB] Starting auto-login...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=80)
        ctx = await browser.new_context(
            viewport={"width":1280,"height":900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        try:
            await page.goto("https://www.facebook.com", timeout=30000)
            await asyncio.sleep(2)

            # Accept cookies if prompted
            try:
                await page.click('[data-cookiebanner="accept_button"]', timeout=5000)
                await asyncio.sleep(1)
            except: pass

            # Fill login form
            await page.fill('#email', email)
            await asyncio.sleep(0.5)
            await page.fill('#pass', password)
            await asyncio.sleep(0.5)
            await page.click('[name="login"]')
            await asyncio.sleep(5)

            # Check for 2FA
            if "two_step" in page.url or "checkpoint" in page.url:
                print("\n⚠️  Facebook requires 2FA/verification.")
                print("   Complete it in the browser window, then press ENTER here.")
                input("Press ENTER after completing verification...")
                await asyncio.sleep(3)

            # Check login success
            if "facebook.com" in page.url and "login" not in page.url:
                print("[FB] ✅ Login successful!")
                await asyncio.sleep(3)  # Let page settle
                os.makedirs("sessions", exist_ok=True)
                await ctx.storage_state(path="sessions/facebook_session.json")
                _save_b64("sessions/facebook_session.json", "sessions/facebook_session_b64.txt")
                print("[FB] Session saved.")
                await browser.close()
                return True
            else:
                print(f"[FB] ❌ Login may have failed. Current URL: {page.url}")
                print("   Check credentials in .env")
                await browser.close()
                return False
        except Exception as e:
            print(f"[FB] Error: {e}")
            await browser.close()
            return False

async def auto_login_kijiji():
    from playwright.async_api import async_playwright
    email    = os.getenv("KIJIJI_EMAIL","")
    password = os.getenv("KIJIJI_PASSWORD","")
    if not email or not password:
        print("❌ KIJIJI_EMAIL or KIJIJI_PASSWORD not set in .env")
        return False

    print("\n[KIJIJI] Starting auto-login...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=80)
        ctx = await browser.new_context(
            viewport={"width":1280,"height":900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        try:
            await page.goto("https://www.kijiji.ca/t-login.html", timeout=30000)
            await asyncio.sleep(2)
            await page.fill('#LoginEmailOrNickname', email)
            await asyncio.sleep(0.5)
            await page.fill('#login-password', password)
            await asyncio.sleep(0.5)
            await page.click('[data-testid="login-submit-button"]')
            await asyncio.sleep(4)

            if "kijiji.ca" in page.url and "login" not in page.url:
                print("[KIJIJI] ✅ Login successful!")
                os.makedirs("sessions", exist_ok=True)
                await ctx.storage_state(path="sessions/kijiji_session.json")
                _save_b64("sessions/kijiji_session.json", "sessions/kijiji_session_b64.txt")
                print("[KIJIJI] Session saved.")
                await browser.close()
                return True
            else:
                print(f"[KIJIJI] ❌ Login may have failed. URL: {page.url}")
                await browser.close()
                return False
        except Exception as e:
            print(f"[KIJIJI] Error: {e}")
            await browser.close()
            return False

def _save_b64(json_path, txt_path):
    with open(json_path) as f:
        content = f.read()
    encoded = base64.b64encode(content.encode()).decode()
    with open(txt_path, 'w') as f:
        f.write(encoded)
    print(f"   Base64 saved to {txt_path} — copy this value into Railway as env var")

async def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "both"
    results = {}
    if target in ("facebook","fb","both"):
        results["Facebook"] = await auto_login_facebook()
    if target in ("kijiji","kj","both"):
        results["Kijiji"] = await auto_login_kijiji()

    print("\n" + "="*50)
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    print("="*50)
    if all(results.values()):
        print("\n✅ All sessions captured! Now run: python agent/main.py")
    else:
        print("\n⚠️  Some logins failed. Check credentials in .env and retry.")

if __name__ == "__main__":
    asyncio.run(main())
