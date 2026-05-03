"""
human_browser.py — Human-like browser interactions. Random delays, mouse movements,
realistic typing. Makes automated actions look like a real person.
"""
import asyncio, random, math

async def human_delay(min_ms=800, max_ms=2500):
    """Random delay mimicking human reaction time."""
    await asyncio.sleep(random.uniform(min_ms/1000, max_ms/1000))

async def reading_delay(text_length):
    """Delay proportional to text length — like actually reading it."""
    words = text_length / 5
    reading_time = words / 200 * 60  # 200 wpm reading speed
    jitter = random.uniform(0.7, 1.4)
    await asyncio.sleep(max(1.0, reading_time * jitter))

async def human_type(page, selector, text):
    """
    Type text character by character with realistic timing.
    Includes occasional micro-pauses like a real typist.
    """
    await page.click(selector)
    await human_delay(300, 800)
    for i, char in enumerate(text):
        await page.type(selector, char, delay=random.uniform(40, 140))
        # Occasional longer pause (like thinking mid-sentence)
        if char in '.!?,':
            await asyncio.sleep(random.uniform(0.2, 0.6))
        elif random.random() < 0.03:  # 3% chance of brief pause
            await asyncio.sleep(random.uniform(0.3, 1.0))
    await human_delay(400, 900)

async def move_mouse_naturally(page, target_x, target_y):
    """Move mouse in a curved path to target, not a straight line."""
    try:
        start_x = random.randint(100, 800)
        start_y = random.randint(100, 600)
        steps = random.randint(12, 25)
        for i in range(steps + 1):
            t = i / steps
            # Bezier curve with random control point
            cx = (start_x + target_x) / 2 + random.randint(-80, 80)
            cy = (start_y + target_y) / 2 + random.randint(-60, 60)
            x = int((1-t)**2 * start_x + 2*(1-t)*t * cx + t**2 * target_x)
            y = int((1-t)**2 * start_y + 2*(1-t)*t * cy + t**2 * target_y)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.01, 0.04))
    except: pass

async def human_click(page, selector):
    """Find element, move mouse there naturally, then click."""
    try:
        el = await page.query_selector(selector)
        if not el: return False
        box = await el.bounding_box()
        if not box: return False
        # Click slightly off-center (humans rarely click dead center)
        x = box['x'] + box['width'] * random.uniform(0.3, 0.7)
        y = box['y'] + box['height'] * random.uniform(0.3, 0.7)
        await move_mouse_naturally(page, int(x), int(y))
        await human_delay(100, 400)
        await page.mouse.click(x, y)
        await human_delay(300, 700)
        return True
    except:
        # Fallback to normal click
        try:
            await page.click(selector)
            return True
        except:
            return False

async def human_scroll(page, direction="down", times=1):
    """Scroll naturally with variable speed."""
    for _ in range(times):
        scroll_amount = random.randint(300, 700) * (1 if direction == "down" else -1)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await human_delay(600, 1400)

async def random_page_browse(page):
    """
    Brief 'browsing' behavior — move mouse around, maybe scroll.
    Makes the session look more like a real user.
    """
    actions = random.randint(2, 4)
    for _ in range(actions):
        action = random.choice(["move", "scroll", "pause"])
        if action == "move":
            await move_mouse_naturally(page, random.randint(200, 900), random.randint(200, 600))
        elif action == "scroll":
            await human_scroll(page, "down", 1)
        else:
            await human_delay(500, 1500)

async def pre_action_warmup(page):
    """Before any important action, do some natural browsing first."""
    await random_page_browse(page)
    await human_delay(1000, 3000)

ROTATE_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.122 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

def get_random_user_agent():
    return random.choice(ROTATE_USER_AGENTS)
