import os
import asyncio
import requests
from decimal import Decimal
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from db import (
    init_db,
    add_wallet,
    remove_wallet,
    get_wallets,
    add_admin,
    is_admin,
    already_notified,
    mark_notified
)

TOKEN = os.getenv("TOKEN")
MASTER_ID = int(os.getenv("MASTER_ID"))
ETHERSCAN_KEY = os.getenv("ETHERSCAN_KEY")

CHECK_INTERVAL = 30  # วินาที

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
# BTC OUTGOING
# ==========================
def check_btc(address):
    url = f"https://blockstream.info/api/address/{address}/txs"
    data = requests.get(url).json()
    if not data:
        return None

    for tx in data[:5]:  # เช็ค 5 รายการล่าสุด
        txid = tx["txid"]

        for vin in tx["vin"]:
            if vin.get("prevout", {}).get("scriptpubkey_address") == address:
                amount = Decimal(tx["vout"][0]["value"]) / Decimal(100000000)
                return txid, amount, tx["status"]["block_time"]

    return None

# ==========================
# ETH / USDT OUTGOING
# ==========================
def check_eth(address, token=False):
    action = "tokentx" if token else "txlist"
    url = (
        f"https://api.etherscan.io/api?"
        f"module=account&action={action}"
        f"&address={address}&sort=desc&apikey={ETHERSCAN_KEY}"
    )

    res = requests.get(url).json()
    if res["status"] != "1":
        return None

    for tx in res["result"][:5]:
        if tx["from"].lower() == address.lower():
            amount = Decimal(tx["value"]) / Decimal(10**18)
            return tx["hash"], amount, int(tx["timeStamp"])

    return None

# ==========================
# COMMANDS
# ==========================
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ Admin เท่านั้น")
        return

    try:
        coin = context.args[0].upper()
        address = context.args[1]

        if coin not in ["BTC", "ETH", "USDT"]:
            await update.message.reply_text("รองรับ: BTC ETH USDT")
            return

        add_wallet(chat_id, coin, address)
        await update.message.reply_text("✅ เพิ่มสำเร็จ")

    except:
        await update.message.reply_text("ใช้: /add BTC address")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ Admin เท่านั้น")
        return

    try:
        address = context.args[0]
        remove_wallet(chat_id, address)
        await update.message.reply_text("🗑 ลบสำเร็จ")
    except:
        await update.message.reply_text("ใช้: /remove address")

async def list_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    wallets = get_wallets()

    rows = [w for w in wallets if w["chat_id"] == chat_id]

    if not rows:
        await update.message.reply_text("ไม่มี address")
        return

    text = "📋 Wallets\n"
    for w in rows:
        text += f"{w['coin']} → {w['address']}\n"

    await update.message.reply_text(text)

async def setadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ID:
        await update.message.reply_text("⛔ Master เท่านั้น")
        return

    try:
        new_admin = int(context.args[0])
        add_admin(update.effective_chat.id, new_admin)
        await update.message.reply_text("👑 ตั้ง admin สำเร็จ")
    except:
        await update.message.reply_text("ใช้: /setadmin user_id")

# ==========================
# AUTO CHECK LOOP
# ==========================
async def auto_check(app):
    while True:
        wallets = get_wallets()

        for w in wallets:
            chat_id = w["chat_id"]
            coin = w["coin"]
            address = w["address"]

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

                if already_notified(chat_id, txid):
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
                mark_notified(chat_id, txid)

            except Exception as e:
                print("Error:", e)

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
