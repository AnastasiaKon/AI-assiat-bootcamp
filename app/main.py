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
    # MVP-заглушка: пока просто эхо
    # дальше сюда подключим Gemini
    return {"answer": f"Ты спросила: {req.text}"}
