"""
검색 + LLM 호출 모듈
- 사용자 질문 → ChromaDB 유사 검색 → Gemini 답변 생성
"""

import os
from pathlib import Path

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from google import genai

CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"

# ⚠️ embedder.py와 반드시 동일해야 함 (다르면 검색 불가)
EMBEDDING_MODEL = "gemini-embedding-001"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")

SYSTEM_PROMPT = """너는 서울우유 공식 고객 상담 AI 어시스턴트야.
아래 [참고 문서]를 바탕으로 사용자의 질문에 친절하고 정확하게 답변해.

규칙:
1. 반드시 참고 문서에 있는 내용만 사용해서 답변해.
2. 참고 문서에 없는 내용은 "죄송합니다, 해당 정보는 확인이 어렵습니다."라고 말해.
3. 제품 정보, FAQ, 레시피 등 다양한 질문에 답변할 수 있어.
4. 답변은 친근하고 명확하게, 한국어로 해.
5. 레시피 질문에는 재료와 조리법을 단계별로 설명해.
6. 답변은 핵심만 간결하게, 불필요한 인사말이나 반복은 피해. 목록은 최대 5개까지만 보여주고 더 궁금한 게 있으면 물어보라고 안내해.
"""


class GeminiEmbeddingFunction(EmbeddingFunction):
    """embedder.py와 동일한 구현 — 임베딩 모델/SDK가 일치해야 검색이 정상 동작."""

    def __init__(self, api_key: str, model: str = EMBEDDING_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def __call__(self, input: Documents) -> Embeddings:
        result = self.client.models.embed_content(
            model=self.model,
            contents=input,
        )
        return [e.values for e in result.embeddings]


class SeoulMilkRetriever:
    def __init__(self, api_key: str):
        self.api_key = api_key
        os.environ["GOOGLE_API_KEY"] = api_key

        # ChromaDB 연결
        self.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.ef = GeminiEmbeddingFunction(api_key=api_key)
        self.collection = self.chroma_client.get_collection(
            name="seoulmilk",
            embedding_function=self.ef,
        )

        # Gemini 클라이언트
        self.gemini = genai.Client(api_key=api_key)

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """사용자 질문과 유사한 문서 검색"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
        )

        docs = []
        for i, doc in enumerate(results["documents"][0]):
            docs.append({
                "content": doc,
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
        return docs

    def answer(self, query: str, history: list[dict] | None = None) -> dict:
        """
        질문에 대한 RAG 기반 답변 생성
        Returns: {"answer": str, "sources": list[dict]}
        """
        # 1. 유사 문서 검색
        docs = self.search(query, n_results=5)

        # 2. 컨텍스트 구성
        context = "\n\n".join(
            f"[문서 {i+1}] ({doc['metadata'].get('type', '')})\n{doc['content']}"
            for i, doc in enumerate(docs)
        )

        # 3. 대화 히스토리 포함 프롬프트 구성
        history_str = ""
        if history:
            for msg in history[-6:]:  # 최근 6턴만
                role = "사용자" if msg["role"] == "user" else "어시스턴트"
                history_str += f"{role}: {msg['content']}\n"

        prompt = f"""{SYSTEM_PROMPT}

[참고 문서]
{context}

[대화 기록]
{history_str}

[사용자 질문]
{query}

[답변]"""

        # 4. Gemini 호출
        resp = self.gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"temperature": 0.3, "max_output_tokens": 4096},
        )

        answer_text = (getattr(resp, "text", None) or "").strip()

        # 5. 출처 정보 (객체 배열, 중복 제거)
        sources = []
        seen = set()
        for doc in docs:
            meta = doc["metadata"]
            source_type = meta.get("type", "")

            if source_type == "product":
                key = ("product", meta.get("name", ""))
                if key in seen:
                    continue
                seen.add(key)
                sources.append({
                    "type": "product",
                    "label": meta.get("name", ""),
                    "image_url": meta.get("image_url", ""),
                    "url": meta.get("url", ""),
                })
            elif source_type == "faq":
                q = meta.get("question", "")
                key = ("faq", q)
                if key in seen:
                    continue
                seen.add(key)
                sources.append({
                    "type": "faq",
                    "label": q[:30] + ("..." if len(q) > 30 else ""),
                    "image_url": "",
                    "url": "",
                })
            elif source_type == "recipe":
                t = meta.get("title", "")
                key = ("recipe", t)
                if key in seen:
                    continue
                seen.add(key)
                sources.append({
                    "type": "recipe",
                    "label": t,
                    "image_url": "",
                    "url": meta.get("url", ""),
                })

        return {
            "answer": answer_text,
            "sources": sources,
        }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    retriever = SeoulMilkRetriever(api_key)

    # 테스트
    test_questions = [
        "서울우유 흰 우유 영양성분이 어떻게 돼?",
        "우유로 만들 수 있는 레시피 추천해줘",
        "유통기한이 지난 우유는 어떻게 해야 해?",
    ]

    for q in test_questions:
        print(f"\n질문: {q}")
        result = retriever.answer(q)
        print(f"답변: {result['answer']}")
        print(f"출처: {result['sources']}")
        print("-" * 40)
