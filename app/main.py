from fastapi import FastAPI
from pydantic import BaseModel
import os
import sqlite3
from pathlib import Path
import re
import threading
import httpx

from google import genai  # google-genai SDK

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

# ======================
# CONFIG
# ======================

DB_PATH = Path(__file__).parent / "data" / "vacancies.db"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ВАЖНО: бот дергает твой же бэкенд
BACKEND_URL = "https://ai-assiat-bootcamp.onrender.com/ask"

app = FastAPI()


class AskRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    return {"status": "ok"}


# ======================
# RAG: SEARCH (SQLite FTS5)
# ======================

def search_vacancies(query: str, limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # делаем запрос безопаснее для FTS (убираем спецсимволы)
    safe_query = re.sub(r"[^\w\s]", " ", query).strip()
    if not safe_query:
        conn.close()
        return []

    sql = f"""
    SELECT v.*
    FROM vacancies_fts f
    JOIN vacancies v ON v.id = f.rowid
    WHERE vacancies_fts MATCH "{safe_query}"
      AND v.is_active = 1
    LIMIT {int(limit)}
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


# ======================
# API ENDPOINT (/ask)
# ======================

@app.post("/ask")
def ask(req: AskRequest):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    vacancies = search_vacancies(req.text, limit=5)
    context = build_context(vacancies)

    prompt = f"""
Ты — ассистент по поиску вакансий.

Используй ТОЛЬКО информацию ниже.
Если ответа нет в данных — честно скажи, что не знаешь.

ДАННЫЕ:
{context}

ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{req.text}
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        text = getattr(resp, "text", None)
        if not text:
            return {"error": "Empty response from model"}

        return {"answer": text}

    except Exception as e:
        return {"error": str(e)}


# ======================
# TELEGRAM BOT (polling in separate thread)
# ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            BACKEND_URL,
            json={"text": user_text},
            timeout=60
        )

    try:
        data = resp.json()
        answer = data.get("answer") or data.get("error") or "Ошибка 😢"
    except Exception:
        answer = "Ошибка сервера 😢"

    await update.message.reply_text(answer)


def run_telegram_polling():
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set")
        return

    tg_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ВАЖНО: run_polling() сам управляет event loop -> запускаем в отдельном потоке
    tg_app.run_polling(close_loop=False)


@app.on_event("startup")
def on_startup():
    # запускаем бота один раз, в фоне
    t = threading.Thread(target=run_telegram_polling, daemon=True)
    t.start()
