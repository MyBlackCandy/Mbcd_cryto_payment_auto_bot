import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT,
        chain VARCHAR(20),
        address TEXT,
        last_tx_hash TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    conn.commit()
    cur.close()
    conn.close()

# ================= CRUD =================

def add_wallet(chat_id, chain, address):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO wallets (chat_id, chain, address)
        VALUES (%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, (chat_id, chain, address))
    conn.commit()
    cur.close()
    conn.close()

def remove_wallet(chat_id, chain, address):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM wallets
        WHERE chat_id=%s AND chain=%s AND address=%s
    """, (chat_id, chain, address))
    conn.commit()
    cur.close()
    conn.close()

def get_wallets(chat_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT * FROM wallets WHERE chat_id=%s
    """, (chat_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_all_wallets():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM wallets")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def update_last_tx(wallet_id, tx_hash):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE wallets SET last_tx_hash=%s WHERE id=%s
    """, (tx_hash, wallet_id))
    conn.commit()
    cur.close()
    conn.close()
