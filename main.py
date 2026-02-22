import os
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from db import init_db, add_wallet, remove_wallet, get_wallets

TOKEN = os.getenv("TOKEN")
ETHERSCAN_KEY = os.getenv("ETHERSCAN_KEY")

init_db()

# ==========================
def get_btc_tx(address):
    url = f"https://blockstream.info/api/address/{address}/txs"
    res = requests.get(url)
    data = res.json()
    for tx in data:
        for vout in tx["vout"]:
            if vout.get("scriptpubkey_address") != address:
                return tx, vout
    return None, None

# ==========================
def get_eth_tx(address):
    url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&sort=desc&apikey={ETHERSCAN_KEY}"
    res = requests.get(url).json()
    if res["status"] == "1":
        for tx in res["result"]:
            if tx["from"].lower() == address.lower():
                return tx
    return None

# ==========================
def get_price(coin, timestamp):
    date = datetime.utcfromtimestamp(int(timestamp)).strftime("%d-%m-%Y")
    coin_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "USDT": "tether"
    }
    url = f"https://api.coingecko.com/api/v3/coins/{coin_map[coin]}/history?date={date}"
    try:
        data = requests.get(url).json()
        return data["market_data"]["current_price"]["usd"]
    except:
        return None

# ==========================
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].upper()
        address = context.args[1]
        add_wallet(coin, address)
        await update.message.reply_text(f"✅ เพิ่ม {coin} address สำเร็จ")
    except:
        await update.message.reply_text("ใช้คำสั่ง: /add BTC address")

# ==========================
async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = context.args[0]
        remove_wallet(address)
        await update.message.reply_text("🗑 ลบสำเร็จ")
    except:
        await update.message.reply_text("ใช้คำสั่ง: /remove address")

# ==========================
async def list_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallets = get_wallets()
    if not wallets:
        await update.message.reply_text("ไม่มี address")
        return

    text = "📋 รายการ Address\n"
    for coin, addr in wallets:
        text += f"{coin} → {addr}\n"
    await update.message.reply_text(text)

# ==========================
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallets = get_wallets()
    if not wallets:
        await update.message.reply_text("ไม่มี address")
        return

    for coin, address in wallets:

        if coin == "BTC":
            tx, vout = get_btc_tx(address)
            if not tx:
                continue
            amount = vout["value"] / 100000000
            timestamp = tx["status"]["block_time"]
            to_addr = vout["scriptpubkey_address"]

        else:
            tx = get_eth_tx(address)
            if not tx:
                continue
            amount = int(tx["value"]) / 10**18
            timestamp = tx["timeStamp"]
            to_addr = tx["to"]

        price = get_price(coin, timestamp)

        if price:
            total = amount * price
            text = f"""
📤 {coin} โอนออก

🪙 {amount:.6f}
💵 ราคา: ${price:,.2f}
💰 รวม: ${total:,.2f}

📤 ไปที่:
{to_addr}

⏰ {datetime.utcfromtimestamp(int(timestamp))}
"""
            await update.message.reply_text(text)

# ==========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("list", list_wallet))
    app.add_handler(CommandHandler("check", check))

    app.run_polling()

if __name__ == "__main__":
    main()
