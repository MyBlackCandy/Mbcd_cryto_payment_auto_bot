# ================== IMPORT ==================
import os
import asyncio
import requests
from decimal import Decimal
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode
from db import *

# ================== ENV ==================
TOKEN = os.getenv("TOKEN")
MASTER_ID = int(os.getenv("MASTER_ID", "0"))
ALCHEMY_KEY = os.getenv("ALCHEMY_KEY")
CHECK_INTERVAL = 30

print("TOKEN loaded:", bool(TOKEN))
print("MASTER_ID:", MASTER_ID)
print("ALCHEMY_KEY loaded:", bool(ALCHEMY_KEY))

# ================== UTIL ==================
def escape_markdown(text):
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join("\\" + c if c in escape_chars else c for c in text)

def get_price(coin):
    coin_map = {"BTC": "bitcoin", "ETH": "ethereum"}
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_map[coin]}&vs_currencies=usd"
    data = requests.get(url).json()
    return Decimal(str(list(data.values())[0]["usd"]))

# ================== CHAIN ==================
def check_btc(address):
    try:
        data = requests.get(
            f"https://blockstream.info/api/address/{address}/txs",
            timeout=10
        ).json()

        for tx in data[:5]:
            for vin in tx["vin"]:
                if vin.get("prevout", {}).get("scriptpubkey_address") == address:
                    amount = Decimal(tx["vout"][0]["value"]) / Decimal(100000000)
                    return tx["txid"], amount, tx["status"]["block_time"]
    except:
        return None
    return None

def check_eth_alchemy(address, erc20=False):
    if not ALCHEMY_KEY:
        return None

    try:
        url = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}"
        category = ["erc20"] if erc20 else ["external", "internal"]

        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [{
                "fromBlock": "0x0",
                "toBlock": "latest",
                "fromAddress": address,
                "category": category,
                "withMetadata": True,
                "maxCount": "0x5",
                "order": "desc"
            }],
            "id": 1
        }

        res = requests.post(url, json=payload, timeout=10).json()
        transfers = res.get("result", {}).get("transfers", [])
        if not transfers:
            return None

        tx = transfers[0]
        txid = tx["hash"]
        timestamp = int(datetime.fromisoformat(
            tx["metadata"]["blockTimestamp"].replace("Z", "+00:00")
        ).timestamp())
        amount = Decimal(str(tx["value"]))

        return txid, amount, timestamp
    except:
        return None

def check_trc20(address):
    try:
        url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
        res = requests.get(url, timeout=10).json()
        if "data" not in res:
            return None

        for tx in res["data"][:5]:
            if tx["from"].lower() == address.lower():
                return (
                    tx["transaction_id"],
                    Decimal(tx["value"]) / Decimal(10**6),
                    int(tx["block_timestamp"] / 1000)
                )
    except:
        return None
    return None

