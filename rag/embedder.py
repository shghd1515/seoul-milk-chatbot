"""
임베딩 + ChromaDB 저장 모듈
- 크롤링된 JSON 데이터를 청킹하여 벡터DB에 저장
- 실행: python rag/embedder.py
"""

import json
from pathlib import Path

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from google import genai

DATA_DIR = Path(__file__).parent.parent / "crawling" / "data"
CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"

# Google Gemini 임베딩 모델 (새 SDK 기준)
EMBEDDING_MODEL = "gemini-embedding-001"


class GeminiEmbeddingFunction(EmbeddingFunction):
    """새 google-genai SDK를 사용하는 ChromaDB 임베딩 함수.
    embedder와 retriever 양쪽에서 동일하게 사용해야 한다.
    """

    def __init__(self, api_key: str, model: str = EMBEDDING_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def __call__(self, input: Documents) -> Embeddings:
        result = self.client.models.embed_content(
            model=self.model,
            contents=input,
        )
        return [e.values for e in result.embeddings]


def load_json(filename: str) -> list:
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  [경고] {path} 파일이 없습니다. 먼저 crawler.py를 실행하세요.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """텍스트를 일정 크기로 청킹"""
    if not text or len(text) < chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def prepare_documents() -> tuple[list[str], list[dict], list[str]]:
    """JSON 데이터를 ChromaDB용 문서로 변환"""
    documents = []
    metadatas = []
    ids = []
    idx = 0

    # 제품 정보
    products = load_json("products.json")
    print(f"  제품 데이터: {len(products)}건 로드")
    for item in products:
        text = f"[제품] {item.get('category', '')} - {item.get('name', '')}\n"
        text += f"설명: {item.get('description', '')}\n"
        if item.get("nutrition"):
            nutrition_str = ", ".join(
                f"{k}: {v}" for k, v in item["nutrition"].items()
            )
            text += f"영양정보: {nutrition_str}"

        for chunk in chunk_text(text):
            documents.append(chunk)
            metadatas.append({
                "type": "product",
                "name": item.get("name", ""),
                "url": item.get("url", ""),
                "image_url": item.get("image_url", ""),  # ← 신규 필드
            })
            ids.append(f"product_{idx}")
            idx += 1

    # FAQ
    faqs = load_json("faq.json")
    print(f"  FAQ 데이터: {len(faqs)}건 로드")
    for item in faqs:
        text = f"[FAQ] Q: {item.get('question', '')}\nA: {item.get('answer', '')}"
        for chunk in chunk_text(text):
            documents.append(chunk)
            metadatas.append({"type": "faq", "question": item.get("question", "")})
            ids.append(f"faq_{idx}")
            idx += 1

    # 레시피
    recipes = load_json("recipes.json")
    print(f"  레시피 데이터: {len(recipes)}건 로드")
    for item in recipes:
        steps_str = " → ".join(item.get("steps", []))
        text = (
            f"[레시피] {item.get('title', '')}\n"
            f"재료: {item.get('ingredients', '')}\n"
            f"조리법: {steps_str}"
        )
        for chunk in chunk_text(text):
            documents.append(chunk)
            metadatas.append({"type": "recipe", "title": item.get("title", ""), "url": item.get("url", "")})
            ids.append(f"recipe_{idx}")
            idx += 1

    return documents, metadatas, ids


def build_vectordb(api_key: str):
    """ChromaDB에 문서 임베딩 후 저장"""
    import os
    os.environ["GOOGLE_API_KEY"] = api_key

    print("\n[임베딩] 문서 준비 중...")
    documents, metadatas, ids = prepare_documents()

    if not documents:
        print("저장할 문서가 없습니다. 크롤러를 먼저 실행하세요.")
        return

    print(f"  총 {len(documents)}개 청크 준비 완료")

    # ChromaDB 초기화
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = GeminiEmbeddingFunction(api_key=api_key)

    # 기존 컬렉션 삭제 후 재생성
    try:
        client.delete_collection("seoulmilk")
    except Exception:
        pass

    collection = client.create_collection(
        name="seoulmilk",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # 배치 단위로 저장 (API 한도 고려)
    BATCH_SIZE = 50
    for i in range(0, len(documents), BATCH_SIZE):
        batch_docs = documents[i:i + BATCH_SIZE]
        batch_meta = metadatas[i:i + BATCH_SIZE]
        batch_ids = ids[i:i + BATCH_SIZE]

        collection.add(
            documents=batch_docs,
            metadatas=batch_meta,
            ids=batch_ids,
        )
        print(f"  저장 중... {min(i + BATCH_SIZE, len(documents))}/{len(documents)}")

    print(f"\n✅ ChromaDB 저장 완료! ({CHROMA_DIR})")
    print(f"   총 {collection.count()}개 청크 저장됨")


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 GEMINI_API_KEY를 설정하세요.")

    build_vectordb(api_key)
