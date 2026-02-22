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

    context.user_data["flow"] = "add"
    context.user_data["coin"] = coin
    context.user_data["step"] = "address"

    await query.message.reply_text(f"请输入 {coin} 地址")


async def add_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if context.user_data.get("flow") != "add":
        return

    step = context.user_data.get("step")

    if step == "address":
        context.user_data["address"] = update.message.text.strip()
        context.user_data["step"] = "note"
        await update.message.reply_text("请输入备注 (发送 - 跳过)")
        return

    if step == "note":
        note = update.message.text.strip()
        if note == "-":
            note = ""

        chat_id = update.effective_chat.id
        coin = context.user_data["coin"]
        address = context.user_data["address"]

        add_wallet(chat_id, coin, address, note)

        await update.message.reply_text(
            f"✅ 添加成功\n\n"
            f"币种: {coin}\n"
            f"备注: {escape_md(note)}\n"
            f"地址: `{address}`",
            parse_mode=ParseMode.MARKDOWN
        )

        context.user_data.clear()


# ================== REMOVE ==================
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

    delete_wallet(query.message.chat.id, address)

    await query.message.reply_text("🗑 删除成功")


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


# ================== PRICE ==================
def get_price_usd(symbol):
    try:
        mapping = {
            "BTC": "bitcoin",
            "ETH": "ethereum"
        }

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


# ================== AUTO CHECK ==================
async def auto_check(app):

    while True:

        wallets = get_all_wallets()

        for w in wallets:

            coin = w["coin"]
            address = w["address"]
            chat_id = w["chat_id"]
            note = w.get("note") or ""

            result = None

            if coin == "BTC":
                result = check_btc_withdraw(address)
            elif coin == "ETH":
                result = check_eth_withdraw(address)
            elif coin == "ERC20":
                result = check_erc20_withdraw(address)
            elif coin == "TRC20":
                result = check_trc20_withdraw(address)

            if not result:
                continue

            txid, amount = result

            if is_notified(chat_id, txid):
                continue

            usd_text = ""

            if coin in ["BTC", "ETH"] and not isinstance(amount, str):
                price = get_price_usd(coin)
                if price:
                    usd_value = amount * price
                    usd_text = f"\n💲 价值: ${usd_value:.2f}"

            elif coin in ["ERC20", "TRC20"]:
                if isinstance(amount, str):
                    value, _ = amount.split()
                    usd_value = Decimal(value)
                else:
                    usd_value = Decimal(amount)

                usd_text = f"\n💲 价值: ${usd_value:.2f}"

            note_text = f"备注: {escape_md(note)}\n" if note else ""

            await app.bot.send_message(
                chat_id,
                f"🚨 新交易通知\n\n"
                f"{note_text}"
                f"币种: {coin}\n"
                f"数量: {amount}"
                f"{usd_text}\n"
                f"地址: `{address}`",
                parse_mode=ParseMode.MARKDOWN
            )

            mark_notified(chat_id, txid)

        await asyncio.sleep(CHECK_INTERVAL)


# ================== STARTUP ==================
async def startup(app):

    wallets = get_all_wallets()
    chat_ids = list(set(w["chat_id"] for w in wallets))

    for chat_id in chat_ids:
        try:
            await app.bot.send_message(chat_id, "机器人可使用")
        except:
            pass

    asyncio.create_task(auto_check(app))


# ================== MAIN ==================
def main():
    init_pool()
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("add", add_start))
    app.add_handler(CommandHandler("remove", remove_start))
    app.add_handler(CommandHandler("list", list_wallet))

    app.add_handler(CallbackQueryHandler(add_select_coin, pattern="^addcoin_"))
    app.add_handler(CallbackQueryHandler(remove_confirm, pattern="^remove_"))
    app.add_handler(CallbackQueryHandler(cancel_flow, pattern="^cancel$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_flow))

    app.post_init = startup
    app.run_polling()


if __name__ == "__main__":
    main()
