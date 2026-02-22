import os
import asyncio
import requests
from decimal import Decimal
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from db import *

TOKEN = os.getenv("TOKEN")
MASTER_ID = int(os.getenv("MASTER_ID"))
ALCHEMY_KEY = os.getenv("ALCHEMY_KEY")

CHECK_INTERVAL = 30


# ================= Markdown Safe =================

def escape_markdown(text):
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join("\\" + c if c in escape_chars else c for c in text)


# ================= PRICE =================

def get_price(coin):
    coin_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
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


# ================= ETH + ERC20 (Alchemy) =================

def check_eth_alchemy(address, erc20=False):
    url = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}"

    if erc20:
        category = ["erc20"]
    else:
        category = ["external", "internal"]

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

    res = requests.post(url, json=payload).json()
    transfers = res.get("result", {}).get("transfers", [])

    if not transfers:
        return None

    tx = transfers[0]

    txid = tx["hash"]

    # FIXED timestamp (ISO format)
    timestamp = int(
        datetime.fromisoformat(
            tx["metadata"]["blockTimestamp"].replace("Z", "+00:00")
        ).timestamp()
    )

    amount = Decimal(str(tx["value"]))

    return txid, amount, timestamp


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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 监控机器人已启动\n\n"
        "/addbtc 地址\n"
        "/addeth 地址\n"
        "/adderc20 地址\n"
        "/addtrc20 地址\n\n"
        "/removebtc 地址\n"
        "/removeeth 地址\n"
        "/removeerc20 地址\n"
        "/removetrc20 地址\n\n"
        "/list\n"
        "/status"
    )


async def add_coin(update, context, coin):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ 没有权限")
        return

    if len(context.args) != 1:
        await update.message.reply_text("格式错误")
        return

    add_wallet(chat_id, coin, context.args[0])
    await update.message.reply_text("✅ 添加成功")


async def addbtc(update, context): await add_coin(update, context, "BTC")
async def addeth(update, context): await add_coin(update, context, "ETH")
async def adderc20(update, context): await add_coin(update, context, "ERC20")
async def addtrc20(update, context): await add_coin(update, context, "TRC20")


# ================= LIST =================

async def list_wallet(update, context):
    chat_id = update.effective_chat.id
    wallets = [w for w in get_wallets() if w["chat_id"] == chat_id]

    if not wallets:
        await update.message.reply_text("没有 address")
        return

    text = "📋 Wallet List\n\n"

    for w in wallets:
        safe_address = escape_markdown(w["address"])
        text += f"{w['coin']}\n`{safe_address}`\n\n"

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2
    )


# ================= REMOVE =================

async def remove_coin(update, context, coin):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ 没有权限")
        return

    if len(context.args) != 1:
        await update.message.reply_text("格式错误")
        return

    address = context.args[0]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM wallets WHERE chat_id=%s AND coin=%s AND address=%s",
        (chat_id, coin, address)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text("🗑 删除成功")


async def removebtc(update, context): await remove_coin(update, context, "BTC")
async def removeeth(update, context): await remove_coin(update, context, "ETH")
async def removeerc20(update, context): await remove_coin(update, context, "ERC20")
async def removetrc20(update, context): await remove_coin(update, context, "TRC20")


# ================= STATUS =================

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_admin(chat_id, user_id, MASTER_ID):
        await update.message.reply_text("⛔ 没有权限")
        return

    wallets = [w for w in get_wallets() if w["chat_id"] == chat_id]

    text = (
        "📊 系统状态\n\n"
        "🤖 Bot: Online\n"
        f"⏱ 检测间隔: {CHECK_INTERVAL} 秒\n"
        f"📦 当前监控地址: {len(wallets)} 个"
    )

    await update.message.reply_text(text)


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
                    result = check_eth_alchemy(address)

                elif coin == "ERC20":
                    result = check_eth_alchemy(address, erc20=True)

                elif coin == "TRC20":
                    result = check_trc20(address)

                else:
                    continue

                if not result:
                    continue

                txid, amount, timestamp = result

                if already_notified(chat_id, txid):
                    continue

                safe_address = escape_markdown(address)

                if coin in ["BTC", "ETH"]:
                    price = get_price(coin)
                    total = amount * price

                    text = (
                        "🚨 出金\n\n"
                        f"币种 | {coin}\n"
                        f"数量 | {amount:.6f}\n"
                        f"金额 | {total:,.2f} 美金\n"
                        f"客户地址 | `{safe_address}`"
                    )

                elif coin == "ERC20":
                    text = (
                        "🚨 出金\n\n"
                        "币种 | ERC20\n"
                        f"数量 | {amount:.2f}\n"
                        f"金额 | {amount:,.2f} 美金\n"
                        f"客户地址 | `{safe_address}`"
                    )

                elif coin == "TRC20":
                    text = (
                        "🚨 出金\n\n"
                        "币种 | TRC20\n"
                        f"数量 | {amount:.2f}\n"
                        f"金额 | {amount:,.2f} 美金\n"
                        f"客户地址 | `{safe_address}`"
                    )

                await app.bot.send_message(
                    chat_id,
                    text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )

                mark_notified(chat_id, txid)

            except Exception as e:
                print("Error:", e)

        await asyncio.sleep(CHECK_INTERVAL)

# ================= MASTER COMMANDS =================

async def master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ID:
        return

    await update.message.reply_text(
        "👑 Master 控制面板\n\n"
        "/addadmin 用户ID\n"
        "/deladmin 用户ID\n"
        "/adminlist\n\n"
        "你拥有所有权限"
    )


async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ID:
        await update.message.reply_text("⛔ 只有 Master 可以使用")
        return

    if len(context.args) != 1:
        await update.message.reply_text("格式: /addadmin 用户ID")
        return

    user_id = int(context.args[0])
    add_admin(update.effective_chat.id, user_id)
    await update.message.reply_text("✅ 添加管理员成功")


async def deladmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ID:
        await update.message.reply_text("⛔ 只有 Master 可以使用")
        return

    if len(context.args) != 1:
        await update.message.reply_text("格式: /deladmin 用户ID")
        return

    user_id = int(context.args[0])
    remove_admin(update.effective_chat.id, user_id)
    await update.message.reply_text("🗑 删除管理员成功")


async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ID:
        return

    admins = get_admins(update.effective_chat.id)

    if not admins:
        await update.message.reply_text("没有管理员")
        return

    text = "👑 管理员列表:\n"
    for a in admins:
        text += f"{a[0]}\n"

    await update.message.reply_text(text)


# ================= MAIN =================

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addbtc", addbtc))
    app.add_handler(CommandHandler("addeth", addeth))
    app.add_handler(CommandHandler("adderc20", adderc20))
    app.add_handler(CommandHandler("addtrc20", addtrc20))
    app.add_handler(CommandHandler("removebtc", removebtc))
    app.add_handler(CommandHandler("removeeth", removeeth))
    app.add_handler(CommandHandler("removeerc20", removeerc20))
    app.add_handler(CommandHandler("removetrc20", removetrc20))
    app.add_handler(CommandHandler("list", list_wallet))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("master", master))
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("deladmin", deladmin))
    app.add_handler(CommandHandler("adminlist", adminlist))

    async def post_init(app):
        app.create_task(auto_check(app))

    app.post_init = post_init
    app.run_polling()


if __name__ == "__main__":
    main()
