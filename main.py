import os
import requests
from decimal import Decimal
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from db import *

TOKEN = os.getenv("TOKEN")
MASTER_ID = int(os.getenv("MASTER_ID"))

ETHERSCAN_API = os.getenv("ETHERSCAN_API")
BLOCKCYPHER_API = os.getenv("BLOCKCYPHER_API")
TRONGRID_API = os.getenv("TRONGRID_API")
SOLANA_API = "https://api.mainnet-beta.solana.com"





# ================= PRICE =================



def get_price(symbol):
    if symbol == "USDT-ERC20" or symbol == "USDT-TRC20":
        return Decimal(1)

    ids = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana"
    }

    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ids[symbol], "vs_currencies": "usd"}
    r = requests.get(url, params=params).json()
    return Decimal(r[ids[symbol]]["usd"])


# ================= BLOCKCHAIN =================

def get_latest_tx(symbol, address):
    try:
        if symbol == "BTC":
            url = f"https://api.blockcypher.com/v1/btc/main/addrs/{address}"
            r = requests.get(url).json()
            if "txrefs" in r:
                return r["txrefs"][0]

        if symbol in ["ETH", "USDT-ERC20"]:
            url = "https://api.etherscan.io/api"
            action = "tokentx" if symbol == "USDT-ERC20" else "txlist"
            params = {
                "module": "account",
                "action": action,
                "address": address,
                "sort": "desc",
                "apikey": ETHERSCAN_API
            }
            r = requests.get(url, params=params).json()
            if r["status"] == "1":
                return r["result"][0]

        if symbol == "USDT-TRC20":
            url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
            r = requests.get(url).json()
            if "data" in r:
                return r["data"][0]

        if symbol == "SOL":
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [address, {"limit": 1}]
            }
            r = requests.post(SOLANA_API, json=payload).json()
            if "result" in r and r["result"]:
                return r["result"][0]

    except:
        return None

    return None


# ================= AUTH =================

def is_master(user_id):
    return user_id == MASTER_ID


def has_access(user_id):
    return is_master(user_id) or is_admin(user_id)


