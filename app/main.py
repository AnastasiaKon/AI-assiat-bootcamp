from fastapi import FastAPI
from pydantic import BaseModel
import os
from google import genai
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "vacancies.db"


app = FastAPI()

class AskRequest(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"status": "ok"}

def search_vacancies(query: str, limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # простая очистка запроса для FTS
    safe_query = query.replace('"', "").replace("'", "")

    sql = f"""
    SELECT v.*
    FROM vacancies_fts f
    JOIN vacancies v ON v.id = f.rowid
    WHERE vacancies_fts MATCH "{safe_query}"
      AND v.is_active = 1
    LIMIT {limit}
    """

    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()

    return rows

    
def build_context(vacancies):
    if not vacancies:
        return "Подходящих вакансий не найдено."

    blocks = []
    for v in vacancies:
        block = f"""
Вакансия: {v['position']}
Компания: {v['company']}
Город: {v['city']}
Стек: {v['stack']}
Описание: {v['description']}
Зарплата: {v['salary']}
"""
        blocks.append(block.strip())

    return "\n\n---\n\n".join(blocks)


@app.post("/ask")
def ask(req: AskRequest):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    # 1. Retrieval
    vacancies = search_vacancies(req.text, limit=5)
    context = build_context(vacancies)

    genai.configure(api_key=api_key)

    prompt = f"""
Ты — ассистент по поиску вакансий.

Используй ТОЛЬКО информацию ниже.
Если ответа нет в данных — честно скажи, что не знаешь.

ДАННЫЕ:
{context}

ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{req.text}
"""

    try:
        model = genai.GenerativeModel("models/gemini-pro")
        response = model.generate_content(prompt)

        if not response or not response.text:
            return {"error": "Empty response from model"}

        return {"answer": response.text}

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

