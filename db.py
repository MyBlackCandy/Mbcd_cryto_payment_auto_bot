import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

DATABASE_URL = os.getenv("DATABASE_URL")

_connection_pool = None


# ================== CONNECTION POOL ==================
def init_pool():
    global _connection_pool

    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")

    _connection_pool = pool.SimpleConnectionPool(
        1, 10,   # min 1 max 10 connection
        DATABASE_URL,
        sslmode="require",
        connect_timeout=5
    )


def get_conn():
    return _connection_pool.getconn()


def put_conn(conn):
    _connection_pool.putconn(conn)


# ================== INIT DATABASE ==================
def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:

            # ---------------- Wallet Table ----------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                coin VARCHAR(20) NOT NULL,
                address TEXT NOT NULL,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, address)
            );
            """)

            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallets_chat
            ON wallets(chat_id);
            """)

            # ---------------- Notified Table ----------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS notified (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                txid TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, txid)
            );
            """)

            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_notified_chat_tx
            ON notified(chat_id, txid);
            """)

            # ---------------- Admin Table ----------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                UNIQUE(chat_id, user_id)
            );
            """)

        conn.commit()
        print("Database initialized successfully")

    finally:
        put_conn(conn)


# ================== WALLET ==================
def add_wallet(chat_id, coin, address, note):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO wallets (chat_id, coin, address, note)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (chat_id, address)
                DO UPDATE SET note = EXCLUDED.note
            """, (chat_id, coin, address, note))
        conn.commit()
    finally:
        put_conn(conn)


def get_wallets(chat_id):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM wallets WHERE chat_id=%s ORDER BY id DESC",
                (chat_id,)
            )
            return cur.fetchall()
    finally:
        put_conn(conn)


def get_all_wallets():
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM wallets")
            return cur.fetchall()
    finally:
        put_conn(conn)


def delete_wallet(chat_id, address):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM wallets WHERE chat_id=%s AND address=%s",
                (chat_id, address)
            )
        conn.commit()
    finally:
        put_conn(conn)


# ================== NOTIFY ==================
def is_notified(chat_id, txid):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM notified WHERE chat_id=%s AND txid=%s",
                (chat_id, txid)
            )
            return cur.fetchone() is not None
    finally:
        put_conn(conn)


def mark_notified(chat_id, txid):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO notified (chat_id, txid)
                VALUES (%s,%s)
                ON CONFLICT DO NOTHING
            """, (chat_id, txid))
        conn.commit()
    finally:
        put_conn(conn)


# ================== ADMIN ==================
def add_admin(chat_id, user_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admins (chat_id, user_id)
                VALUES (%s,%s)
                ON CONFLICT DO NOTHING
            """, (chat_id, user_id))
        conn.commit()
    finally:
        put_conn(conn)


def remove_admin(chat_id, user_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM admins WHERE chat_id=%s AND user_id=%s",
                (chat_id, user_id)
            )
        conn.commit()
    finally:
        put_conn(conn)


def get_admins(chat_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM admins WHERE chat_id=%s",
                (chat_id,)
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        put_conn(conn)


def is_admin(chat_id, user_id, master_id):
    if user_id == master_id:
        return True

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM admins WHERE chat_id=%s AND user_id=%s",
                (chat_id, user_id)
            )
            return cur.fetchone() is not None
    finally:
        put_conn(conn)
