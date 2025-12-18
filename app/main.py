from fastapi import FastAPI
from pydantic import BaseModel
import os
from google import genai

app = FastAPI()

class AskRequest(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ask")
async def ask(req: AskRequest):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    try:
        client = genai.Client(api_key=api_key)

        # актуальный стиль вызова из документации
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=req.text,
        )

        # на всякий случай: если ответ пустой/нестандартный
        text = getattr(resp, "text", None)
        if not text:
            return {"error": "Empty response", "raw": str(resp)}

        return {"answer": text}

    except Exception as e:
        return {"error": str(e)}

import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import httpx

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BACKEND_URL = "https://ai-assiat-bootcamp.onrender.com/ask"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            BACKEND_URL,
            json={"text": user_text},
            timeout=60
        )

    data = resp.json()
    answer = data.get("answer", "Ошибка 😢")

    await update.message.reply_text(answer)


async def start_bot():
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.start()
    await app.bot.initialize()
    await app.updater.start_polling()


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(start_bot())

