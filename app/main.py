from fastapi import FastAPI
from pydantic import BaseModel
import os
import sqlite3
from pathlib import Path
import re
import requests

from google import genai  # google-genai SDK

# ======================
# APP INIT
# ======================

app = FastAPI()

# ======================
# CONFIG
# ======================

DB_PATH = Path(__file__).parent / "data" / "vacancies.db"


class AskRequest(BaseModel):
    text: str


# ======================
# HEALTH & DEBUG
# ======================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug/sample")
def debug_sample():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT position, description FROM vacancies LIMIT 3")
    rows = cur.fetchall()
    conn.close()
    return rows


@app.get("/debug/models")
def debug_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    resp = requests.get(url, params={"key": api_key})

    return {
        "status_code": resp.status_code,
        "response": resp.json()
    }


# ======================
# RAG: SEARCH (SQLite FTS5)
# ======================

def search_vacancies(query: str, limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

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
            model="models/text-bison-001",
            contents=prompt,
        )

        text = getattr(resp, "text", None)
        if not text:
            return {"error": "Empty response from model"}

        return {"answer": text}

    except Exception as e:
        msg = str(e)

        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "404" in msg:
            return {
                "answer": (
                    "Генерация сейчас недоступна, "
                    "но вот подходящие вакансии из базы:\n\n"
                    f"{context}"
                )
            }

        return {"error": msg}
