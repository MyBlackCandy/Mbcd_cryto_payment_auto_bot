import os
import asyncio
import requests
from decimal import Decimal
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from telegram.constants import ParseMode
from db import *

TOKEN = os.getenv("TOKEN")
MASTER_ID = int(os.getenv("MASTER_ID", "0"))
ALCHEMY_KEY = os.getenv("ALCHEMY_KEY")
CHECK_INTERVAL = 30


# ================== UTIL ==================
def escape_md(text):
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!`"
    return "".join("\\" + c if c in escape_chars else c for c in text)


# ================== CHECK FUNCTIONS ==================
def check_eth_withdraw(address):
    try:
        url = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}"
        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [{
                "fromBlock": "0x0",
                "toBlock": "latest",
                "fromAddress": address,
                "category": ["external"],
                "maxCount": "0x3",
                "order": "desc"
            }],
            "id": 1
        }
        res = requests.post(url, json=payload, timeout=10).json()
        transfers = res.get("result", {}).get("transfers", [])
        if not transfers:
            return None
        tx = transfers[0]
        return tx["hash"], Decimal(str(tx["value"]))
    except:
        return None


# ================== ADD FLOW ==================
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id,
                    update.effective_user.id,
                    MASTER_ID):
        await update.message.reply_text("⛔ 没有权限")
        return

    context.user_data.clear()
    context.user_data["flow"] = "add"

    keyboard = [
        [InlineKeyboardButton("🟡 BTC", callback_data="addcoin_BTC"),
         InlineKeyboardButton("🔵 ETH", callback_data="addcoin_ETH")],
        [InlineKeyboardButton("🟢 ERC20", callback_data="addcoin_ERC20"),
         InlineKeyboardButton("🔴 TRC20", callback_data="addcoin_TRC20")],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel")]
    ]

    await update.message.reply_text(
        "请选择币种",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def add_select_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    coin = query.data.replace("addcoin_", "")

    # 🔥 สำคัญ
    context.user_data["flow"] = "add"
    context.user_data["coin"] = coin
    context.user_data["step"] = "address"

    await query.message.reply_text(f"请输入 {coin} 地址")


async def add_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if context.user_data.get("flow") != "add":
        return

    step = context.user_data.get("step")

    # ---------- รับ address ----------
    if step == "address":
        context.user_data["address"] = update.message.text.strip()
        context.user_data["step"] = "note"

        await update.message.reply_text("请输入备注 (发送 - 跳过)")
        return

    # ---------- รับ note ----------
    if step == "note":

        note = update.message.text.strip()
        if note == "-":
            note = ""

        chat_id = update.effective_chat.id
        coin = context.user_data["coin"]
        address = context.user_data["address"]

        add_wallet(chat_id, coin, address, note)

        await update.message.reply_text(
            f"✅ 添加成功\n"
            f"币种: {coin}\n"
            f"备注: {escape_md(note)}\n"
            f"地址: `{address}`",
            parse_mode=ParseMode.MARKDOWN
        )

        context.user_data.clear()


# ================== CANCEL ==================
async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.reply_text("❌ 已取消操作")


# ================== REMOVE FLOW ==================
async def remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id,
                    update.effective_user.id,
                    MASTER_ID):
        await update.message.reply_text("⛔ 没有权限")
        return

    wallets = get_wallets(update.effective_chat.id)

    if not wallets:
        await update.message.reply_text("暂无地址")
        return

    context.user_data.clear()
    context.user_data["flow"] = "remove"

    keyboard = []
    for w in wallets:
        keyboard.append([
            InlineKeyboardButton(
                f"{w['coin']} | {w['note'] or ''}",
                callback_data=f"remove_{w['coin']}|{w['address']}"
            )
        ])

    keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="cancel")])

    await update.message.reply_text(
        "请选择要删除的地址",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def remove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.replace("remove_", "")
    coin, address = data.split("|", 1)
    chat_id = query.message.chat.id

    delete_wallet(chat_id, coin, address)

    await query.message.reply_text("🗑 删除成功")
    context.user_data.clear()


# ================== LIST ==================
async def list_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallets = get_wallets(update.effective_chat.id)

    if not wallets:
        await update.message.reply_text("暂无地址")
        return

    text = "📋 当前监控列表\n\n"

    for w in wallets:
        text += (
            f"币种: {w['coin']}\n"
            f"备注: {escape_md(w['note'])}\n"
            f"地址: `{w['address']}`\n\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

def update_last_txid(chat_id, coin, address, txid):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE wallets
                SET last_txid=%s
                WHERE chat_id=%s AND coin=%s AND address=%s
                """,
                (txid, chat_id, coin, address)
            )
        conn.commit()
    finally:
        put_conn(conn)


def get_last_txid(chat_id, address):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_txid FROM wallets WHERE chat_id=%s AND address=%s",
                (chat_id, address)
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        put_conn(conn)


# ================== ADMIN ==================
async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ID:
        return
    user_id = int(context.args[0])
    add_admin(update.effective_chat.id, user_id)
    await update.message.reply_text("✅ 添加管理员成功")


async def deladmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ID:
        return
    user_id = int(context.args[0])
    remove_admin(update.effective_chat.id, user_id)
    await update.message.reply_text("🗑 删除管理员成功")


async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = get_admins(update.effective_chat.id)
    if not admins:
        await update.message.reply_text("暂无管理员")
        return

    text = "👑 管理员列表\n\n"
    for a in admins:
        text += f"{a}\n"

    await update.message.reply_text(text)


# ================== CHECK FUNCTIONS ==================

def check_btc_withdraw(address):
    try:
        url = f"https://blockstream.info/api/address/{address}/txs?limit=3"
        data = requests.get(url, timeout=10).json()

        for tx in data:
            for vin in tx.get("vin", []):
                prev = vin.get("prevout", {})
                if prev.get("scriptpubkey_address") == address:
                    amount = Decimal(prev.get("value", 0)) / Decimal(100000000)
                    return tx["txid"], amount
    except:
        return None
    return None


def check_eth_withdraw(address):
    try:
        url = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}"
        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [{
                "fromBlock": "0x0",
                "toBlock": "latest",
                "fromAddress": address,
                "category": ["external"],
                "maxCount": "0x3",
                "order": "desc"
            }],
            "id": 1
        }

        res = requests.post(url, json=payload, timeout=10).json()
        transfers = res.get("result", {}).get("transfers", [])
        if not transfers:
            return None

        tx = transfers[0]
        return tx["hash"], Decimal(str(tx["value"]))
    except:
        return None


def check_erc20_withdraw(address):
    try:
        url = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}"
        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [{
                "fromBlock": "0x0",
                "toBlock": "latest",
                "fromAddress": address,
                "category": ["erc20"],
                "maxCount": "0x3",
                "order": "desc"
            }],
            "id": 1
        }

        res = requests.post(url, json=payload, timeout=10).json()
        transfers = res.get("result", {}).get("transfers", [])
        if not transfers:
            return None

        tx = transfers[0]
        amount = Decimal(str(tx["value"]))
        symbol = tx.get("asset", "TOKEN")
        return tx["hash"], f"{amount} {symbol}"
    except:
        return None


def check_trc20_withdraw(address):
    try:
        url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?limit=3"
        res = requests.get(url, timeout=10).json()

        for tx in res.get("data", []):
            if tx.get("from", "").lower() == address.lower():
                amount = Decimal(tx["value"]) / Decimal(10**6)
                return tx["transaction_id"], amount
    except:
        return None
    return None


# ================== AUTO CHECK ==================
async def auto_check(app):

    while True:

        wallets = get_all_wallets()

        for w in wallets:

            coin = w["coin"]
            address = w["address"]
            chat_id = w["chat_id"]

            # ---------------- เลือก chain ----------------
            if coin == "BTC":
                result = check_btc_withdraw(address)

            elif coin == "ETH":
                result = check_eth_withdraw(address)

            elif coin == "ERC20":
                result = check_erc20_withdraw(address)

            elif coin == "TRC20":
                result = check_trc20_withdraw(address)

            else:
                continue

            if not result:
                continue

            txid, amount = result

            # ---------------- กันแจ้งซ้ำ ----------------
            if is_notified(chat_id, txid):
                continue

            # ---------------- คำนวณ USD ----------------
            usd_text = ""

            if isinstance(amount, str):
                # ERC20 แบบมี symbol เช่น 100 USDT
                try:
                    value, token = amount.split()
                    value = Decimal(value)

                    if token.upper() in ["USDT", "USDC"]:
                        usd_value = value
                        usd_text = f"\n💲 价值: ${usd_value:.2f}"
                    else:
                        usd_text = ""
                except:
                    pass
            else:
                price = get_price_usd(coin)
                if price:
                    usd_value = amount * price
                    usd_text = f"\n💲 价值: ${usd_value:.2f}"

            # ---------------- ส่งข้อความ ----------------
            await app.bot.send_message(
                chat_id,
                f"🚨 新交易通知\n\n"
                f"币种: {coin}\n"
                f"数量: {amount}"
                f"{usd_text}\n"
                f"地址: `{address}`",
                parse_mode=ParseMode.MARKDOWN
            )

            # ---------------- บันทึกลง DB ----------------
            mark_notified(chat_id, txid)

        await asyncio.sleep(CHECK_INTERVAL)



async def startup(app):

    print("🚀 Bot started")

    try:
        wallets = get_all_wallets()

        # ดึง chat_id ไม่ให้ซ้ำ
        chat_ids = list(set(w["chat_id"] for w in wallets))

        for chat_id in chat_ids:
            try:
                await app.bot.send_message(
                    chat_id,
                    "机器人可使用"
                )
            except Exception as e:
                print(f"Notify error {chat_id}:", e)

    except Exception as e:
        print("Startup notify error:", e)

    asyncio.create_task(auto_check(app))

# ================== PRICE ==================
def get_price_usd(symbol):
    try:
        mapping = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "TRC20": "tron"
        }

        if symbol == "ERC20":
            return None  # ERC20 จะดึงจาก token symbol แยก

        coin_id = mapping.get(symbol)
        if not coin_id:
            return None

        url = "https://api.coingecko.com/api/v3/simple/price"
        res = requests.get(url, params={
            "ids": coin_id,
            "vs_currencies": "usd"
        }, timeout=10).json()

        return Decimal(str(res[coin_id]["usd"]))

    except:
        return None

# ================== MAIN ==================
def main():
    init_pool()
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("add", add_start))
    app.add_handler(CommandHandler("remove", remove_start))
    app.add_handler(CommandHandler("list", list_wallet))
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("deladmin", deladmin))
    app.add_handler(CommandHandler("adminlist", adminlist))

    app.add_handler(CallbackQueryHandler(add_select_coin, pattern="^addcoin_"))
    app.add_handler(CallbackQueryHandler(remove_confirm, pattern="^remove_"))
    app.add_handler(CallbackQueryHandler(cancel_flow, pattern="^cancel$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_flow))

    async def startup(app):
        asyncio.create_task(auto_check(app))


    app.post_init = startup
    app.run_polling()


if __name__ == "__main__":
    main()
