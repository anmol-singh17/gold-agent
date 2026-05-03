"""
main.py — Entry point. APScheduler with full error recovery.
Run: python agent/main.py
Test: python agent/main.py --test
"""
import asyncio, os, sys, argparse
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from playwright.async_api import async_playwright
import db, scraper, scorer, messenger, poller, handover, safety
from handover import send_alert_telegram, send_daily_summary_telegram, check_telegram_replies

scheduler = BackgroundScheduler()

async def _do_scrape():
    run_id = db.start_job_run("scrape")
    try:
        kj_new = scraper.run_kijiji_scrape()
        cl_new = scraper.run_craigslist_scrape()
        eb_new = scraper.run_ebay_scrape()
        fb_new = 0
        fb_session = "sessions/facebook_session.json"
        if os.path.exists(fb_session) or os.getenv("FACEBOOK_SESSION_B64"):
            try:
                async with async_playwright() as p:
                    browser, ctx = await messenger.get_browser_context("facebook",p)
                    fb_new = await scraper.run_all_fb_scrapes(ctx)
                    await ctx.close(); await browser.close()
            except Exception as e:
                db.log_agent_event("scrape",f"FB scrape failed (non-fatal): {e}",level="error")
                send_alert_telegram(f"⚠️ FB scrape error: {e}")
        else:
            db.log_agent_event("scrape","FB skipped — no session. Run session_setup.py facebook")
        total = kj_new+cl_new+eb_new+fb_new
        db.log_agent_event("scrape",f"Done: {total} total new (KJ:{kj_new} CL:{cl_new} EB:{eb_new} FB:{fb_new})")
        db.finish_job_run(run_id,"done",f"new:{total}")
    except Exception as e:
        db.log_agent_event("scrape",f"Job crashed: {e}",level="error")
        db.finish_job_run(run_id,"error","",str(e))
        send_alert_telegram(f"❌ Scrape job crashed: {e}")

def _do_score():
    run_id = db.start_job_run("score")
    try:
        listings = db.get_listings_by_status("new",limit=30)
        if not listings:
            db.log_agent_event("score","No new listings to score")
            db.finish_job_run(run_id,"done","nothing to score")
            return
        ok = err = 0
        for l in listings:
            try:
                score, merged, reasons = scorer.run_scorer_for_listing(l)
                db.update_listing_score(l["id"],score,merged,reasons)
                if score>=70:   st="queued_msg"
                elif score<20:  st="rejected"
                else:           st="scored"
                db.update_listing_status(l["id"],st)
                db.log_agent_event("score",f"'{l['title'][:45]}' → {score}/100 → {st}")
                ok += 1
            except Exception as e:
                db.log_agent_event("score",f"Error scoring {l['id']}: {e}",level="error")
                err += 1
        db.finish_job_run(run_id,"done",f"ok:{ok} err:{err}")
    except Exception as e:
        db.log_agent_event("score",f"Job crashed: {e}",level="error")
        db.finish_job_run(run_id,"error","",str(e))
        send_alert_telegram(f"❌ Score job crashed: {e}")

async def _do_message():
    run_id = db.start_job_run("message")
    sent = failed = 0
    try:
        if db.messages_sent_today() >= safety.DAILY_MESSAGE_CAP:
            db.log_agent_event("message","Daily cap reached. No messages today.")
            db.finish_job_run(run_id,"done","cap reached")
            return
        queued = db.get_listings_by_status("queued_msg",limit=4)
        if not queued:
            db.log_agent_event("message","Nothing queued")
            db.finish_job_run(run_id,"done","nothing queued")
            return

        async with async_playwright() as p:
            fb_browser, fb_ctx = await messenger.get_browser_context("facebook",p)
            kj_browser, kj_ctx = await messenger.get_browser_context("kijiji",p)

            for listing in queued:
                if db.messages_sent_today() >= safety.DAILY_MESSAGE_CAP: break
                platform = listing.get("platform","")
                msg_text = messenger.generate_first_message(listing)
                try:
                    if platform=="facebook":
                        ok,conv_url = await messenger.send_message_facebook(listing["url"],msg_text,fb_ctx,p)
                    elif platform=="kijiji":
                        ok,conv_url = await messenger.send_message_kijiji(listing["url"],msg_text,kj_ctx,p)
                    elif platform in ("ebay","craigslist"):
                        db.log_agent_event("message",f"Skipping {platform} — email messaging not automated (manual only)")
                        db.update_listing_status(listing["id"],"scored")
                        continue
                    else:
                        continue

                    if ok:
                        db.save_conversation(listing["id"],platform,conv_url,[{"role":"me","text":msg_text,"ts":"now"}])
                        db.update_listing_status(listing["id"],"awaiting_reply")
                        db.log_message_sent(listing["id"],platform)
                        sent += 1
                    else:
                        failed += 1
                        db.log_agent_event("message",f"Failed to send to '{listing['title'][:40]}'",level="warn")

                    await safety.inter_message_delay(platform)
                except Exception as e:
                    db.log_agent_event("message",f"Error for listing {listing['id']}: {e}",level="error")
                    failed += 1

            await fb_ctx.close(); await fb_browser.close()
            await kj_ctx.close(); await kj_browser.close()

        db.finish_job_run(run_id,"done",f"sent:{sent} failed:{failed}")
    except Exception as e:
        db.log_agent_event("message",f"Job crashed: {e}",level="error")
        db.finish_job_run(run_id,"error","",str(e))
        send_alert_telegram(f"❌ Message job crashed: {e}")

