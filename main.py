import os
from decimal import Decimal
from telegram.ext import (
    Application, CommandHandler,
    ContextTypes
)
from db import *
from blockchain import *

TOKEN = os.getenv("TOKEN")

async def add_cmd(update, context):
    if len(context.args) != 2:
        await update.message.reply_text("ใช้: /add chain address")
        return

    chain = context.args[0].upper()
    address = context.args[1]

    add_wallet(update.effective_chat.id, chain, address)
    await update.message.reply_text("เพิ่มสำเร็จ ✅")

async def remove_cmd(update, context):
    if len(context.args) != 2:
        await update.message.reply_text("ใช้: /remove chain address")
        return

    chain = context.args[0].upper()
    address = context.args[1]

    remove_wallet(update.effective_chat.id, chain, address)
    await update.message.reply_text("ลบสำเร็จ ✅")

async def list_cmd(update, context):
    wallets = get_wallets(update.effective_chat.id)

    if not wallets:
        await update.message.reply_text("ไม่มีรายการ")
        return

    text = ""
    for w in wallets:
        text += f"{w['chain']} - {w['address']}\n"

    await update.message.reply_text(text)

async def check_transactions(context: ContextTypes.DEFAULT_TYPE):
    wallets = get_all_wallets()

    for w in wallets:
        tx_hash, amount = get_latest_tx(w["chain"], w["address"])

        if not tx_hash:
            continue

        if tx_hash == w["last_tx_hash"]:
            continue

        price = get_price(w["chain"])
        usd = amount * price if amount else Decimal(0)

        msg = f"""
🔔 {w['chain']} ALERT
จำนวน: {amount}
≈ ${usd:.2f}

TX:
{tx_hash}
"""

        await context.bot.send_message(
            chat_id=w["chat_id"],
            text=msg.strip()
        )

        update_last_tx(w["id"], tx_hash)

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("remove", remove_cmd))
    app.add_handler(CommandHandler("list", list_cmd))

    app.job_queue.run_repeating(check_transactions, interval=30)

    app.run_polling()

if __name__ == "__main__":
    main()
