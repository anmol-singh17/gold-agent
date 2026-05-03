"""
poller.py — Read inbox every 45 min, parse seller replies, generate follow-ups
"""
import os
import json
import asyncio
import random
from google import genai
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_MODEL = "gemini-2.5-flash"


# ── READ CONVERSATIONS ────────────────────────────────────────────────────────

async def read_fb_conversation(conversation_url, playwright_ctx):
    """Read full message thread from a FB Marketplace conversation."""
    from browser_use import Agent
    from langchain_google_genai import ChatGoogleGenerativeAI

    bu_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY")
    )

    agent = Agent(
        task=f"""
Navigate to: {conversation_url}

I am logged in to Facebook. DO NOT try to log in.

Wait for the messages to load fully (up to 5 seconds).

Extract ALL messages in this conversation, in chronological order (oldest first).

For each message identify:
- who sent it: "me" (my messages, shown on the RIGHT side) or "seller" (their messages, on the LEFT)
- the exact text of the message
- timestamp if visible (approximate is fine)

Return ONLY a JSON array — no other text:
[{{"role": "me", "text": "...", "ts": "..."}}, {{"role": "seller", "text": "...", "ts": "..."}}]

If no messages found or page fails to load, return: []
""",
        llm=bu_llm,
        browser_context=playwright_ctx,
    )

    try:
        result = await agent.run(max_steps=12)
        raw = (result.final_result() or "[]").strip().replace('```json', '').replace('```', '')
        messages = json.loads(raw)
        print(f"[POLLER] FB conversation: {len(messages)} messages found")
        return messages
    except Exception as e:
        print(f"[POLLER] FB conversation read error: {e}")
        return []


async def read_kijiji_inbox(playwright_ctx):
    """Check Kijiji inbox for new/unread replies."""
    from browser_use import Agent
    from langchain_google_genai import ChatGoogleGenerativeAI

    bu_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY")
    )

    agent = Agent(
        task="""
Navigate to: https://www.kijiji.ca/m-mes-messages.html

I am logged in to Kijiji.

Find all conversations that have a new/unread reply (they may appear bold, highlighted, or marked as "new").

For each unread conversation collect:
- listing_title: the title of the item being discussed
- conversation_url: the direct URL to this conversation thread
- reply_text: the seller's latest message text

Return ONLY a JSON array:
[{"listing_title": "...", "conversation_url": "...", "reply_text": "..."}]

If no new messages, return: []
""",
        llm=bu_llm,
        browser_context=playwright_ctx,
    )

    try:
        result = await agent.run(max_steps=15)
        raw = (result.final_result() or "[]").strip().replace('```json', '').replace('```', '')
        replies = json.loads(raw)
        print(f"[POLLER] Kijiji inbox: {len(replies)} unread conversations")
        return replies
    except Exception as e:
        print(f"[POLLER] Kijiji inbox error: {e}")
        return []


async def read_kijiji_conversation(conversation_url, playwright_ctx):
    """Read full thread from a specific Kijiji conversation URL."""
    from browser_use import Agent
    from langchain_google_genai import ChatGoogleGenerativeAI

    bu_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY")
    )

    agent = Agent(
        task=f"""
Navigate to: {conversation_url}

I am logged in to Kijiji.

Extract all messages in this conversation in order (oldest first).
For each: who sent it ("me" or "seller"), the text, and timestamp if shown.

Return ONLY a JSON array:
[{{"role": "me", "text": "...", "ts": "..."}}, {{"role": "seller", "text": "...", "ts": "..."}}]

If page fails, return: []
""",
        llm=bu_llm,
        browser_context=playwright_ctx,
    )

    try:
        result = await agent.run(max_steps=12)
        raw = (result.final_result() or "[]").strip().replace('```json', '').replace('```', '')
        messages = json.loads(raw)
        return messages
    except Exception as e:
        print(f"[POLLER] Kijiji conversation read error: {e}")
        return []


