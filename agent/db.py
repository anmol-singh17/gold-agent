"""
db.py — Complete PostgreSQL state management. Every event, failure, warning tracked.
"""
import os, json, psycopg2, psycopg2.extras
from datetime import date, datetime
from dotenv import load_dotenv
load_dotenv()

def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS listings (
        id SERIAL PRIMARY KEY,
        platform TEXT,
        external_id TEXT UNIQUE,
        url TEXT,
        title TEXT,
        description TEXT,
        price_cad FLOAT,
        city TEXT,
        images TEXT[],
        weight_grams FLOAT,
        karat INT,
        hallmark_seen BOOL DEFAULT FALSE,
        item_type TEXT,
        melt_value_cad FLOAT,
        deal_score INT DEFAULT 0,
        final_score INT DEFAULT 0,
        confidence FLOAT DEFAULT 0.0,
        score_reasons TEXT[],
        status TEXT DEFAULT 'new',
        first_msg_at TIMESTAMPTZ,
        last_checked_at TIMESTAMPTZ,
        follow_up_count INT DEFAULT 0,
        ghosted BOOL DEFAULT FALSE,
        price_history JSONB DEFAULT '[]',
        notified BOOL DEFAULT FALSE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_listings_status  ON listings(status);
    CREATE INDEX IF NOT EXISTS idx_listings_score   ON listings(deal_score);
    CREATE INDEX IF NOT EXISTS idx_listings_created ON listings(created_at);
    CREATE INDEX IF NOT EXISTS idx_listings_ext     ON listings(external_id);

    CREATE TABLE IF NOT EXISTS conversations (
        id SERIAL PRIMARY KEY,
        listing_id INT REFERENCES listings(id),
        platform TEXT,
        conversation_url TEXT,
        messages JSONB DEFAULT '[]',
        confirmed_grams FLOAT,
        confirmed_karat INT,
        condition TEXT,
        reason_selling TEXT,
        seller_score INT,
        red_flags TEXT[],
        melt_value_cad FLOAT,
        profit_est_cad FLOAT,
        margin_pct FLOAT,
        handover_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS message_log (
        id SERIAL PRIMARY KEY,
        listing_id INT,
        platform TEXT,
        sent_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS agent_events (
        id SERIAL PRIMARY KEY,
        job TEXT,
        message TEXT,
        level TEXT DEFAULT 'info',
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS job_runs (
        id SERIAL PRIMARY KEY,
        job_name TEXT,
        started_at TIMESTAMPTZ DEFAULT NOW(),
        finished_at TIMESTAMPTZ,
        status TEXT DEFAULT 'running',
        details TEXT,
        error TEXT
    );

    CREATE TABLE IF NOT EXISTS safety_events (
        id SERIAL PRIMARY KEY,
        platform TEXT,
        event_type TEXT,
        message TEXT,
        action_taken TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS cooldowns (
        id SERIAL PRIMARY KEY,
        platform TEXT UNIQUE,
        until TIMESTAMPTZ,
        reason TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("[DB] All tables ready.")

# ── LISTINGS ──────────────────────────────────────────────────────────────────
def listing_exists(external_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM listings WHERE external_id=%s",(external_id,))
            return cur.fetchone() is not None

def get_listing_price(external_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT price_cad, id FROM listings WHERE external_id=%s",(external_id,))
            row = cur.fetchone()
            return row if row else None

def save_listing(data):
    data.setdefault('description','')
    data.setdefault('city','toronto')
    data.setdefault('images',[])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO listings
                (platform,external_id,url,title,description,price_cad,city,images,status)
                VALUES (%(platform)s,%(external_id)s,%(url)s,%(title)s,%(description)s,
                %(price_cad)s,%(city)s,%(images)s,%(status)s)
                ON CONFLICT (external_id) DO NOTHING""", data)
        conn.commit()

def update_listing_price(listing_id, new_price, old_price):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""UPDATE listings SET price_cad=%s,
                price_history=price_history || %s::jsonb,
                status=CASE WHEN status='scored' THEN 'new' ELSE status END
                WHERE id=%s""",
                (new_price, json.dumps([{"price":old_price,"at":datetime.now().isoformat()}]), listing_id))
        conn.commit()

def get_listings_by_status(status, limit=50):
    if isinstance(status, list):
        ph = ','.join(['%s']*len(status))
        sql = f"SELECT * FROM listings WHERE status IN ({ph}) ORDER BY deal_score DESC LIMIT %s"
        params = status + [limit]
    else:
        sql = "SELECT * FROM listings WHERE status=%s ORDER BY deal_score DESC LIMIT %s"
        params = [status, limit]
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

def update_listing_score(listing_id, score, merged, reasons):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""UPDATE listings SET deal_score=%(s)s,final_score=%(s)s,
                weight_grams=%(w)s,karat=%(k)s,hallmark_seen=%(h)s,item_type=%(it)s,
                confidence=%(c)s,melt_value_cad=%(mv)s,score_reasons=%(r)s,
                last_checked_at=NOW() WHERE id=%(id)s""",
                {'s':score,'w':merged.get('weight_grams'),'k':merged.get('karat'),
                 'h':merged.get('hallmark_seen',False),'it':merged.get('item_type'),
                 'c':merged.get('confidence',0.0),'mv':merged.get('melt_value_cad'),
                 'r':reasons,'id':listing_id})
        conn.commit()

def update_listing_status(listing_id, status):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE listings SET status=%s WHERE id=%s",(status,listing_id))
        conn.commit()

def mark_notified(listing_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE listings SET notified=TRUE WHERE id=%s",(listing_id,))
        conn.commit()

def mark_ghosted(listing_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE listings SET ghosted=TRUE,status='ghosted' WHERE id=%s",(listing_id,))
        conn.commit()

def increment_followup_count(listing_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE listings SET follow_up_count=follow_up_count+1 WHERE id=%s",(listing_id,))
        conn.commit()

def get_duplicate_check(title, price_cad):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT id,platform,external_id,status FROM listings
                WHERE LOWER(title) LIKE %s AND ABS(COALESCE(price_cad,0)-%s)<20
                AND status NOT IN ('new','rejected')""",
                (f"%{title[:20].lower()}%", price_cad or 0))
            return [dict(r) for r in cur.fetchall()]

# ── CONVERSATIONS ─────────────────────────────────────────────────────────────
def save_conversation(listing_id, platform, conversation_url, messages):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO conversations
                (listing_id,platform,conversation_url,messages)
                VALUES (%s,%s,%s,%s)""",
                (listing_id,platform,conversation_url,json.dumps(messages)))
            cur.execute("UPDATE listings SET first_msg_at=NOW() WHERE id=%s",(listing_id,))
        conn.commit()

def get_conversation(listing_id):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM conversations WHERE listing_id=%s ORDER BY id DESC LIMIT 1",(listing_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def update_conversation_messages(conv_id, messages):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE conversations SET messages=%s,updated_at=NOW() WHERE id=%s",
                (json.dumps(messages),conv_id))
        conn.commit()

def update_conversation_parsed(conv_id, parsed, profit):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""UPDATE conversations SET confirmed_grams=%(cg)s,confirmed_karat=%(ck)s,
                condition=%(cond)s,reason_selling=%(rs)s,seller_score=%(ss)s,red_flags=%(rf)s,
                melt_value_cad=%(mv)s,profit_est_cad=%(pe)s,margin_pct=%(mp)s,
                handover_at=NOW(),updated_at=NOW() WHERE id=%(id)s""",
                {'cg':parsed.get('confirmed_grams'),'ck':parsed.get('confirmed_karat'),
                 'cond':parsed.get('condition'),'rs':parsed.get('reason_selling'),
                 'ss':parsed.get('seller_reliability'),'rf':parsed.get('red_flags',[]),
                 'mv':profit.get('melt_value_cad'),'pe':profit.get('gross_margin_cad'),
                 'mp':profit.get('margin_pct'),'id':conv_id})
        conn.commit()

def get_all_conversations_with_listings():
    sql = """SELECT l.id,l.title,l.platform,l.price_cad,l.deal_score,l.status,
                    l.follow_up_count,l.ghosted,l.first_msg_at,l.url as listing_url,
                    l.images,c.id as conv_id,c.conversation_url,c.messages,
                    c.confirmed_karat,c.confirmed_grams,c.condition,c.seller_score,
                    c.red_flags,c.profit_est_cad,c.melt_value_cad,c.updated_at as last_activity
             FROM listings l LEFT JOIN conversations c ON l.id=c.listing_id
             WHERE l.status NOT IN ('new','scored','rejected')
             ORDER BY c.updated_at DESC NULLS LAST LIMIT 100"""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]

# ── MESSAGES ──────────────────────────────────────────────────────────────────
def messages_sent_today():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM message_log WHERE sent_at::date=%s",(date.today(),))
            return cur.fetchone()[0]

def log_message_sent(listing_id=None, platform=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO message_log (listing_id,platform) VALUES (%s,%s)",(listing_id,platform))
        conn.commit()

def get_messages_sent_today_detail():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT ml.sent_at,l.title,ml.platform
                FROM message_log ml LEFT JOIN listings l ON ml.listing_id=l.id
                WHERE ml.sent_at::date=%s ORDER BY ml.sent_at DESC""",(date.today(),))
            return [dict(r) for r in cur.fetchall()]

# ── SAFETY ────────────────────────────────────────────────────────────────────
def log_safety_event(platform, event_type, message, action_taken="none"):
    print(f"[SAFETY] [{platform}] {event_type}: {message}")
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO safety_events (platform,event_type,message,action_taken) VALUES (%s,%s,%s,%s)",
                    (platform,event_type,message,action_taken))
            conn.commit()
    except: pass

def set_cooldown(platform, minutes, reason):
    from datetime import timedelta
    until = datetime.now() + timedelta(minutes=minutes)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO cooldowns (platform,until,reason)
                VALUES (%s,%s,%s) ON CONFLICT (platform) DO UPDATE
                SET until=%s,reason=%s,created_at=NOW()""",
                (platform,until,reason,until,reason))
        conn.commit()
    log_safety_event(platform,"cooldown",f"Cooldown set for {minutes}min: {reason}","paused")

def is_in_cooldown(platform):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT until,reason FROM cooldowns WHERE platform=%s AND until>NOW()",(platform,))
            row = cur.fetchone()
            return row if row else None

def get_all_cooldowns():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM cooldowns WHERE until>NOW()")
            return [dict(r) for r in cur.fetchall()]

def get_recent_safety_events(limit=20):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM safety_events ORDER BY created_at DESC LIMIT %s",(limit,))
            return [dict(r) for r in cur.fetchall()]

# ── EVENTS & JOBS ─────────────────────────────────────────────────────────────
def log_agent_event(job, message, level="info"):
    print(f"[{job.upper()}] [{level.upper()}] {message}")
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO agent_events (job,message,level) VALUES (%s,%s,%s)",
                    (job,message,level))
            conn.commit()
    except: pass

def get_recent_events(limit=80):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM agent_events ORDER BY created_at DESC LIMIT %s",(limit,))
            return [dict(r) for r in cur.fetchall()]

def get_recent_errors(limit=20):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM agent_events WHERE level='error' ORDER BY created_at DESC LIMIT %s",(limit,))
            return [dict(r) for r in cur.fetchall()]

def start_job_run(job_name):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO job_runs (job_name) VALUES (%s) RETURNING id",(job_name,))
            run_id = cur.fetchone()[0]
        conn.commit()
    return run_id

def finish_job_run(run_id, status="done", details="", error=""):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE job_runs SET finished_at=NOW(),status=%s,details=%s,error=%s WHERE id=%s",
                (status,details,error,run_id))
        conn.commit()

def get_last_job_runs():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT DISTINCT ON (job_name) job_name,started_at,
                finished_at,status,details,error FROM job_runs
                ORDER BY job_name,started_at DESC""")
            return {r['job_name']:dict(r) for r in cur.fetchall()}

# ── COUNTS & STATS ────────────────────────────────────────────────────────────
def get_count(metric):
    queries = {
        'all':            "SELECT COUNT(*) FROM listings",
        'today':          "SELECT COUNT(*) FROM listings WHERE created_at::date=CURRENT_DATE",
        'score_gte_70':   "SELECT COUNT(*) FROM listings WHERE deal_score>=70",
        'queued':         "SELECT COUNT(*) FROM listings WHERE status='queued_msg'",
        'msg_sent':       "SELECT COUNT(*) FROM listings WHERE status IN ('msg_sent','awaiting_reply','replied')",
        'awaiting_reply': "SELECT COUNT(*) FROM listings WHERE status='awaiting_reply'",
        'replied':        "SELECT COUNT(*) FROM listings WHERE status='replied'",
        'handover':       "SELECT COUNT(*) FROM listings WHERE status='handover'",
        'ghosted':        "SELECT COUNT(*) FROM listings WHERE ghosted=TRUE",
        'rejected':       "SELECT COUNT(*) FROM listings WHERE status='rejected'",
        'approved':       "SELECT COUNT(*) FROM listings WHERE status='approved'",
        'errors_today':   "SELECT COUNT(*) FROM agent_events WHERE level='error' AND created_at::date=CURRENT_DATE",
    }
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(queries.get(metric,"SELECT 0"))
            return cur.fetchone()[0]

def get_pipeline_counts():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT status,COUNT(*) as cnt FROM listings GROUP BY status")
            return {r['status']:r['cnt'] for r in cur.fetchall()}

def get_all_listings(min_score=0, platforms=None, statuses=None, limit=500):
    import pandas as pd
    conds=["deal_score>=%s"]; params=[min_score]
    if platforms:
        conds.append(f"platform IN ({','.join(['%s']*len(platforms))})"); params+=platforms
    if statuses:
        conds.append(f"status IN ({','.join(['%s']*len(statuses))})"); params+=statuses
    sql=f"SELECT * FROM listings WHERE {' AND '.join(conds)} ORDER BY deal_score DESC LIMIT {limit}"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql,params)
            rows=cur.fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

def get_ghosted_listings():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT * FROM listings WHERE status='awaiting_reply'
                AND first_msg_at < NOW()-INTERVAL '48 hours' ORDER BY first_msg_at ASC""")
            return [dict(r) for r in cur.fetchall()]

def get_weekly_stats():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT DATE(created_at) as day,COUNT(*) as found,
                COUNT(CASE WHEN deal_score>=70 THEN 1 END) as high_score,
                COUNT(CASE WHEN status='handover' THEN 1 END) as handovers
                FROM listings WHERE created_at>NOW()-INTERVAL '7 days'
                GROUP BY DATE(created_at) ORDER BY day""")
            return [dict(r) for r in cur.fetchall()]
