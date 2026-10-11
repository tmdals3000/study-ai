import json
import threading
from sqlmodel import Session, select
from . import llm
from .db import engine
from .generators.verify import verify_scoped
from .grounding import match_evidence
from .models import Document, Message
from .prompts import load_prompt
from .retrieval import retrieve
from .schemas import obj, string, array, EVIDENCE

SCHEMA = obj({"paragraphs": array(obj({"text": string(2000), "evidence": EVIDENCE}), 0, 10)})
active: set[int] = set()
guard = threading.RLock()

def output(message):
    result = message.model_dump()
    result["citations"] = json.loads(message.citations)
    return result

def answer(doc_id, question, mode):
    try:
        with Session(engine) as session:
            if not session.get(Document, doc_id):
                raise ValueError("문서를 찾을 수 없습니다.")
            history = session.exec(select(Message).where(Message.doc_id == doc_id).order_by(Message.id.desc()).limit(8)).all()[::-1]
            history_text = json.dumps([{"role": m.role, "content": m.content[:3000]} for m in history], ensure_ascii=False)
            search_query = question
            if len(question) < 25:
                previous = next((m.content[:500] for m in reversed(history) if m.role == "user"), "")
                search_query += " " + previous
            sources = retrieve(session, doc_id, search_query)
            session.add(Message(doc_id=doc_id, role="user", content=question, mode=mode))
            session.commit()
        paragraphs = []
        if sources:
            out = llm.generate(load_prompt("tutor", MODE=mode, HISTORY=history_text, QUESTION=question,
                SOURCE=json.dumps(sources, ensure_ascii=False)), system=load_prompt("system_grounded"), schema=SCHEMA)
            page_text = {}
            for source in sources:
                page_text[source["page"]] = page_text.get(source["page"], "") + "\n" + source["text"]
            candidates = {}
            for i, paragraph in enumerate(out["paragraphs"]):
                evidence = match_evidence(paragraph["evidence"], page_text)
                if evidence:
                    candidates[str(i)] = {"text": paragraph["text"], "evidence": evidence}
            verdicts = verify_scoped({key: (p["text"], "\n".join(e["quote"] for e in p["evidence"])) for key, p in candidates.items()})
            paragraphs = [p for key, p in candidates.items() if verdicts.get(key, {}).get("verdict") == "supported"]
        citations = []
        for paragraph in paragraphs:
            for evidence in paragraph["evidence"]:
                if evidence not in citations:
                    citations.append(evidence)
        content = "\n\n".join(p["text"] + " " + " ".join(f'[p.{n}]' for n in sorted({e["page"] for e in p["evidence"]})) for p in paragraphs)
        if not content:
            content = "이 질문에 답할 근거를 문서에서 확인하지 못했습니다. 문서에 나온 용어나 페이지를 포함해 다시 질문해 주세요."
        with Session(engine) as session:
            message = Message(doc_id=doc_id, role="assistant", content=content, citations=json.dumps(citations, ensure_ascii=False), mode=mode)
            session.add(message)
            session.commit()
            session.refresh(message)
            return output(message)
    finally:
        with guard:
            active.discard(doc_id)
