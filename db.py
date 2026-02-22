import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=5
    )

def init_db():
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            coin VARCHAR(20) NOT NULL,
            address TEXT NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, coin, address)
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS notified_txs (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            txid TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, txid)
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            UNIQUE(chat_id, user_id)
        );
        """)

        conn.commit()
        conn.close()

        print("Database initialized successfully")

    except Exception as e:
        print("Database init error:", e)
        raise

def add_wallet(chat_id, coin, address, note=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO wallets (chat_id, coin, address, note)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (chat_id, coin, address)
        DO UPDATE SET note = EXCLUDED.note
    """, (chat_id, coin, address, note))
    conn.commit()
    conn.close()

def get_wallets():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM wallets")
    rows = cur.fetchall()
    conn.close()
    return rows

def already_notified(chat_id, txid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM notified_txs WHERE chat_id=%s AND txid=%s",
        (chat_id, txid)
    )
    result = cur.fetchone()
    conn.close()
    return result is not None

def mark_notified(chat_id, txid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notified_txs (chat_id, txid)
        VALUES (%s,%s)
        ON CONFLICT DO NOTHING
    """, (chat_id, txid))
    conn.commit()
    conn.close()

def add_admin(chat_id, user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO admins (chat_id,user_id)
        VALUES (%s,%s)
        ON CONFLICT DO NOTHING
    """, (chat_id, user_id))
    conn.commit()
    conn.close()

def remove_admin(chat_id, user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM admins WHERE chat_id=%s AND user_id=%s
    """, (chat_id, user_id))
    conn.commit()
    conn.close()

def get_admins(chat_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE chat_id=%s", (chat_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def is_admin(chat_id, user_id, master_id):
    if user_id == master_id:
        return True

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM admins WHERE chat_id=%s AND user_id=%s",
        (chat_id, user_id)
    )
    result = cur.fetchone()
    conn.close()
    return result is not None