# ================= COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    user_id = user.id
    chat_id = chat.id
    chat_type = chat.type

    # ตรวจสอบสิทธิ์
    if is_master(user_id):
        role = "👑 MASTER"
    elif is_admin(user_id):
        role = "🛡 ADMIN"
    else:
        role = "❌ ไม่มีสิทธิ์"

    text = f"""
🤖 Crypto Alert Bot

👤 User ID: {user_id}
💬 Chat ID: {chat_id}
🔐 สิทธิ์: {role}

━━━━━━━━━━━━━━━
📘 วิธีใช้งาน

1️⃣ เพิ่มกระเป๋า
/add
→ เลือกเหรียญ
→ ส่งที่อยู่
→ ส่งหมายเหตุ

2️⃣ ดูรายการในกลุ่ม
/list

3️⃣ ลบรายการ
/remove

━━━━━━━━━━━━━━━
👑 คำสั่งมาสเตอร์
/addadmin <user_id>
/removeadmin <user_id>
/admins

⚠️ หมายเหตุ:
• บอทต้องอยู่ในกลุ่ม
• การแจ้งเตือนแยกตาม group
• ไม่แจ้งซ้ำธุรกรรม
• แสดงมูลค่า USD ณ เวลาตรวจพบ
"""

    if role == "❌ ไม่มีสิทธิ์":
        text += "\n\n🚫 คุณยังไม่มีสิทธิ์ใช้งาน กรุณาติดต่อ MASTER"

    await update.message.reply_text(text.strip())


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access(update.effective_user.id):
        return

    coins = ["BTC", "ETH", "SOL", "USDT-ERC20", "USDT-TRC20"]
    keyboard = [[InlineKeyboardButton(c, callback_data=f"coin_{c}")] for c in coins]

    await update.message.reply_text(
        "เลือกเหรียญ:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def coin_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    symbol = query.data.split("_")[1]
    context.user_data["symbol"] = symbol
    await query.edit_message_text("ส่งที่อยู่กระเป๋า:")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "symbol" in context.user_data and "address" not in context.user_data:
        context.user_data["address"] = update.message.text
        await update.message.reply_text("ส่งหมายเหตุ:")
        return

    if "address" in context.user_data:
        group_id = update.effective_chat.id
        add_wallet(
            group_id,
            context.user_data["symbol"],
            context.user_data["address"],
            update.message.text
        )
        context.user_data.clear()
        await update.message.reply_text("เพิ่มสำเร็จ ✅")


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.effective_chat.id
    wallets = get_wallets(group_id)

    # ✅ ถ้าไม่มีรายการ
    if not wallets:
        await update.message.reply_text(
            "📭 ไม่มีรายการที่ติดตามในกลุ่มนี้\n\nใช้ /add เพื่อเพิ่มกระเป๋า"
        )
        return

    # ✅ ถ้ามีรายการ
    text = "📋 รายการที่ติดตามในกลุ่มนี้\n\n"

    for w in wallets:
        text += (
            f"🔹 ID: {w['id']}\n"
            f"เหรียญ: {w['symbol']}\n"
            f"หมายเหตุ: {w['note']}\n"
            f"ที่อยู่: {w['address']}\n\n"
        )

    await update.message.reply_text(text)


async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallets = get_wallets(update.effective_chat.id)

    keyboard = [
        [InlineKeyboardButton(f"{w['symbol']} | {w['note']}", callback_data=f"del_{w['id']}")]
        for w in wallets
    ]

    await update.message.reply_text(
        "เลือกรายการที่ต้องการลบ",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def delete_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    wallet_id = int(query.data.split("_")[1])
    remove_wallet(wallet_id)
    await query.edit_message_text("ลบสำเร็จ ✅")


# ================= ALERT SYSTEM =================

async def check_transactions(context: ContextTypes.DEFAULT_TYPE):
    wallets = get_all_wallets()

    for w in wallets:
        tx = get_latest_tx(w["symbol"], w["address"])
        if not tx:
            continue

        tx_hash = tx.get("hash") or tx.get("tx_hash") or tx.get("signature")

        if tx_hash == w["last_tx_hash"]:
            continue

        price = get_price(w["symbol"])

        amount = Decimal(0)

        if w["symbol"] == "BTC":
            amount = Decimal(tx["value"]) / Decimal(1e8)
        elif w["symbol"] == "ETH":
            amount = Decimal(tx["value"]) / Decimal(1e18)
        elif w["symbol"] == "USDT-ERC20":
            amount = Decimal(tx["value"]) / Decimal(1e6)
        else:
            amount = Decimal(1)

        usd_value = amount * price

        text = f"""
🔔 แจ้งเตือนธุรกรรม

เหรียญ: {w['symbol']}
จำนวน: {amount}
มูลค่า: ${usd_value:.2f}

หมายเหตุ: {w['note']}
"""

        await context.bot.send_message(chat_id=w["group_id"], text=text)

        update_last_tx(w["id"], tx_hash)


# ================= ADMIN =================

async def add_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_master(update.effective_user.id):
        return
    user_id = int(context.args[0])
    add_admin(user_id)
    await update.message.reply_text("เพิ่มแอดมินแล้ว")


async def remove_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_master(update.effective_user.id):
        return
    user_id = int(context.args[0])
    remove_admin(user_id)
    await update.message.reply_text("ลบแอดมินแล้ว")


async def list_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_master(update.effective_user.id):
        return
    admins = get_admins()
    await update.message.reply_text("\n".join(str(a["telegram_id"]) for a in admins))


# ================= MAIN =================

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("addadmin", add_admin_cmd))
    app.add_handler(CommandHandler("removeadmin", remove_admin_cmd))
    app.add_handler(CommandHandler("admins", list_admin_cmd))

    app.add_handler(CallbackQueryHandler(coin_selected, pattern="coin_"))
    app.add_handler(CallbackQueryHandler(delete_wallet, pattern="del_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.job_queue.run_repeating(check_transactions, interval=30)

    app.run_polling()


if __name__ == "__main__":
    main()
