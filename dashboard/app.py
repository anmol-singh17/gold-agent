"""
dashboard/app.py — Complete Gold Agent Dashboard. Everything visible. Auto-refreshes every 30s.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..','agent'))
import streamlit as st
import pandas as pd
from datetime import datetime
import db

st.set_page_config(page_title="Gold Agent",page_icon="🥇",layout="wide",initial_sidebar_state="expanded")
# Auto-refresh every 5 seconds for trading terminal feel
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, key="autorefresh")
except ImportError:
    pass

st.markdown("""<style>
/* Trading Terminal Dark Theme */
.stApp {
    background-color: #0e1117;
    color: #c9d1d9;
}
[data-testid="stMetricValue"] {
    color: #ffffff;
}
/* Metric Cards */
[data-testid="stMetric"] {
    background-color: #161b22;
    border: 1px solid #30363d;
    padding: 15px;
    border-radius: 8px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}
.status-pill {display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;margin:2px;border:1px solid rgba(255,255,255,0.2);}
.pill-new {background:#1f2937;color:#60a5fa;}
.pill-scoring {background:#312e81;color:#a78bfa;}
.pill-queued {background:#78350f;color:#fbbf24;}
.pill-waiting {background:#422006;color:#fcd34d;}
.pill-replied {background:#064e3b;color:#34d399;}
.pill-handover {background:#065f46;color:#10b981;border-color:#10b981;}
.pill-ghosted {background:#1f2937;color:#9ca3af;}
.pill-approved {background:#064e3b;color:#10b981;}
.pill-rejected {background:#7f1d1d;color:#f87171;border-color:#f87171;}

/* Deal Cards */
.deal-card {
    border: 2px solid #30363d;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    background-color: #161b22;
    color: #c9d1d9;
}
.deal-card h3 { color: #58a6ff; margin-top: 0; }
.deal-good { border-color: #2ea043; background: linear-gradient(135deg, #161b22, #04260f); }
.deal-bad { border-color: #f85149; background: linear-gradient(135deg, #161b22, #3a0001); }

.safety-low{background:#04260f;border-left:4px solid #2ea043;padding:8px 12px;border-radius:4px;color:#c9d1d9}
.safety-medium{background:#4d3b00;border-left:4px solid #d29922;padding:8px 12px;border-radius:4px;color:#c9d1d9}
.safety-high{background:#3a0001;border-left:4px solid #f85149;padding:8px 12px;border-radius:4px;color:#c9d1d9}
.safety-critical{background:#790000;color:white;border-left:4px solid #f85149;padding:8px 12px;border-radius:4px}
.event-info{border-left:3px solid #58a6ff;padding:4px 8px;margin:2px 0;background:#161b22;border-radius:0 4px 4px 0;font-size:13px;color:#c9d1d9}
.event-error{border-left:3px solid #f85149;padding:4px 8px;margin:2px 0;background:#3a0001;border-radius:0 4px 4px 0;font-size:13px;color:#ff7b72}
.event-warn{border-left:3px solid #d29922;padding:4px 8px;margin:2px 0;background:#4d3b00;border-radius:0 4px 4px 0;font-size:13px;color:#e3b341}
</style>""", unsafe_allow_html=True)

STATUS_CLASS = {'new':'pill-new','scored':'pill-scoring','queued_msg':'pill-queued',
    'msg_sent':'pill-waiting','awaiting_reply':'pill-waiting','replied':'pill-replied',
    'handover':'pill-handover','ghosted':'pill-ghosted','approved':'pill-approved','rejected':'pill-rejected'}
def pill(s): return f'<span class="status-pill {STATUS_CLASS.get(s,"pill-new")}">{s.replace("_"," ").upper()}</span>'
def sc(s): return "🟢" if s>=80 else "🟡" if s>=60 else "🟠" if s>=40 else "🔴"

with st.sidebar:
    st.image("https://img.icons8.com/emoji/96/gold-bar.png",width=55)
    st.title("Gold Agent")
    st.caption("🔄 Auto-refreshes every 30s")
    page = st.radio("Navigate",[
        "🧠 Brain Overview","🏆 Deals Ready","💬 Conversations",
        "👻 Ghosted","🛡️ Safety","❌ Errors","📋 All Listings","📊 Stats"])
    st.divider()
    if st.button("🔄 Refresh Now"): st.rerun()
    st.caption(f"Last: {datetime.now().strftime('%H:%M:%S')}")

try:
    _ = db.get_count('all')
except Exception as e:
    st.error(f"❌ Database error: {e}")
    st.info("Check DATABASE_URL in .env — use DATABASE_PUBLIC_URL from Railway for local testing")
    st.stop()

# ════════════════ BRAIN OVERVIEW ════════════════════════════════════════════
if page == "🧠 Brain Overview":
    st.title("🧠 Agent Brain — Live Overview")

    # Job status
    st.subheader("⚙️ Job Status")
    job_runs = db.get_last_job_runs()
    cols = st.columns(4)
    for i,(jk,label,freq) in enumerate([("scrape","🔍 Scrape","20 min"),("score","⭐ Score","25 min"),
                                          ("message","💬 Message","30 min"),("poll","📬 Poll","45 min")]):
        with cols[i]:
            run = job_runs.get(jk)
            if run:
                fa = run.get('finished_at')
                st_txt = run.get('status','?')
                err = run.get('error','')
                if fa:
                    mins = int((datetime.now(fa.tzinfo)-fa).total_seconds()/60)
                    color = "🟢" if st_txt=="done" else "🔴"
                    st.markdown(f"**{label}**\n\n{color} {mins}m ago")
                    if err: st.caption(f"⚠️ {err[:50]}")
                else:
                    st.markdown(f"**{label}**\n\n🔵 Running...")
            else:
                st.markdown(f"**{label}**\n\n⬜ Not run yet")
            st.caption(f"Every {freq}")

    st.divider()

    # Safety status (always visible at top)
    from safety import get_ban_risk_level
    risk_level, risk_desc = get_ban_risk_level()
    risk_class = f"safety-{risk_level}"
    risk_icon = {"low":"✅","medium":"⚠️","high":"🚨","critical":"🆘"}.get(risk_level,"✅")
    st.markdown(f'<div class="{risk_class}"><b>{risk_icon} Account Safety: {risk_level.upper()}</b> — {risk_desc}</div>', unsafe_allow_html=True)
    cooldowns = db.get_all_cooldowns()
    if cooldowns:
        for c in cooldowns:
            st.error(f"🔒 {c['platform'].upper()} in cooldown until {c['until'].strftime('%H:%M')} — {c['reason']}")

    st.divider()

    # Pipeline
    st.subheader("🔄 Pipeline Right Now")
    counts = db.get_pipeline_counts()
    stages = [("new","📥 Scraped"),("scored","⭐ Scored"),("queued_msg","📤 Queued"),
              ("awaiting_reply","⏳ Waiting"),("replied","💬 Replied"),
              ("handover","🏆 Ready"),("approved","✅ Bought"),("ghosted","👻 Ghost")]
    scols = st.columns(len(stages))
    for i,(status,label) in enumerate(stages):
        scols[i].metric(label,counts.get(status,0))

    st.divider()

    # Metrics
    st.subheader("📊 Today")
    m1,m2,m3,m4,m5,m6,m7 = st.columns(7)
    m1.metric("📥 Found",db.get_count('today'))
    m2.metric("⭐ Score≥70",db.get_count('score_gte_70'))
    sent_today = db.messages_sent_today()
    from safety import DAILY_MESSAGE_CAP,WARNING_THRESHOLD
    m3.metric("💬 Messages",f"{sent_today}/{DAILY_MESSAGE_CAP}")
    m4.metric("⏳ Waiting",db.get_count('awaiting_reply'))
    m5.metric("🏆 Deals",db.get_count('handover'))
    m6.metric("👻 Ghosted",db.get_count('ghosted'))
    m7.metric("❌ Errors",db.get_count('errors_today'))

    # Message cap bar
    pct = min(int(sent_today/DAILY_MESSAGE_CAP*100),100)
    color = "normal" if sent_today < WARNING_THRESHOLD else ("off" if sent_today < DAILY_MESSAGE_CAP else "off")
    st.progress(pct, text=f"Daily Message Cap: {sent_today}/{DAILY_MESSAGE_CAP}")
    if sent_today >= DAILY_MESSAGE_CAP:
        st.error("🔴 Daily cap reached. No more messages until midnight.")
    elif sent_today >= WARNING_THRESHOLD:
        st.warning(f"⚠️ Approaching daily limit — {DAILY_MESSAGE_CAP-sent_today} remaining")
    else:
        st.success(f"✅ {DAILY_MESSAGE_CAP-sent_today} messages remaining today")

    st.divider()

    # Activity feed
    st.subheader("📡 Live Activity Feed")
    events = db.get_recent_events(60)
    if not events:
        st.info("No activity yet. Run the agent to see the live feed.")
    for ev in events:
        ts = ev['created_at'].strftime('%H:%M:%S') if hasattr(ev['created_at'],'strftime') else str(ev['created_at'])[:8]
        level = ev.get('level','info')
        cls = 'event-error' if level=='error' else 'event-warn' if level=='warn' else 'event-info'
        icon = '❌' if level=='error' else '⚠️' if level=='warn' else '✓'
        st.markdown(f'<div class="{cls}"><b>{ts}</b> [{ev.get("job","").upper()}] {icon} {ev.get("message","")}</div>',
                    unsafe_allow_html=True)

# ════════════════ DEALS READY ═══════════════════════════════════════════════
elif page == "🏆 Deals Ready":
    st.title("🏆 Deals Ready — Action Required")
    handovers = db.get_listings_by_status("handover")
    if not handovers:
        st.info("No deals ready yet. Agent is working...")
    else:
        st.success(f"{len(handovers)} deal(s) waiting for your decision!")
        for deal in handovers:
            conv  = db.get_conversation(deal["id"])
            score = deal.get("final_score") or deal.get("deal_score",0)
            karat = (conv.get("confirmed_karat") if conv else None) or deal.get("karat","?")
            grams = (conv.get("confirmed_grams") if conv else None) or deal.get("weight_grams","?")
            mv    = (conv.get("melt_value_cad") if conv else None) or deal.get("melt_value_cad")
            profit= conv.get("profit_est_cad") if conv else None
            margin= conv.get("margin_pct") if conv else None
            flags = conv.get("red_flags",[]) if conv else []
            msgs  = conv.get("messages",[]) if conv else []
            if isinstance(msgs,str):
                try: msgs=json.loads(msgs)
                except: msgs=[]
            images = deal.get("images") or []

            deal_class = "deal-good" if score >= 70 else "deal-bad" if score < 40 else ""
            st.markdown(f'<div class="deal-card {deal_class}"><h3>{sc(score)} SCORE {score}/100 &nbsp;|&nbsp; {deal.get("title","")[:60]}</h3>'
                       f'<b>{deal.get("platform","").upper()}</b> &nbsp;|&nbsp; Asking: <b>${deal.get("price_cad","?")} CAD</b></div>',
                       unsafe_allow_html=True)

            # Show images
            if images:
                valid_imgs = [i for i in images if i and i.startswith('http')][:4]
                if valid_imgs:
                    img_cols = st.columns(len(valid_imgs))
                    for i,img_url in enumerate(valid_imgs):
                        with img_cols[i]:
                            try: st.image(img_url)
                            except: st.caption(f"[Image {i+1}]")

            c1,c2,c3 = st.columns(3)
            with c1:
                st.markdown("**📊 Gold Details**")
                st.write(f"Karat: **{karat}K**")
                st.write(f"Weight: **{grams}g**")
                if mv: st.write(f"Melt Value: **${mv:.2f} CAD**")
                if profit is not None:
                    st.write(f"Gross Profit: **${profit:.2f}**" + (f" ({margin:.1f}%)" if margin else ""))
            with c2:
                st.markdown("**🧑 Seller**")
                st.write(f"Condition: {conv.get('condition','?') if conv else '?'}")
                st.write(f"Seller Score: {conv.get('seller_score','?') if conv else '?'}/5")
                st.write(f"Reason: {conv.get('reason_selling','not stated') if conv else '?'}")
                if flags: st.warning(f"⚠️ {', '.join(flags)}")
                else: st.success("✓ No red flags")
            with c3:
                st.markdown("**💬 Conversation**")
                for m in (msgs[-4:] if msgs else []):
                    icon = "🧑" if m.get('role')=='me' else "👤"
                    st.caption(f"{icon} {m.get('text','')[:90]}")

            lc1,lc2 = st.columns(2)
            with lc1:
                if deal.get("url"): st.link_button("🔗 View Listing",deal["url"])
            with lc2:
                if conv and conv.get("conversation_url"): st.link_button("💬 Open Chat",conv["conversation_url"])

            b1,b2 = st.columns(2)
            if b1.button("✅ I'm Buying It!",key=f"buy_{deal['id']}",type="primary"):
                db.update_listing_status(deal["id"],"approved"); st.success("🎉 Go get that gold!"); st.rerun()
            if b2.button("❌ Pass",key=f"rej_{deal['id']}"):
                db.update_listing_status(deal["id"],"rejected"); st.rerun()
            st.divider()

# ════════════════ CONVERSATIONS ═════════════════════════════════════════════
elif page == "💬 Conversations":
    st.title("💬 All Conversations")
    convs = db.get_all_conversations_with_listings()
    if not convs:
        st.info("No conversations yet.")
    else:
        status_filter = st.multiselect("Filter",["awaiting_reply","replied","handover","approved","rejected","ghosted"],
                                       default=["awaiting_reply","replied","handover"])
        filtered = [c for c in convs if c.get('status') in status_filter] if status_filter else convs
        st.caption(f"{len(filtered)} conversations")
        for conv in filtered:
            msgs = conv.get('messages',[])
            if isinstance(msgs,str):
                try: msgs=json.loads(msgs)
                except: msgs=[]
            seller_replied = any(m.get('role')=='seller' for m in msgs)
            la = conv.get('last_activity')
            la_str = la.strftime('%b %d %H:%M') if la and hasattr(la,'strftime') else "?"
            score = conv.get('deal_score',0)
            flags = conv.get('red_flags') or []
            images = conv.get('images') or []

            with st.expander(f"{sc(score)} {score} | {conv.get('title','?')[:45]} | ${conv.get('price_cad','?')} | {conv.get('platform','?').upper()} | {la_str}"):
                # Images
                if images:
                    valid = [i for i in images if i and i.startswith('http')][:3]
                    if valid:
                        ic = st.columns(len(valid))
                        for i,img in enumerate(valid):
                            with ic[i]:
                                try: st.image(img)
                                except: pass

                i1,i2,i3 = st.columns(3)
                with i1:
                    st.markdown(f"**Status:** {pill(conv.get('status','?'))}",unsafe_allow_html=True)
                    st.write(f"Follow-ups: {conv.get('follow_up_count',0)}/2")
                    st.write(f"Last activity: {la_str}")
                    if conv.get('ghosted'): st.error("👻 GHOSTED")
                    if not seller_replied: st.warning("⏳ No reply yet")
                with i2:
                    st.write(f"Karat: {conv.get('confirmed_karat','?')}")
                    st.write(f"Weight: {conv.get('confirmed_grams','?')}g")
                    st.write(f"Condition: {conv.get('condition','?')}")
                    st.write(f"Seller score: {conv.get('seller_score','?')}/5")
                with i3:
                    if conv.get('melt_value_cad'): st.write(f"Melt: ${conv.get('melt_value_cad'):.2f}")
                    if conv.get('profit_est_cad') is not None: st.write(f"Profit est: ${conv.get('profit_est_cad'):.2f}")
                    if flags: st.warning(f"Flags: {', '.join(flags)}")

                st.markdown("**Full Conversation:**")
                for m in msgs:
                    role = m.get('role','?')
                    icon = "🧑 **Me:**" if role=="me" else "👤 **Seller:**"
                    st.markdown(f"{icon} {m.get('text','')}\n\n---")

                if conv.get('listing_url'): st.link_button("🔗 Listing",conv['listing_url'])
                if conv.get('conversation_url'): st.link_button("💬 Chat",conv['conversation_url'])

# ════════════════ GHOSTED ════════════════════════════════════════════════════
elif page == "👻 Ghosted":
    st.title("👻 Ghosted Sellers")
    ghosted = db.get_ghosted_listings()
    if not ghosted:
        st.success("✓ No ghosts — all sellers have replied!")
    else:
        st.warning(f"{len(ghosted)} seller(s) haven't replied in 48+ hours")
        for g in ghosted:
            fa = g.get('first_msg_at')
            h = int((datetime.now(fa.tzinfo)-fa).total_seconds()/3600) if fa and hasattr(fa,'tzinfo') and fa.tzinfo else "?"
            st.markdown(f"👻 **{g.get('title','?')[:60]}** | {g.get('platform','?').upper()} | ${g.get('price_cad','?')} | Score {g.get('deal_score',0)} | {h}h ago")
            c1,c2 = st.columns(2)
            with c1:
                if g.get('url'): st.link_button("🔗 View",g['url'],key=f"gv_{g['id']}")
            with c2:
                if st.button("Mark Dead",key=f"gd_{g['id']}"): db.mark_ghosted(g['id']); st.rerun()
            st.divider()

# ════════════════ SAFETY ════════════════════════════════════════════════════
elif page == "🛡️ Safety":
    st.title("🛡️ Safety & Ban Prevention")
    from safety import get_ban_risk_level, DAILY_MESSAGE_CAP, WARNING_THRESHOLD, COOLDOWN_MINUTES
    risk_level, risk_desc = get_ban_risk_level()
    risk_icon = {"low":"✅","medium":"⚠️","high":"🚨","critical":"🆘"}.get(risk_level,"✅")
    st.markdown(f'<div class="safety-{risk_level}"><h3>{risk_icon} Risk Level: {risk_level.upper()}</h3><p>{risk_desc}</p></div>',
                unsafe_allow_html=True)
    st.divider()

    sent = db.messages_sent_today()
    st.subheader("💬 Daily Message Cap")
    st.progress(min(int(sent/DAILY_MESSAGE_CAP*100),100),text=f"{sent}/{DAILY_MESSAGE_CAP}")
    st.info(f"Warning threshold: {WARNING_THRESHOLD}/day | Hard cap: {DAILY_MESSAGE_CAP}/day | Auto-cooldown: {COOLDOWN_MINUTES}min")

    st.divider()
    st.subheader("🔒 Active Cooldowns")
    cooldowns = db.get_all_cooldowns()
    if cooldowns:
        for c in cooldowns:
            st.error(f"🔒 **{c['platform'].upper()}** — locked until {c['until'].strftime('%H:%M')} | Reason: {c['reason']}")
    else:
        st.success("✓ No active cooldowns")

    st.divider()
    st.subheader("📋 Safety Event Log")
    events = db.get_recent_safety_events(30)
    if events:
        for e in events:
            ts = e['created_at'].strftime('%b %d %H:%M') if hasattr(e['created_at'],'strftime') else "?"
            st.write(f"`{ts}` **[{e['platform']}]** {e['event_type']}: {e['message'][:80]}")
    else:
        st.info("No safety events yet.")

    st.divider()
    st.subheader("📖 What Gets You Banned")
    st.markdown("""
**Facebook (HIGH RISK):**
- Sending >10 messages/day ← hard blocked in code
- Sending identical messages ← we generate unique via AI
- No normal account activity ← manually like posts weekly
- Session looks like a bot ← we use human delays + realistic typing

**Kijiji (LOW RISK):**
- Bulk scraping without delays ← we add delays between requests
- Same IP hitting too often ← use proxy later if needed

**What agent does automatically:**
- Stops all messaging when daily cap hit ✓
- Pauses 2 hours on any rate-limit signal ✓
- 90-200 second random delays between messages ✓
- Rotates user agents each session ✓
- Human-like mouse movement and typing speed ✓
- Alerts you immediately if anything suspicious ✓
    """)

# ════════════════ ERRORS ════════════════════════════════════════════════════
elif page == "❌ Errors":
    st.title("❌ Error Log")
    errors = db.get_recent_errors(50)
    if not errors:
        st.success("✓ No errors! Everything running clean.")
    else:
        st.warning(f"{len(errors)} recent errors")
        for e in errors:
            ts = e['created_at'].strftime('%b %d %H:%M:%S') if hasattr(e['created_at'],'strftime') else "?"
            with st.expander(f"[{e.get('job','?').upper()}] {e.get('message','')[:70]} — {ts}"):
                st.code(e.get('message',''))
                st.caption(f"Job: {e.get('job','')} | Time: {ts}")

    st.divider()
    st.subheader("📋 All Recent Job Runs")
    job_runs = db.get_last_job_runs()
    for job_name, run in job_runs.items():
        err = run.get('error','')
        status = run.get('status','?')
        fa = run.get('finished_at')
        ts = fa.strftime('%H:%M') if fa and hasattr(fa,'strftime') else "running"
        icon = "✅" if status=="done" else "🔴" if status=="error" else "🔵"
        st.write(f"{icon} **{job_name}** — {status} at {ts} | {run.get('details','')} {('| Error: '+err[:60]) if err else ''}")

# ════════════════ ALL LISTINGS ══════════════════════════════════════════════
elif page == "📋 All Listings":
    st.title("📋 All Listings")
    c1,c2,c3 = st.columns(3)
    with c1: min_score = st.slider("Min Score",0,100,0)
    with c2: platforms = st.multiselect("Platform",["facebook","kijiji","craigslist","ebay"],
                                         default=["facebook","kijiji","craigslist","ebay"])
    with c3: statuses = st.multiselect("Status",
        ["new","scored","queued_msg","awaiting_reply","replied","handover","rejected","ghosted","approved"],
        default=["new","scored","queued_msg","awaiting_reply","replied","handover"])
    df = db.get_all_listings(min_score=min_score,platforms=platforms,statuses=statuses)
    if df.empty:
        st.info("No listings match filters.")
    else:
        cols = ["title","price_cad","deal_score","karat","weight_grams","melt_value_cad","platform","status","created_at"]
        avail = [c for c in cols if c in df.columns]
        st.dataframe(df[avail].rename(columns={"price_cad":"Price($)","deal_score":"Score",
            "weight_grams":"Grams","melt_value_cad":"Melt($)","platform":"Platform",
            "status":"Status","created_at":"Found At"}),height=500)
        st.caption(f"{len(df)} listings")

# ════════════════ STATS ══════════════════════════════════════════════════════
elif page == "📊 Stats":
    st.title("📊 Performance Stats")
    s1,s2,s3,s4,s5,s6 = st.columns(6)
    s1.metric("Total Scraped",db.get_count('all'))
    s2.metric("Score≥70",db.get_count('score_gte_70'))
    s3.metric("Messaged",db.get_count('msg_sent'))
    s4.metric("Handovers",db.get_count('handover'))
    s5.metric("Approved",db.get_count('approved'))
    s6.metric("Ghosted",db.get_count('ghosted'))
    st.divider()
    st.subheader("📈 Last 7 Days")
    weekly = db.get_weekly_stats()
    if weekly:
        wdf = pd.DataFrame(weekly)
        wdf['day'] = pd.to_datetime(wdf['day'])
        wdf = wdf.set_index('day')
        st.bar_chart(wdf[['found','high_score','handovers']])
    else:
        st.info("Stats appear after agent runs for a day.")
    st.divider()
    st.subheader("🏪 By Platform")
    try:
        adf = db.get_all_listings()
        if not adf.empty and 'platform' in adf.columns:
            st.dataframe(adf.groupby('platform').agg(count=('id','count'),avg_score=('deal_score','mean')).round(1))
    except: st.info("Not enough data yet.")
    st.divider()
    st.subheader("📬 Reply Rate")
    total_msg = db.get_count('msg_sent')
    total_rep = db.get_count('replied')+db.get_count('handover')+db.get_count('approved')
    if total_msg>0:
        r1,r2,r3 = st.columns(3)
        r1.metric("Sent",total_msg)
        r2.metric("Reply Rate",f"{round(total_rep/total_msg*100,1)}%")
        r3.metric("Ghost Rate",f"{round(db.get_count('ghosted')/total_msg*100,1)}%")
    else:
        st.info("No messages sent yet.")

st.markdown("---")
st.caption("🥇 Gold Deal Hunter — Final Version | Personal Use Only")
