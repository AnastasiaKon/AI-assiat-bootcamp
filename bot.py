import os
import httpx
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL")  # например https://ai-assiat-bootcamp.onrender.com/ask


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            BACKEND_URL,
            json={"text": text},
            timeout=60
        )

    try:
        data = resp.json()
        answer = data.get("answer") or data.get("error") or "Ошибка 😢"
    except Exception:
        answer = "Ошибка сервера 😢"

    await update.message.reply_text(answer)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
