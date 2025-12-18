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