async def _do_poll():
    run_id = db.start_job_run("poll")
    try:
        check_telegram_replies()
        for g in db.get_ghosted_listings():
            db.mark_ghosted(g["id"])
            db.log_agent_event("poll",f"Auto-ghosted: '{g['title'][:40]}'")

        active = db.get_listings_by_status(["awaiting_reply","replied"],limit=20)
        if not active:
            db.log_agent_event("poll","No active conversations")
            db.finish_job_run(run_id,"done","no active convos")
            return

        async with async_playwright() as p:
            fb_browser, fb_ctx = await messenger.get_browser_context("facebook",p)
            kj_browser, kj_ctx = await messenger.get_browser_context("kijiji",p)

            for listing in active:
                try:
                    conv = db.get_conversation(listing["id"])
                    if not conv or not conv.get("conversation_url"): continue
                    platform = listing.get("platform","")
                    if platform=="facebook":
                        messages = await poller.read_fb_conversation(conv["conversation_url"],fb_ctx)
                    elif platform=="kijiji":
                        messages = await poller.read_kijiji_conversation(conv["conversation_url"],kj_ctx)
                    else: continue

                    if not messages:
                        db.log_agent_event("poll",f"No messages readable for listing {listing['id']}",level="warn")
                        continue
                    db.update_conversation_messages(conv["id"],messages)
                    parsed = poller.parse_seller_reply(messages,listing)

                    should_ho,final_score = handover.check_handover(listing,parsed)
                    if should_ho:
                        grams  = parsed.get("confirmed_grams") or listing.get("weight_grams")
                        karat  = parsed.get("confirmed_karat") or listing.get("karat")
                        profit = handover.calc_profit(grams,karat,listing.get("price_cad",0))
                        if not listing.get("notified"):
                            handover.send_handover_telegram(listing,conv,parsed,profit,final_score)
                            db.mark_notified(listing["id"])
                        db.update_listing_status(listing["id"],"handover")
                        db.update_conversation_parsed(conv["id"],parsed,profit)
                        db.log_agent_event("poll",f"🏆 HANDOVER: '{listing['title'][:40]}' score {final_score}")
                        continue

                    follow_up_count = listing.get("follow_up_count",0)
                    if parsed.get("seller_replied") and follow_up_count < 2:
                        followup = poller.generate_followup(messages,parsed,follow_up_count)
                        if followup:
                            if platform=="facebook":
                                ok,_ = await messenger.send_message_facebook(conv["conversation_url"],followup,fb_ctx,p)
                            else:
                                ok,_ = await messenger.send_message_kijiji(conv["conversation_url"],followup,kj_ctx,p)
                            if ok:
                                db.increment_followup_count(listing["id"])
                                db.update_listing_status(listing["id"],"replied")
                                db.log_agent_event("poll",f"Follow-up #{follow_up_count+1} sent to '{listing['title'][:35]}'")

                    await asyncio.sleep(random.uniform(30,90))
                except Exception as e:
                    db.log_agent_event("poll",f"Error for listing {listing['id']}: {e}",level="error")

            await fb_ctx.close(); await fb_browser.close()
            await kj_ctx.close(); await kj_browser.close()

        db.finish_job_run(run_id,"done",f"checked:{len(active)}")
    except Exception as e:
        db.log_agent_event("poll",f"Job crashed: {e}",level="error")
        db.finish_job_run(run_id,"error","",str(e))
        send_alert_telegram(f"❌ Poll job crashed: {e}")

@scheduler.scheduled_job(IntervalTrigger(minutes=20),id="scrape")
async def job_scrape():
    print("\n[JOB] ═══ SCRAPE ═══"); await _do_scrape()

@scheduler.scheduled_job(IntervalTrigger(minutes=25),id="score")
def job_score():
    print("\n[JOB] ═══ SCORE ═══"); _do_score()

@scheduler.scheduled_job(IntervalTrigger(minutes=30),id="message")
async def job_message():
    print("\n[JOB] ═══ MESSAGE ═══"); await _do_message()

@scheduler.scheduled_job(IntervalTrigger(minutes=45),id="poll")
async def job_poll():
    print("\n[JOB] ═══ POLL ═══"); await _do_poll()

@scheduler.scheduled_job('cron',hour=20,minute=0,id="daily_summary")
def job_daily_summary():
    stats = {"found":db.get_count("today"),"high_score":db.get_count("score_gte_70"),
             "messages_sent":db.messages_sent_today(),"awaiting_reply":db.get_count("awaiting_reply"),
             "handovers":db.get_count("handover"),"ghosted":db.get_count("ghosted")}
    send_daily_summary_telegram(stats)
    db.log_agent_event("daily",f"Summary sent: {stats}")

async def run_test_mode():
    print("\n"+"="*60+"\n  TEST MODE — One Full Cycle\n"+"="*60)
    print("\n[1/4] SCRAPE"); await _do_scrape()
    print("\n[2/4] SCORE"); _do_score()
    print("\n[3/4] MESSAGE (max 2)"); await _do_message()
    print("\n[4/4] POLL"); await _do_poll()
    print("\n"+"="*60+"\n  DONE — open dashboard: streamlit run dashboard/app.py\n"+"="*60)

import random
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",action="store_true",help="Run one full cycle then exit")
    args = parser.parse_args()
    print("="*60+"\n  🥇 Gold Deal Hunter — Final Version\n"+"="*60)
    db.init_db()
    if args.test:
        asyncio.run(run_test_mode()); sys.exit(0)
    scheduler.start()
    db.log_agent_event("main","Agent started — all jobs scheduled")
    send_alert_telegram("🟢 Gold Agent started! All systems go.")
    print("[MAIN] Running. Ctrl+C to stop.")
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt,SystemExit):
        scheduler.shutdown()
        db.log_agent_event("main","Agent stopped by user")
        print("[MAIN] Stopped.")
