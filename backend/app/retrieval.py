"""Page-preserving chunks and local retrieval. Optional semantic vectors stay in SQLite."""
import json
import math
import re
import threading
from collections import Counter
from functools import lru_cache
from sqlmodel import Session, delete, select
from sqlalchemy import text as sql
from .config import EMBEDDING_MODEL
from .models import Chunk, Page

_model_lock = threading.Lock()

def split_text(text: str, limit: int = 2400, overlap: int = 180):
    text = text.strip()
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            candidates = [text.rfind(delimiter, start + limit // 2, end) for delimiter in ("\n\n", "\n", ". ", "。")]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + 1
        part = text[start:end].strip()
        if part:
            yield part
        if end == len(text):
            break
        start = max(start + 1, end - overlap)

@lru_cache(maxsize=1)
def embedding_model():
    if not EMBEDDING_MODEL:
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("임베딩 패키지가 없습니다. setup-embeddings.ps1을 먼저 실행해 주세요.") from exc
    # Never silently download a model or transmit a document.
    return SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)

def encode(texts: list[str]):
    with _model_lock:
        model = embedding_model()
        if model is None:
            return None
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

def index_pages(session: Session, doc_id: int, pages: list[tuple[int, str]]):
    session.exec(delete(Chunk).where(Chunk.doc_id == doc_id))
    chunks = [(n, part) for n, text in pages for part in split_text(text)]
    for start in range(0, len(chunks), 32):
        batch = chunks[start:start + 32]
        vectors = encode([text for _, text in batch])
        for i, (number, text) in enumerate(batch):
            session.add(Chunk(doc_id=doc_id, page_start=number, page_end=number, text=text,
                embedding=json.dumps(vectors[i]) if vectors else None,
                embedding_model=EMBEDDING_MODEL or "lexical"))

def tokens(text):
    words = re.findall(r"[a-z0-9]+|[가-힣]+", text.lower())
    return words + [word[i:i+2] for word in words if re.fullmatch(r"[가-힣]+", word) for i in range(len(word)-1)]

def retrieve(session: Session, doc_id: int, query: str, top_k=5) -> list[dict]:
    rows = session.exec(select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.id)).all()
    if not rows:
        pages = session.exec(select(Page).where(Page.doc_id == doc_id).order_by(Page.page_no)).all()
        index_pages(session, doc_id, [(p.page_no, p.text) for p in pages])
        session.commit()
        rows = session.exec(select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.id)).all()
    if not rows:
        return []
    query_tokens = set(tokens(query))
    counts = [Counter(tokens(row.text)) for row in rows]
    avg_length = sum(sum(c.values()) for c in counts) / len(rows) or 1
    frequency = {t: sum(t in c for c in counts) for t in query_tokens}
    query_vector = encode([query]) if EMBEDDING_MODEL else None
    similarities = {}
    if query_vector:
        similarities = dict(session.execute(sql(
            "SELECT id, 1 - vec_distance_cosine(vec_f32(embedding), vec_f32(:query)) "
            "FROM chunk WHERE doc_id=:doc AND embedding_model=:model AND embedding IS NOT NULL "
            "AND json_array_length(embedding)=:dimensions"
        ), {"query": json.dumps(query_vector[0]), "doc": doc_id, "model": EMBEDDING_MODEL,
            "dimensions": len(query_vector[0])}).all())
    ranked = []
    for row, count in zip(rows, counts):
        score = 0.0
        length = sum(count.values())
        for t in query_tokens:
            tf = count[t]
            score += math.log(1 + (len(rows) - frequency[t] + 0.5) / (frequency[t] + 0.5)) * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg_length)) if tf else 0
        if row.id in similarities:
            score = score / (1 + score) + max(0, similarities[row.id])
        if score > 0:
            ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [{"id": r.id, "page": r.page_start, "text": r.text, "score": round(score, 4)} for score, r in ranked[:top_k]]