# ================== ADD FLOW ==================
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🟡 BTC", callback_data="coin_BTC"),
         InlineKeyboardButton("🔵 ETH", callback_data="coin_ETH")],
        [InlineKeyboardButton("🟢 ERC20", callback_data="coin_ERC20"),
         InlineKeyboardButton("🔴 TRC20", callback_data="coin_TRC20")],
        [InlineKeyboardButton("❌ 取消", callback_data="add_cancel")]
    ]

    context.user_data["add_step"] = "select_coin"

    await update.message.reply_text(
        "请选择币种",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_select_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["add_coin"] = query.data.replace("coin_", "")
    context.user_data["add_step"] = "address"

    keyboard = [[InlineKeyboardButton("❌ 取消", callback_data="add_cancel")]]

    await query.message.reply_text(
        "请输入地址",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "add_step" not in context.user_data:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ 没有权限")
        context.user_data.clear()
        return

    step = context.user_data["add_step"]

    if step == "address":
        context.user_data["add_address"] = update.message.text.strip()
        context.user_data["add_step"] = "note"

        keyboard = [[InlineKeyboardButton("❌ 取消", callback_data="add_cancel")]]

        await update.message.reply_text(
            "请输入备注 (发送 - 跳过)",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        note = update.message.text.strip()
        if note == "-":
            note = None

        add_wallet(
            chat_id,
            context.user_data["add_coin"],
            context.user_data["add_address"],
            note
        )

        await update.message.reply_text("✅ 添加成功")
        context.user_data.clear()

async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.reply_text("❌ 已取消")

# ================== AUTO CHECK ==================
async def auto_check(app):
    print("Auto check started")

    while True:
        wallets = get_wallets()

        for w in wallets:
            chat_id = w["chat_id"]
            coin = w["coin"]
            address = w["address"]
            note = w.get("note")

            if coin == "BTC":
                result = check_btc(address)
            elif coin == "ETH":
                result = check_eth_alchemy(address)
            elif coin == "ERC20":
                result = check_eth_alchemy(address, True)
            elif coin == "TRC20":
                result = check_trc20(address)
            else:
                continue

            if not result:
                continue

            txid, amount, _ = result

            if already_notified(chat_id, txid):
                continue

            note_text = f"备注 | {escape_markdown(note)}\n" if note else ""

            text = (
                f"🚨 出金\n\n"
                f"币种 | {coin}\n"
                f"{note_text}"
                f"数量 | {amount}\n"
                f"客户地址 | `{escape_markdown(address)}`"
            )

            await app.bot.send_message(
                chat_id,
                text,
                parse_mode=ParseMode.MARKDOWN_V2
            )

            mark_notified(chat_id, txid)

        await asyncio.sleep(CHECK_INTERVAL)

# ================== remove FLOW ==================
async def remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id, update.effective_user.id, MASTER_ID):
        await update.message.reply_text("⛔ 没有权限")
        return

    keyboard = [
        [InlineKeyboardButton("🟡 BTC", callback_data="rmcoin_BTC")],
        [InlineKeyboardButton("🔵 ETH", callback_data="rmcoin_ETH")],
        [InlineKeyboardButton("🟢 ERC20", callback_data="rmcoin_ERC20")],
        [InlineKeyboardButton("🔴 TRC20", callback_data="rmcoin_TRC20")],
        [InlineKeyboardButton("❌ 取消", callback_data="rm_cancel")]
    ]

    await update.message.reply_text(
        "请选择币种",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def remove_select_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    coin = query.data.replace("rmcoin_", "")
    chat_id = query.message.chat.id

    wallets = [
        w for w in get_wallets()
        if w["chat_id"] == chat_id and w["coin"] == coin
    ]

    if not wallets:
        await query.message.reply_text("没有地址")
        return

    keyboard = []

    for w in wallets:
        short = w["address"][:10] + "..."
        keyboard.append([
            InlineKeyboardButton(
                short,
                callback_data=f"rmaddr_{coin}_{w['address']}"
            )
        ])

    keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="rm_cancel")])

    await query.message.reply_text(
        "请选择要删除的地址",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
async def remove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, coin, address = query.data.split("_", 2)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM wallets WHERE chat_id=%s AND coin=%s AND address=%s",
        (query.message.chat.id, coin, address)
    )
    conn.commit()
    conn.close()

    await query.message.reply_text("🗑 删除成功")

async def remove_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("❌ 已取消")

# ================== TEST ==================
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ 没有权限")
        return

    text = "🧪 系统检测...\n\n"

    try:
        conn = get_conn()
        conn.close()
        text += "🗄 Database: ✅\n"
    except Exception as e:
        text += f"🗄 Database: ❌ {e}\n"

    try:
        me = await context.bot.get_me()
        text += f"🤖 Bot: ✅ {me.username}\n"
    except Exception as e:
        text += f"🤖 Bot: ❌ {e}\n"

    await update.message.reply_text(text)


# ================== list ==================
async def list_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        wallets = get_wallets()

        # กรองเฉพาะกลุ่มนี้
        wallets = [w for w in wallets if w["chat_id"] == chat_id]

        if not wallets:
            await update.message.reply_text("没有 address")
            return

        # เรียงเหรียญตามลำดับ
        coin_order = ["BTC", "ETH", "ERC20", "TRC20"]

        grouped = {}
        for w in wallets:
            grouped.setdefault(w["coin"], []).append(w)

        text = "📋 当前群监控地址\n\n"

        for coin in coin_order:
            if coin not in grouped:
                continue

            text += f"{coin}\n"

            for w in grouped[coin]:
                note = w.get("note") or "未备注"
                address = w["address"]

                # ไม่ต้อง escape address เพราะใช้ backtick
                text += f"{note} | `{address}`\n"

            text += "\n"

        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        print("LIST ERROR:", e)
        await update.message.reply_text("list 出错")

# ================== MAIN ==================
def main():
    print("Starting application...")

    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("add", add_start))
    app.add_handler(CallbackQueryHandler(add_select_coin, pattern="^coin_"))
    app.add_handler(CallbackQueryHandler(add_cancel, pattern="^add_cancel$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_flow))
    app.add_handler(CommandHandler("test", test))

    app.add_handler(CommandHandler("remove", remove_start))
    app.add_handler(CallbackQueryHandler(remove_select_coin, pattern="^rmcoin_"))
    app.add_handler(CallbackQueryHandler(remove_confirm, pattern="^rmaddr_"))
    app.add_handler(CallbackQueryHandler(remove_cancel, pattern="^rm_cancel$"))

    app.add_handler(CommandHandler("list", list_wallet))

    
    async def startup(app):
        print("Bot polling started")
        asyncio.create_task(auto_check(app))

    app.post_init = startup

    app.run_polling()

if __name__ == "__main__":
    main()
