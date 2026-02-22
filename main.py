import os
import asyncio
import requests
from datetime import datetime
from decimal import Decimal
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import psycopg2

# ==========================
# ENV
# ==========================
TOKEN = os.getenv("TOKEN")
MASTER_ID = int(os.getenv("MASTER_ID"))
ETHERSCAN_KEY = os.getenv("ETHERSCAN_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

CHECK_INTERVAL = 30  # วินาที

# ==========================
# DATABASE
# ==========================
def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT,
        coin TEXT,
        address TEXT,
        last_tx TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        chat_id BIGINT,
        user_id BIGINT
    )
    """)

    conn.commit()
    conn.close()

# ==========================
# ADMIN SYSTEM
# ==========================
def is_admin(chat_id, user_id):
    if user_id == MASTER_ID:
        return True

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM admins WHERE chat_id=%s AND user_id=%s",
        (chat_id, user_id),
    )
    result = cur.fetchone()
    conn.close()
    return result is not None

# ==========================
# COMMANDS
# ==========================
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id):
        await update.message.reply_text("⛔ Admin เท่านั้น")
        return

    try:
        coin = context.args[0].upper()
        address = context.args[1]

        if coin not in ["BTC", "ETH", "USDT"]:
            await update.message.reply_text("เหรียญรองรับ: BTC ETH USDT")
            return

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO wallets (chat_id, coin, address) VALUES (%s,%s,%s)",
            (chat_id, coin, address),
        )
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ เพิ่ม {coin} สำเร็จ")

    except:
        await update.message.reply_text("ใช้: /add BTC address")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id):
        await update.message.reply_text("⛔ Admin เท่านั้น")
        return

    try:
        address = context.args[0]

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM wallets WHERE chat_id=%s AND address=%s",
            (chat_id, address),
        )
        conn.commit()
        conn.close()

        await update.message.reply_text("🗑 ลบสำเร็จ")

    except:
        await update.message.reply_text("ใช้: /remove address")

async def list_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT coin, address FROM wallets WHERE chat_id=%s",
        (chat_id,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("ไม่มี address")
        return

    text = "📋 Wallets\n"
    for coin, addr in rows:
        text += f"{coin} → {addr}\n"

    await update.message.reply_text(text)

async def setadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id != MASTER_ID:
        await update.message.reply_text("⛔ Master เท่านั้น")
        return

    try:
        new_admin = int(context.args[0])

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO admins (chat_id, user_id) VALUES (%s,%s)",
            (chat_id, new_admin),
        )
        conn.commit()
        conn.close()

        await update.message.reply_text("👑 ตั้ง admin สำเร็จ")

    except:
        await update.message.reply_text("ใช้: /setadmin user_id")

# ==========================
# PRICE (USD)
# ==========================
def get_price(coin):
    coin_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "USDT": "tether"
    }

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_map[coin]}&vs_currencies=usd"
    data = requests.get(url).json()
    return Decimal(str(list(data.values())[0]["usd"]))

# ==========================
# BLOCKCHAIN CHECK
# ==========================
def check_btc(address):
    data = requests.get(
        f"https://blockstream.info/api/address/{address}/txs"
    ).json()

    if not data:
        return None

    tx = data[0]

    # ตรวจ outgoing
    for vin in tx["vin"]:
        if vin.get("prevout", {}).get("scriptpubkey_address") == address:
            amount = Decimal(tx["vout"][0]["value"]) / Decimal(100000000)
            return tx["txid"], amount, tx["status"]["block_time"]

    return None

def check_eth(address, token=False):
    if token:
        action = "tokentx"
    else:
        action = "txlist"

    url = (
        f"https://api.etherscan.io/api?"
        f"module=account&action={action}"
        f"&address={address}&sort=desc&apikey={ETHERSCAN_KEY}"
    )

    res = requests.get(url).json()

    if res["status"] != "1":
        return None

    tx = res["result"][0]

    if tx["from"].lower() != address.lower():
        return None

    amount = Decimal(tx["value"]) / Decimal(10**18)
    return tx["hash"], amount, int(tx["timeStamp"])

# ==========================
# AUTO CHECK LOOP
# ==========================
async def auto_check(app):
    while True:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, chat_id, coin, address, last_tx FROM wallets")
        rows = cur.fetchall()

        for wid, chat_id, coin, address, last_tx in rows:
            try:
                if coin == "BTC":
                    result = check_btc(address)
                elif coin == "ETH":
                    result = check_eth(address)
                else:
                    result = check_eth(address, token=True)

                if not result:
                    continue

                txid, amount, timestamp = result

                if txid == last_tx:
                    continue

                price = get_price(coin)
                total = amount * price

                text = (
                    f"🚨 OUTGOING DETECTED\n\n"
                    f"Coin: {coin}\n"
                    f"Amount: {amount:.6f}\n"
                    f"Price: ${price:,.2f}\n"
                    f"Value: ${total:,.2f}\n\n"
                    f"Time: {datetime.utcfromtimestamp(timestamp)}"
                )

                await app.bot.send_message(chat_id, text)

                cur.execute(
                    "UPDATE wallets SET last_tx=%s WHERE id=%s",
                    (txid, wid),
                )
                conn.commit()

            except Exception as e:
                print("Error:", e)

        conn.close()
        await asyncio.sleep(CHECK_INTERVAL)

# ==========================
# MAIN
# ==========================
def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("list", list_wallet))
    app.add_handler(CommandHandler("setadmin", setadmin))

    app.job_queue.run_once(
        lambda ctx: asyncio.create_task(auto_check(app)), 1
    )

    app.run_polling()

if __name__ == "__main__":
    main()
