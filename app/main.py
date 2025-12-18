from fastapi import FastAPI
from pydantic import BaseModel
import os
import sqlite3
from pathlib import Path
import re
import uuid

from google import genai  # google-genai SDK

import matplotlib.pyplot as plt


# ======================
# CONFIG
# ======================

DB_PATH = Path(__file__).parent / "data" / "vacancies.db"

app = FastAPI()


class AskRequest(BaseModel):
    text: str


# ======================
# SEARCH HELPERS
# ======================

def extract_search_term(text: str) -> str:
    words = re.findall(r"\w+", text.lower())
    stop_words = {
        "в", "на", "по", "для", "и", "или",
        "вакансии", "вакансия",
        "москва", "москве",
        "проанализируй", "анализ", "статистика"
    }
    keywords = [w for w in words if w not in stop_words]
    return " ".join(keywords[:2])


def is_analysis_request(text: str) -> bool:
    keywords = ["анализ", "проанализируй", "статистика", "сколько", "распределение"]
    text = text.lower()
    return any(k in text for k in keywords)


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


# ======================
# SEARCH (SQLite FTS5)
# ======================

def search_vacancies(query: str, limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    search_query = extract_search_term(query)
    if not search_query:
        conn.close()
        return []

    sql = f"""
    SELECT v.*
    FROM vacancies_fts f
    JOIN vacancies v ON v.id = f.rowid
    WHERE vacancies_fts MATCH "{search_query}*"
    LIMIT {int(limit)}
    """

    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    return rows


# ======================
# ANALYTICS (LEVEL 1)
# ======================

def analyze_vacancies(vacancies):
    total = len(vacancies)
    by_city = {}
    salary_samples = []

    for v in vacancies:
        city = v["city"] or "Не указан"
        by_city[city] = by_city.get(city, 0) + 1

        if v["salary"]:
            salary_samples.append(v["salary"])

    return {
        "total": total,
        "by_city": by_city,
        "salary_samples": salary_samples[:5],
    }


def build_analysis_text(stats):
    lines = []
    lines.append(f"📊 Всего найдено вакансий: {stats['total']}")

    lines.append("\n🏙 Распределение по городам:")
    for city, count in sorted(
        stats["by_city"].items(), key=lambda x: x[1], reverse=True
    ):
        lines.append(f"- {city}: {count}")

    if stats["salary_samples"]:
        lines.append("\n💰 Примеры зарплат:")
        for s in stats["salary_samples"]:
            lines.append(f"- {s}")

    return "\n".join(lines)


# ======================
# PLOT (LEVEL 2)
# ======================

def plot_city_distribution(by_city):
    filename = f"/tmp/cities_{uuid.uuid4().hex}.png"

    cities = list(by_city.keys())
    counts = list(by_city.values())

    plt.figure(figsize=(8, 4))
    plt.bar(cities, counts)
    plt.xticks(rotation=45, ha="right")
    plt.title("Распределение вакансий по городам")
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()

    return filename


# ======================
# API ENDPOINT (/ask)
# ======================

@app.post("/ask")
def ask(req: AskRequest):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    # для аналитики берём больше данных
    vacancies = search_vacancies(req.text, limit=50)

    # -------- ANALYSIS MODE --------
    if is_analysis_request(req.text):
        stats = analyze_vacancies(vacancies)
        analysis_text = build_analysis_text(stats)
        chart_path = plot_city_distribution(stats["by_city"])

        return {
            "analysis": analysis_text,
            "chart": chart_path
        }

    # -------- NORMAL Q&A MODE --------
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
            model="models/gemini-flash-latest",
            contents=prompt,
        )

        text = getattr(resp, "text", None)
        if not text:
            return {"error": "Empty response from model"}

        return {"answer": text}

    except Exception as e:
        msg = str(e)

        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return {
                "answer": (
                    "Сейчас модель временно недоступна, "
                    "но вот подходящие вакансии из базы:\n\n"
                    f"{context}"
                )
            }

        return {"error": msg}


# ======================
# CONTEXT BUILDER
# ======================

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