# ── PARSE REPLY ───────────────────────────────────────────────────────────────

def parse_seller_reply(conversation_history, listing):
    """
    Extract confirmed data from seller's replies using Gemini.
    Returns a dict with confirmed facts, red flags, still_missing, etc.
    """
    prompt = f"""
You are analyzing a conversation with a gold/jewelry seller on a marketplace.
A buyer (me) asked questions. Extract confirmed information from the seller's replies only.

FULL CONVERSATION:
{json.dumps(conversation_history, indent=2)}

WHAT WE ALREADY KNOW (may be null if unknown):
- Karat: {listing.get('karat')}
- Weight: {listing.get('weight_grams')}g
- Hallmark seen: {listing.get('hallmark_seen')}
- Price: ${listing.get('price_cad')}

Return ONLY valid JSON — no markdown, no explanation:
{{
    "seller_replied": true or false,
    "confirmed_grams": null or float (only if seller explicitly stated the weight),
    "confirmed_karat": null or int (only if seller confirmed the karat — 10/14/18/22/24),
    "hallmark_confirmed": null or bool (seller said there IS a stamp/hallmark),
    "condition": null or string (excellent/good/fair/poor — if seller mentioned),
    "reason_selling": null or string (why they're selling, if mentioned),
    "price_negotiable": null or bool,
    "seller_reliability": 1 to 5 (1=suspicious/vague, 5=very credible/detailed),
    "red_flags": [] (list any concerns: vague answers, no stamp, contradictions, rude),
    "still_missing": [] (list what critical info is still unknown: "weight", "karat", "hallmark"),
    "reply_quality": "detailed" or "vague" or "no_reply"
}}
"""
    try:
        resp = _client.models.generate_content(model=_MODEL, contents=prompt)
        text = resp.text.strip().replace('```json', '').replace('```', '').strip()
        result = json.loads(text)
        print(f"[POLLER] Parsed reply — seller replied: {result.get('seller_replied')}, "
              f"still missing: {result.get('still_missing')}")
        return result
    except Exception as e:
        print(f"[POLLER] Reply parse error: {e}")
        return {
            "seller_replied": False,
            "still_missing": ["all"],
            "red_flags": [],
            "seller_reliability": 3,
            "reply_quality": "no_reply"
        }


# ── FOLLOW-UP GENERATION ──────────────────────────────────────────────────────

def generate_followup(conversation_history, parsed, follow_up_count):
    """
    Generate a natural follow-up question. Returns None if we should stop.
    Max 2 follow-ups ever — after that, stop messaging.
    """
    if follow_up_count >= 2:
        print("[POLLER] Max follow-ups reached. Stopping.")
        return None

    missing = parsed.get("still_missing", [])
    if not missing:
        print("[POLLER] Nothing missing — no follow-up needed.")
        return None

    next_ask = missing[0]

    # Get the last thing the seller said for context
    seller_msgs = [m["text"] for m in conversation_history if m.get("role") == "seller"]
    last_reply = seller_msgs[-1] if seller_msgs else ""

    prompt = f"""
Continue a natural conversation with a jewelry seller on a local marketplace.

They just replied: "{last_reply}"

You still need to find out: {next_ask}

Write ONE short, friendly follow-up message that:
- References what they just said naturally (show you read their reply)
- Asks about ONLY: {next_ask}
- Is 1-2 sentences maximum
- Sounds like a genuine curious buyer, not a script
- Does NOT ask about price or make any offers
- Is casual and warm in tone
- Varies phrasing from the first message

Return only the message text. No quotes. No preamble. No explanation.
"""
    try:
        resp = _client.models.generate_content(model=_MODEL, contents=prompt)
        msg = resp.text.strip()
        print(f"[POLLER] Follow-up #{follow_up_count + 1}: {msg[:80]}...")
        return msg
    except Exception as e:
        print(f"[POLLER] Follow-up generation error: {e}")
        return None
