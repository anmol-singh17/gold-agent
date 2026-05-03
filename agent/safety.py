"""
safety.py — All ban prevention, rate limiting, cooldown management, and user warnings.
Nothing happens without going through here first.
"""
import os, random, asyncio
import db
from handover import send_alert_telegram

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
DAILY_MESSAGE_CAP    = 10
WARNING_THRESHOLD    = 7   # warn user at 7/10
COOLDOWN_MINUTES     = 120 # 2 hour cooldown if rate limit detected
MIN_DELAY_BETWEEN_MESSAGES = 90   # seconds
MAX_DELAY_BETWEEN_MESSAGES = 200  # seconds

BAN_RISK_SIGNALS = [
    "rate limit", "too many requests", "temporarily blocked",
    "account restricted", "unusual activity", "security check",
    "confirm your identity", "checkpoint", "suspicious activity",
    "please try again later", "action blocked"
]

# ── PRE-ACTION CHECKS ─────────────────────────────────────────────────────────
def check_message_safety(platform) -> tuple[bool, str]:
    """
    Before sending ANY message, run all safety checks.
    Returns (safe_to_proceed, reason_if_not).
    """
    # 1. Check cooldown
    cooldown = db.is_in_cooldown(platform)
    if cooldown:
        until, reason = cooldown
        msg = f"Platform {platform} in cooldown until {until.strftime('%H:%M')}. Reason: {reason}"
        db.log_safety_event(platform, "cooldown_block", msg, "skipped")
        return False, msg

    # 2. Check daily cap
    sent = db.messages_sent_today()
    if sent >= DAILY_MESSAGE_CAP:
        msg = f"Daily cap reached ({sent}/{DAILY_MESSAGE_CAP}). No more messages today."
        db.log_safety_event(platform, "daily_cap", msg, "skipped")
        return False, msg

    # 3. Warn at threshold
    if sent >= WARNING_THRESHOLD:
        msg = f"⚠️ HIGH MESSAGE COUNT: {sent}/{DAILY_MESSAGE_CAP} today on {platform}. Approaching daily limit."
        db.log_safety_event(platform, "high_count_warning", msg, "warned")
        send_alert_telegram(f"⚠️ Message count at {sent}/{DAILY_MESSAGE_CAP} today. Agent continuing but be aware.")
        db.log_agent_event("safety", msg, level="warn")

    return True, "ok"

def check_browser_response_for_bans(response_text: str, platform: str) -> bool:
    """
    Scan any browser response for signs of rate limiting or banning.
    Returns True if ban signal detected (should stop immediately).
    """
    if not response_text:
        return False
    lower = response_text.lower()
    for signal in BAN_RISK_SIGNALS:
        if signal in lower:
            msg = f"Ban/rate-limit signal detected on {platform}: '{signal}'"
            db.log_safety_event(platform, "ban_signal_detected", msg, f"cooldown_{COOLDOWN_MINUTES}min")
            db.set_cooldown(platform, COOLDOWN_MINUTES, f"Rate limit signal: {signal}")
            db.log_agent_event("safety", msg, level="error")
            send_alert_telegram(
                f"🚨 SAFETY ALERT\n\n"
                f"Rate-limit/ban signal detected on {platform.upper()}!\n"
                f"Signal: '{signal}'\n\n"
                f"Agent has paused {platform} messaging for {COOLDOWN_MINUTES} minutes automatically.\n"
                f"If this keeps happening, reduce activity on this platform."
            )
            return True
    return False

async def inter_message_delay(platform: str):
    """
    Wait a human-like random amount between messages.
    Longer delays = safer. Never skip this.
    """
    delay = random.uniform(MIN_DELAY_BETWEEN_MESSAGES, MAX_DELAY_BETWEEN_MESSAGES)
    db.log_agent_event("safety", f"Waiting {delay:.0f}s before next {platform} message (rate limit protection)")
    await asyncio.sleep(delay)

def get_ban_risk_level() -> tuple[str, str]:
    """
    Returns (level, description) based on today's activity.
    level: 'low' | 'medium' | 'high' | 'critical'
    """
    sent = db.messages_sent_today()
    cooldowns = db.get_all_cooldowns()

    if cooldowns:
        return "critical", f"Active cooldown on {len(cooldowns)} platform(s)"
    if sent >= DAILY_MESSAGE_CAP:
        return "high", f"Daily cap reached ({sent}/{DAILY_MESSAGE_CAP})"
    if sent >= WARNING_THRESHOLD:
        return "medium", f"{sent}/{DAILY_MESSAGE_CAP} messages sent today"
    return "low", f"{sent}/{DAILY_MESSAGE_CAP} messages sent today — well within limits"

# ── FB-SPECIFIC SAFETY ────────────────────────────────────────────────────────
FACEBOOK_ACCOUNT_WARNING = """
⚠️ FACEBOOK ACCOUNT SAFETY REMINDER

You are using a secondary Facebook account for automated messaging.
This is required — NEVER use your real personal account.

Facebook's bot detection looks for:
- Sending many messages in a short time (we cap at 10/day)
- Messages that look identical (we generate unique messages via AI)
- Unusual login patterns (we use saved sessions)
- No normal account activity (make sure your secondary account occasionally
  likes posts, joins groups, etc. — do this manually once a week)

If your secondary account gets restricted:
1. Stop the agent immediately
2. Do NOT try to appeal with that account
3. Create a new secondary account (wait 2-3 months before using for messaging)
4. Update FB_EMAIL and FB_PASSWORD in your .env
5. Run session_setup.py facebook again
"""

def warn_facebook_first_run():
    """Display FB safety warning the first time FB messaging is used."""
    import os
    flag_file = "sessions/.fb_warned"
    if not os.path.exists(flag_file):
        db.log_safety_event("facebook", "first_run_warning", FACEBOOK_ACCOUNT_WARNING, "displayed")
        send_alert_telegram(
            "⚠️ *Facebook Safety Reminder*\n\n"
            "Agent is starting Facebook messaging.\n\n"
            "Remember:\n"
            "• Using secondary account only ✓\n"
            "• Hard cap: 10 messages/day ✓\n"
            "• Random delays 90-200s between messages ✓\n\n"
            "If account gets restricted, stop agent immediately and create new secondary account."
        )
        os.makedirs("sessions", exist_ok=True)
        open(flag_file, 'w').close()
