from fastapi import FastAPI
from pydantic import BaseModel
import os
import httpx

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

    url = (
        "https://generativelanguage.googleapis.com/v1/models/"
        "gemini-1.5-flash:generateContent"
    )

    headers = {"Content-Type": "application/json"}
    params = {"key": api_key}

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": req.text}
                ]
            }
        ]
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=30
        )

    data = resp.json()

    try:
        answer = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return {"error": data}

    return {"answer": answer}
