"""
서울우유 RAG 챗봇 - FastAPI 백엔드
실행: python app.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY가 없습니다. .env 파일을 확인하세요.")

from rag.retriever import SeoulMilkRetriever

retriever = SeoulMilkRetriever(api_key=API_KEY)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="서울우유 RAG 챗봇")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── 요청/응답 모델 ──────────────────────────
class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []   # [{"role": "user"/"assistant", "content": "..."}]


class Source(BaseModel):
    type: str           # "product" | "faq" | "recipe"
    label: str
    image_url: str = ""
    url: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


# ── 엔드포인트 ──────────────────────────────
@app.get("/")
def root():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=500, detail="static/index.html 파일이 없습니다.")
    return FileResponse(str(index))


@app.get("/api/health")
def health():
    return {"ok": True, "model": os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="메시지를 입력하세요.")
    try:
        result = retriever.answer(req.message, history=req.history)
        return ChatResponse(answer=result["answer"], sources=result["sources"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
