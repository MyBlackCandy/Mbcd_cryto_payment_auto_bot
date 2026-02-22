import os
import asyncio
import requests
from decimal import Decimal
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from db import *

TOKEN = os.getenv("TOKEN")
MASTER_ID = int(os.getenv("MASTER_ID"))
ETHERSCAN_KEY = os.getenv("ETHERSCAN_KEY")

CHECK_INTERVAL = 30

# ================= PRICE =================

def get_price(coin):
    coin_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "USDT": "tether",
        "TRC20": "tether"
    }
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_map[coin]}&vs_currencies=usd"
    data = requests.get(url).json()
    return Decimal(str(list(data.values())[0]["usd"]))

# ================= BTC =================

def check_btc(address):
    data = requests.get(
        f"https://blockstream.info/api/address/{address}/txs"
    ).json()

    for tx in data[:5]:
        for vin in tx["vin"]:
            if vin.get("prevout", {}).get("scriptpubkey_address") == address:
                amount = Decimal(tx["vout"][0]["value"]) / Decimal(100000000)
                return tx["txid"], amount, tx["status"]["block_time"]
    return None

# ================= ETH / ERC20 =================

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

# ================= TRC20 =================

def check_trc20(address):
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
    res = requests.get(url).json()

    if "data" not in res:
        return None

    for tx in res["data"][:5]:
        if tx["from"].lower() == address.lower():
            txid = tx["transaction_id"]
            amount = Decimal(tx["value"]) / Decimal(10**6)
            timestamp = int(tx["block_timestamp"] / 1000)
            return txid, amount, timestamp
    return None

# ================= COMMANDS =================

async def add_coin(update, context, coin):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ Admin เท่านั้น")
        return

    if len(context.args) != 1:
        await update.message.reply_text(f"ใช้: /add{coin.lower()} address")
        return

    add_wallet(chat_id, coin, context.args[0])
    await update.message.reply_text(f"✅ เพิ่ม {coin} สำเร็จ")

async def addbtc(update, context): await add_coin(update, context, "BTC")
async def addeth(update, context): await add_coin(update, context, "ETH")
async def adderc20(update, context): await add_coin(update, context, "USDT")
async def addtrc20(update, context): await add_coin(update, context, "TRC20")

async def remove(update, context):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ Admin เท่านั้น")
        return

    remove_wallet(chat_id, context.args[0])
    await update.message.reply_text("🗑 ลบสำเร็จ")

async def list_wallet(update, context):
    chat_id = update.effective_chat.id
    wallets = [w for w in get_wallets() if w["chat_id"] == chat_id]

    if not wallets:
        await update.message.reply_text("ไม่มี address")
        return

    text = "📋 Wallets\n"
    for w in wallets:
        text += f"{w['coin']} → {w['address']}\n"

    await update.message.reply_text(text)

async def setadmin(update, context):
    if update.effective_user.id != MASTER_ID:
        await update.message.reply_text("⛔ Master เท่านั้น")
        return

    add_admin(update.effective_chat.id, int(context.args[0]))
    await update.message.reply_text("👑 ตั้ง admin สำเร็จ")

# ================= AUTO LOOP =================

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
                elif coin == "USDT":
                    result = check_eth(address, token=True)
                elif coin == "TRC20":
                    result = check_trc20(address)
                else:
                    continue

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

# ================= MAIN =================

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("addbtc", addbtc))
    app.add_handler(CommandHandler("addeth", addeth))
    app.add_handler(CommandHandler("adderc20", adderc20))
    app.add_handler(CommandHandler("addtrc20", addtrc20))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("list", list_wallet))
    app.add_handler(CommandHandler("setadmin", setadmin))

    async def start_background(app):
        asyncio.create_task(auto_check(app))

    app.post_init = start_background

    app.run_polling()
