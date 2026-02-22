import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

# ==========================
# CONNECT
# ==========================
def get_conn():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )

# ==========================
# INIT TABLES
# ==========================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # ตาราง wallets
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        coin VARCHAR(10) NOT NULL,
        address TEXT NOT NULL,
        last_tx TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # ป้องกันเพิ่ม address ซ้ำในกลุ่มเดียวกัน
    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS unique_wallet_per_group
    ON wallets(chat_id, address);
    """)

    # index เร็วขึ้น
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_wallet_chat
    ON wallets(chat_id);
    """)

    # ตาราง admins
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL
    );
    """)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS unique_admin_per_group
    ON admins(chat_id, user_id);
    """)

    conn.commit()
    cur.close()
    conn.close()

# ==========================
# WALLET FUNCTIONS
# ==========================
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

    cur.execute("""
        SELECT * FROM wallets
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# ==========================
# ADMIN FUNCTIONS
# ==========================
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

def is_admin(chat_id, user_id):
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
