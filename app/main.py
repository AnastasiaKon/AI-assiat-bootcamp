from fastapi import FastAPI
from pydantic import BaseModel
import os
import google.generativeai as genai

app = FastAPI()

class AskRequest(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ask")
def ask(req: AskRequest):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    genai.configure(api_key=api_key)

    try:
        model = genai.GenerativeModel("models/gemini-pro")
        response = model.generate_content(req.text)

        if not response or not response.text:
            return {"error": "Empty response from Gemini"}

        return {"answer": response.text}

    except Exception as e:
        return {"error": str(e)}
