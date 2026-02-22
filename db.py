import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")


# ================== CONNECTION ==================
def get_conn():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=5
    )


# ================== INIT DB ==================
def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:

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
            CREATE INDEX IF NOT EXISTS idx_wallets_chat
            ON wallets(chat_id);
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
            CREATE INDEX IF NOT EXISTS idx_notified_chat
            ON notified_txs(chat_id);
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                UNIQUE(chat_id, user_id)
            );
            """)

    print("Database initialized successfully")


# ================== WALLET ==================
def add_wallet(chat_id, coin, address, note=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO wallets (chat_id, coin, address, note)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (chat_id, coin, address)
                DO UPDATE SET note = EXCLUDED.note
            """, (chat_id, coin, address, note))


def get_wallets():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM wallets")
            return cur.fetchall()


# ================== NOTIFY ==================
def already_notified(chat_id, txid):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM notified_txs WHERE chat_id=%s AND txid=%s",
                (chat_id, txid)
            )
            return cur.fetchone() is not None


def mark_notified(chat_id, txid):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO notified_txs (chat_id, txid)
                VALUES (%s,%s)
                ON CONFLICT DO NOTHING
            """, (chat_id, txid))


# ================== ADMIN ==================
def add_admin(chat_id, user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admins (chat_id, user_id)
                VALUES (%s,%s)
                ON CONFLICT DO NOTHING
            """, (chat_id, user_id))


def remove_admin(chat_id, user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM admins
                WHERE chat_id=%s AND user_id=%s
            """, (chat_id, user_id))


def get_admins(chat_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM admins WHERE chat_id=%s",
                (chat_id,)
            )
            return cur.fetchall()


def is_admin(chat_id, user_id, master_id):
    if user_id == master_id:
        return True

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM admins WHERE chat_id=%s AND user_id=%s",
                (chat_id, user_id)
            )
            return cur.fetchone() is not None
