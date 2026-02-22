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
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE,
        role VARCHAR(20) DEFAULT 'admin'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        id SERIAL PRIMARY KEY,
        group_id BIGINT,
        symbol VARCHAR(30),
        address TEXT,
        note TEXT,
        last_tx_hash TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    conn.commit()
    cur.close()
    conn.close()


# ================= USERS =================

def add_admin(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (telegram_id, role)
        VALUES (%s,'admin')
        ON CONFLICT DO NOTHING
    """, (user_id,))
    conn.commit()
    cur.close()
    conn.close()


def remove_admin(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE telegram_id=%s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


def get_admins():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT telegram_id FROM users")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def is_admin(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE telegram_id=%s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return bool(result)


# ================= WALLETS =================

def add_wallet(group_id, symbol, address, note):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO wallets (group_id, symbol, address, note)
        VALUES (%s,%s,%s,%s)
    """, (group_id, symbol, address, note))
    conn.commit()
    cur.close()
    conn.close()


def remove_wallet(wallet_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM wallets WHERE id=%s", (wallet_id,))
    conn.commit()
    cur.close()
    conn.close()


def get_wallets(group_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM wallets WHERE group_id=%s", (group_id,))
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
    cur.execute(
        "UPDATE wallets SET last_tx_hash=%s WHERE id=%s",
        (tx_hash, wallet_id)
    )
    conn.commit()
    cur.close()
    conn.close()
