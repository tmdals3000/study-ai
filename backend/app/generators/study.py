import json
import math
from sqlmodel import Session, select
from .. import llm
from ..config import MODEL_GENERATE, MODEL_VERIFY
from ..db import engine
from ..grounding import match_evidence, normalize
from ..jobs import checkpoint, lock, update_job, JobStopped
from ..models import Card, Chunk, Generation, Page, Question
from ..prompts import load_prompt
from ..retrieval import index_pages, retrieve
from ..schemas import obj, string, array, EVIDENCE
from .verify import verify_scoped

QUESTION_SCHEMA = obj({"items": array(obj({
    "type": {"type": "string", "enum": ["multiple", "ox", "short"]},
    "question": string(1200), "choices": array(string(500), 0, 4), "answer": string(1200),
    "explanation": string(2000), "evidence": EVIDENCE, "concept": string(200),
    "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]}}), 0, 40)})
CARD_SCHEMA = obj({"items": array(obj({"front": string(500), "back": string(2000), "evidence": EVIDENCE}), 0, 40)})
QUALITY_SCHEMA = obj({"verdicts": array(obj({"id": string(100), "valid": {"type": "boolean"},
    "quality": {"type": "integer", "minimum": 1, "maximum": 5}, "issues": {"type": "string"}}), 0, 40)})
GRADE_SCHEMA = obj({"correct": {"type": "boolean"}, "feedback": string(2000)})

def valid_question(item, types):
    if item["type"] not in types:
        return False
    choices = item["choices"]
    if item["type"] == "multiple":
        return len(choices) == 4 and len({normalize(x) for x in choices}) == 4 and item["answer"] in choices
    if item["type"] == "ox":
        return choices == ["O", "X"] and item["answer"] in choices
    return not choices and bool(item["answer"].strip())

def run_study(job_id):
    with Session(engine) as session:
        job = session.get(Generation, job_id)
        if not job:
            raise JobStopped()
        doc_id, kind, options = job.doc_id, job.kind, json.loads(job.options)
        pages = session.exec(select(Page).where(Page.doc_id == doc_id).order_by(Page.page_no)).all()
        chunks = session.exec(select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.id)).all()
        if not chunks:
            index_pages(session, doc_id, [(p.page_no, p.text) for p in pages])
            session.commit()
            chunks = session.exec(select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.id)).all()
    if not chunks:
        raise ValueError("추출된 텍스트가 없습니다.")
    count = options.get("count", 20)
    types = options.get("types", ["multiple", "ox", "short"])
    batches = min(len(chunks), count, 8)
    selected = [chunks[round(i * (len(chunks) - 1) / max(1, batches - 1))] for i in range(batches)]
    if options.get("focus"):
        with Session(engine) as session:
            matches = retrieve(session, doc_id, " ".join(options["focus"]), top_k=batches)
        matched_ids = {item["id"] for item in matches}
        selected = [chunk for chunk in chunks if chunk.id in matched_ids]
        if not selected:
            raise ValueError("오답 개념에 해당하는 원문을 찾지 못했습니다.")
    kept, seen, generated, rejected = [], set(), 0, 0
    for i, chunk in enumerate(selected):
        checkpoint()
        update_job(job_id, progress=f"생성·검증 중 ({i + 1}/{len(selected)})")
        requested = min(count - len(kept), math.ceil(count / batches) + 1)
        if requested <= 0:
            break
        source = f'<page n="{chunk.page_start}">\n{chunk.text}\n</page>'
        prompt = load_prompt("quiz" if kind == "quiz" else "cards", COUNT=str(requested),
            TYPES=", ".join(types), FOCUS=", ".join(options.get("focus", [])) or "전체", SOURCE=source)
        out = llm.generate(prompt, system=load_prompt("system_grounded"),
            schema=QUESTION_SCHEMA if kind == "quiz" else CARD_SCHEMA, model=MODEL_GENERATE)
        candidates = {}
        for index, item in enumerate(out["items"]):
            generated += 1
            evidence = match_evidence(item["evidence"], {chunk.page_start: chunk.text})
            fingerprint = normalize(item["question"] if kind == "quiz" else item["front"]).lower()
            if not evidence or fingerprint in seen or (kind == "quiz" and not valid_question(item, types)):
                rejected += 1
                continue
            seen.add(fingerprint)
            candidates[str(index)] = {**item, "evidence": evidence}
        if kind == "quiz" and candidates:
            payload = [{"id": key, "question": item, "focus": options.get("focus", []), "source": "\n".join(e["quote"] for e in item["evidence"])} for key, item in candidates.items()]
            verdicts = llm.generate(load_prompt("quiz_verify", ITEMS=json.dumps(payload, ensure_ascii=False)),
                system=load_prompt("system_grounded"), schema=QUALITY_SCHEMA, model=MODEL_VERIFY)["verdicts"]
            valid_ids = {v["id"] for v in verdicts if v["valid"] and v["quality"] >= 4 and sum(x["id"] == v["id"] for x in verdicts) == 1}
        elif candidates:
            verdicts = verify_scoped({key: ("질문: " + item["front"] + "\n답변: " + item["back"], "\n".join(e["quote"] for e in item["evidence"])) for key, item in candidates.items()})
            valid_ids = {key for key, verdict in verdicts.items() if verdict["verdict"] == "supported"}
        else:
            valid_ids = set()
        for key, item in candidates.items():
            if key in valid_ids and len(kept) < count:
                kept.append(item)
            elif key not in valid_ids:
                rejected += 1
    checkpoint()
    # Persist all output atomically, guarded against cancellation/deletion.
    with lock, Session(engine) as session:
        job = session.get(Generation, job_id)
        if not job or job.status not in ("queued", "running"):
            raise JobStopped()
        saved = 0
        existing = {normalize(c.front).lower() for c in session.exec(select(Card).where(Card.doc_id == doc_id)).all()} if kind == "cards" else set()
        for item in kept:
            evidence = json.dumps(item["evidence"], ensure_ascii=False)
            if kind == "quiz":
                session.add(Question(doc_id=doc_id, generation_id=job_id, type=item["type"], question=item["question"],
                    choices=json.dumps(item["choices"], ensure_ascii=False), answer=item["answer"], explanation=item["explanation"],
                    evidence=evidence, difficulty=item["difficulty"], concept=item["concept"]))
            else:
                fingerprint = normalize(item["front"]).lower()
                if fingerprint in existing:
                    continue
                existing.add(fingerprint)
                session.add(Card(doc_id=doc_id, front=item["front"], back=item["back"], evidence=evidence))
            saved += 1
        job.status, job.progress = "done", None
        job.data = json.dumps({"requested": count, "generated": generated, "kept": saved, "rejected": rejected,
            "note": "원문 근거와 품질 기준을 통과한 항목만 저장합니다. 요청 수보다 적을 수 있습니다."}, ensure_ascii=False)
        session.add(job)
        session.commit()

def grade_question(question: Question, answer: str):
    expected = question.answer
    if question.type in ("multiple", "ox"):
        if answer not in json.loads(question.choices):
            raise ValueError("보기 중 하나를 선택해 주세요.")
        correct = answer == expected
        return correct, question.explanation
    if normalize(answer).casefold() == normalize(expected).casefold():
        return True, question.explanation
    item = {"question": question.question, "expected": expected, "student_answer": answer,
            "evidence": json.loads(question.evidence)}
    result = llm.generate(load_prompt("grade", ITEM=json.dumps(item, ensure_ascii=False)),
        system=load_prompt("system_grounded"), schema=GRADE_SCHEMA, model=MODEL_VERIFY, timeout=180)
    return result["correct"], result["feedback"]
