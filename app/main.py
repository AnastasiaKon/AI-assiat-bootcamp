from fastapi import FastAPI
from pydantic import BaseModel
import os
import sqlite3
from pathlib import Path
import re

from google import genai  # google-genai SDK

# ======================
# CONFIG
# ======================

DB_PATH = Path(__file__).parent / "data" / "vacancies.db"

app = FastAPI()


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
        return "Под
