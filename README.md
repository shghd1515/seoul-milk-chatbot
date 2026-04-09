# 🥛 서울우유 RAG 챗봇

서울우유 홈페이지를 크롤링한 데이터를 기반으로 **제품 정보 · FAQ · 레시피 · CS** 질문에 답변하는 AI 챗봇입니다.

---

## 주요 기능

- **제품 정보 안내** — 흰우유, 가공유, 발효유 등 전 제품 정보 및 영양성분 안내
- **FAQ 답변** — 자주 묻는 질문에 대한 정확한 답변
- **레시피 추천** — 우유를 활용한 레시피 안내 및 조리법 설명
- **대화 히스토리** — 이전 대화 맥락을 기억하여 자연스러운 대화
- **출처 표시** — 답변 근거 문서를 함께 표시 (할루시네이션 방지)

---

## 기술 스택

| 역할 | 기술 |
|------|------|
| 크롤링 | `requests`, `BeautifulSoup4` |
| 임베딩 | `Google Generative AI Embedding` |
| 벡터DB | `ChromaDB` |
| LLM | `Gemini 2.5 Flash` |
| 백엔드 | `FastAPI`, `Uvicorn` |
| 프론트엔드 | `HTML / CSS / Vanilla JS` |

---

## 프로젝트 구조

```
seoul-milk-chatbot/
├── crawling/
│   ├── crawler.py          # 서울우유 홈페이지 크롤링
│   └── data/               # 크롤링 결과 (gitignore)
│       ├── products.json
│       ├── faq.json
│       └── recipes.json
├── rag/
│   ├── embedder.py         # 임베딩 + ChromaDB 저장
│   └── retriever.py        # 유사 검색 + Gemini 답변 생성
├── static/
│   └── index.html          # 웹 챗봇 UI
├── chroma_db/              # 벡터DB 저장소 (gitignore)
├── app.py                  # FastAPI 서버
├── .env.example            # 환경변수 예시
├── .gitignore
├── requirement.txt
└── README.md
```

---

## 시작하기

### 1. 저장소 클론

```bash
git clone https://github.com/shghd1515/seoul-milk-chatbot.git
cd seoul-milk-chatbot
```

### 2. 의존성 설치

```bash
pip install -r requirement.txt
```

### 3. 환경변수 설정

```bash
cp .env.example .env
# .env 파일에 GEMINI_API_KEY 입력
```

### 4. 데이터 크롤링

```bash
python crawling/crawler.py
```

### 5. 벡터DB 구축 (임베딩)

```bash
python rag/embedder.py
```

### 6. 서버 실행

```bash
python app.py
```

브라우저에서 [http://127.0.0.1:8000](http://127.0.0.1:8000) 접속

---

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/` | 챗봇 웹 UI |
| `GET` | `/api/health` | 서버 상태 확인 |
| `POST` | `/api/chat` | 챗봇 질문/답변 |

### POST `/api/chat` 요청 예시

```json
{
  "message": "흰우유 영양성분 알려줘",
  "history": []
}
```

### 응답 예시

```json
{
  "answer": "서울우유 흰우유 200ml 기준 영양성분은...",
  "sources": ["제품: 서울우유 흰우유", "FAQ: 영양성분 관련..."]
}
```

---

## 라이선스

MIT License
