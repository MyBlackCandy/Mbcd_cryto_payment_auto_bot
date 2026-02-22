import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # wallets
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        coin VARCHAR(10) NOT NULL,
        address TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(chat_id, address)
    );
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_wallet_chat
    ON wallets(chat_id);
    """)

    # admins
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        UNIQUE(chat_id, user_id)
    );
    """)

    # notified transactions (กันซ้ำ 100%)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notified_txs (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        txid TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(chat_id, txid)
    );
    """)

    conn.commit()
    cur.close()
    conn.close()

# ===== Wallet =====

def add_wallet(chat_id, coin, address):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO wallets (chat_id, coin, address)
        VALUES (%s, %s, %s)
        ON CONFLICT (chat_id, address) DO NOTHING
    """, (chat_id, coin, address))
    conn.commit()
    cur.close()
    conn.close()

def remove_wallet(chat_id, address):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM wallets
        WHERE chat_id=%s AND address=%s
    """, (chat_id, address))
    conn.commit()
    cur.close()
    conn.close()

def get_wallets():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM wallets")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# ===== Admin =====

def add_admin(chat_id, user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO admins (chat_id, user_id)
        VALUES (%s, %s)
        ON CONFLICT (chat_id, user_id) DO NOTHING
    """, (chat_id, user_id))
    conn.commit()
    cur.close()
    conn.close()

def is_admin(chat_id, user_id, master_id):
    if user_id == master_id:
        return True

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM admins
        WHERE chat_id=%s AND user_id=%s
    """, (chat_id, user_id))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None

# ===== Notify Control =====

def already_notified(chat_id, txid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM notified_txs
        WHERE chat_id=%s AND txid=%s
    """, (chat_id, txid))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None

def mark_notified(chat_id, txid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notified_txs (chat_id, txid)
        VALUES (%s, %s)
        ON CONFLICT (chat_id, txid) DO NOTHING
    """, (chat_id, txid))
    conn.commit()
    cur.close()
    conn.close()
