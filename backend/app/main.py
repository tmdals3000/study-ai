import asyncio
import hashlib
import json
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from typing import Literal
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, delete, select, update
from . import auth, jobs, llm, tutor
from .config import APP_PASSWORD, COOKIE_SECURE, DATA_DIR, DB_PATH, EMBEDDING_MODEL, MAX_UPLOAD_BYTES, PAGE_IMAGE_DIR, ROOT, UPLOAD_DIR
from .db import engine, get_session, init_db
from .generators.figures import render_png, run_figures
from .generators.summary import run_summary
from .generators.study import run_study, grade_question
from .ingest import ingest_pdf
from .models import Attempt, Card, Chunk, Document, Generation, Message, Page, Question, Review
from .srs import review

@asynccontextmanager
async def lifespan(app):
    pending = init_db()
    jobs.start_workers()
    with Session(engine) as session:
        for doc_id in pending:
            doc = session.get(Document, doc_id)
            if doc:
                doc.status, doc.error = "processing", None
                session.add(doc)
        session.commit()
    for doc_id in pending:
        jobs.resume_ingest(doc_id)
    yield
    jobs.stop_workers()

app = FastAPI(title="Study AI", lifespan=lifespan)
app.middleware("http")(auth.guard)

def document(session, doc_id):
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    return doc

def latest(session, doc_id, kind):
    return session.exec(select(Generation).where(Generation.doc_id == doc_id, Generation.kind == kind).order_by(Generation.id.desc())).first()

def generation_output(session, job):
    if not job:
        return None
    result = jobs.output(job)
    if result["data"] is None:
        previous = session.exec(select(Generation).where(Generation.doc_id == job.doc_id,
            Generation.kind == job.kind, Generation.status == "done").order_by(Generation.id.desc())).first()
        if previous and previous.data:
            result["data"] = json.loads(previous.data)
    return result

def ensure_idle(session, doc):
    active_job = session.exec(select(Generation).where(Generation.doc_id == doc.id, Generation.status.in_(["queued", "running"]))).first()
    if doc.status == "processing" or active_job or doc.id in tutor.active:
        raise HTTPException(409, "처리 중인 작업을 마치거나 생성 작업을 취소한 뒤 시도해 주세요.")

@app.get("/api/health")
def health():
    return {"ok": True, "installation_id": hashlib.sha256(str(ROOT).encode()).hexdigest()[:16], "llm_provider": llm.LLM_PROVIDER, "model": llm.LLM_DEFAULT_MODEL,
            "retrieval": "semantic + lexical" if EMBEDDING_MODEL else "lexical"}

@app.get("/api/auth")
def auth_status(request: Request):
    return {"required": bool(APP_PASSWORD), "authenticated": auth.authenticated(request)}

class Login(BaseModel):
    password: str = Field(max_length=1000)

@app.post("/api/auth/login")
def login(body: Login, request: Request):
    if not auth.check_password(body.password, request.client.host if request.client else ""):
        raise HTTPException(401, "비밀번호가 다르거나 시도 횟수를 초과했습니다. 잠시 후 다시 시도해 주세요.")
    response = JSONResponse({"ok": True})
    response.set_cookie("study_session", auth.serializer.dumps("owner"), httponly=True, secure=COOKIE_SECURE, samesite="strict", max_age=43200)
    return response

@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("study_session")
    return response

@app.get("/api/documents")
def list_documents(session: Session = Depends(get_session)):
    return session.exec(select(Document).order_by(Document.id.desc())).all()

@app.post("/api/documents", status_code=201)
async def upload(file: UploadFile, background: BackgroundTasks, session: Session = Depends(get_session)):
    name = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 업로드할 수 있습니다.")
    stored = f"{uuid.uuid4().hex}.pdf"
    path = UPLOAD_DIR / stored
    size = 0
    try:
        with path.open("wb") as out:
            while block := await file.read(1024 * 1024):
                size += len(block)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"파일은 {MAX_UPLOAD_BYTES // 1024 // 1024}MB까지 올릴 수 있습니다.")
                if size == len(block) and b"%PDF-" not in block[:1024]:
                    raise HTTPException(400, "유효한 PDF 파일이 아닙니다.")
                out.write(block)
        if size == 0:
            raise HTTPException(400, "빈 파일입니다.")
        doc = Document(title=name.rsplit(".", 1)[0][:300], filename=stored)
        with jobs.lock:
            session.add(doc)
            session.commit()
            session.refresh(doc)
        background.add_task(ingest_pdf, doc.id)
        return doc
    except BaseException:
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int, session: Session = Depends(get_session)):
    return document(session, doc_id)

@app.get("/api/documents/{doc_id}/pages")
def pages(doc_id: int, session: Session = Depends(get_session)):
    document(session, doc_id)
    return session.exec(select(Page).where(Page.doc_id == doc_id).order_by(Page.page_no)).all()

@app.get("/api/documents/{doc_id}/pages/{page_no}/image")
def page_image(doc_id: int, page_no: int, session: Session = Depends(get_session)):
    """원문 탭에 보여줄 페이지 이미지. 처음 요청 때 렌더링해 캐시한다."""
    doc = document(session, doc_id)
    if not 1 <= page_no <= doc.pages:
        raise HTTPException(404, "페이지를 찾을 수 없습니다.")
    cached = PAGE_IMAGE_DIR / str(doc_id) / f"{page_no}.png"
    if not cached.is_file():
        source = UPLOAD_DIR / doc.filename
        if not source.is_file():
            raise HTTPException(404, "원본 PDF 파일이 없습니다.")
        cached.parent.mkdir(parents=True, exist_ok=True)
        partial = cached.with_suffix(f".{uuid.uuid4().hex}.tmp")
        partial.write_bytes(render_png(source, page_no))
        partial.replace(cached)
    return FileResponse(cached, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})

@app.get("/api/documents/{doc_id}/file")
def original(doc_id: int, session: Session = Depends(get_session)):
    doc = document(session, doc_id)
    path = UPLOAD_DIR / doc.filename
    if not path.is_file():
        raise HTTPException(404, "원본 PDF 파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=doc.title + ".pdf", content_disposition_type="inline")

@app.post("/api/documents/{doc_id}/retry")
def retry_ingest(doc_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    with jobs.lock, tutor.guard:
        doc = document(session, doc_id)
        ensure_idle(session, doc)
        if not (UPLOAD_DIR / doc.filename).exists():
            raise HTTPException(404, "원본 파일이 없습니다. 다시 업로드해 주세요.")
        doc.status, doc.error = "processing", None
        session.add(doc)
        session.commit()
    background.add_task(ingest_pdf, doc_id)
    return {"ok": True}

@app.delete("/api/documents/{doc_id}", status_code=204)
def remove_document(doc_id: int, session: Session = Depends(get_session)):
    with jobs.lock, tutor.guard:
        doc = document(session, doc_id)
        ensure_idle(session, doc)
        question_ids = select(Question.id).where(Question.doc_id == doc_id)
        card_ids = select(Card.id).where(Card.doc_id == doc_id)
        session.exec(delete(Attempt).where(Attempt.question_id.in_(question_ids)))
        session.exec(delete(Review).where(Review.card_id.in_(card_ids)))
        for table in (Question, Card, Message, Chunk, Page, Generation):
            session.exec(delete(table).where(table.doc_id == doc_id))
        filename = doc.filename
        session.delete(doc)
        session.commit()
        (UPLOAD_DIR / filename).unlink(missing_ok=True)
        shutil.rmtree(PAGE_IMAGE_DIR / str(doc_id), ignore_errors=True)

class GenerateRequest(BaseModel):
    force: bool = False
    count: int = Field(default=20, ge=1, le=40)
    types: list[Literal["multiple", "ox", "short"]] = Field(default_factory=lambda: ["multiple", "ox", "short"], min_length=1, max_length=3)
    wrong_only: bool = False

def start_generation(doc_id, kind, body, session):
    with jobs.lock:
        doc = document(session, doc_id)
        if doc.status != "ready":
            raise HTTPException(409, "문서 처리가 끝난 뒤 생성할 수 있습니다.")
        previous = latest(session, doc_id, kind)
        if previous and previous.status in ("queued", "running"):
            return jobs.output(previous)
        if previous and previous.status == "done" and not body.force:
            return jobs.output(previous)
        options = body.model_dump(exclude={"force"})
        if body.wrong_only and kind == "quiz":
            wrong = question_rows(session, doc_id, True)
            options["focus"] = sorted({row.concept for row in wrong if row.concept})
            if not options["focus"]:
                raise HTTPException(409, "아직 복습할 오답이 없습니다.")
        job = Generation(doc_id=doc_id, kind=kind, progress="대기 중", options=json.dumps(options, ensure_ascii=False))
        session.add(job)
        session.commit()
        session.refresh(job)
        result = jobs.output(job)
        jobs.submit(job.id, {"summary": run_summary, "figures": run_figures}.get(kind, run_study))
        return result

@app.post("/api/documents/{doc_id}/generate/{kind}", status_code=202)
def generate(doc_id: int, kind: Literal["summary", "quiz", "cards", "figures"], body: GenerateRequest = GenerateRequest(), session: Session = Depends(get_session)):
    return start_generation(doc_id, kind, body, session)

@app.get("/api/documents/{doc_id}/summary")
def summary(doc_id: int, session: Session = Depends(get_session)):
    document(session, doc_id)
    job = latest(session, doc_id, "summary")
    if job and job.status == "cancelled":
        job = session.exec(select(Generation).where(Generation.doc_id == doc_id, Generation.kind == "summary", Generation.status == "done").order_by(Generation.id.desc())).first() or job
    return generation_output(session, job)

@app.get("/api/documents/{doc_id}/generations/{kind}")
def generation(doc_id: int, kind: Literal["summary", "quiz", "cards", "figures"], session: Session = Depends(get_session)):
    document(session, doc_id)
    job = latest(session, doc_id, kind)
    return generation_output(session, job)

@app.post("/api/documents/{doc_id}/summary", status_code=202)
def legacy_start_summary(doc_id: int, session: Session = Depends(get_session)):
    return start_generation(doc_id, "summary", GenerateRequest(force=True), session)

@app.post("/api/documents/{doc_id}/summary/cancel", status_code=204)
def legacy_cancel_summary(doc_id: int, session: Session = Depends(get_session)):
    document(session, doc_id)
    job = latest(session, doc_id, "summary")
    if job:
        jobs.cancel(job.id)

@app.post("/api/generations/{job_id}/cancel")
def cancel(job_id: int, session: Session = Depends(get_session)):
    if not session.get(Generation, job_id):
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    jobs.cancel(job_id)
    return {"ok": True}

def question_rows(session, doc_id, wrong_only=False):
    rows = session.exec(select(Question).where(Question.doc_id == doc_id).order_by(Question.id)).all()
    if wrong_only:
        attempts = session.exec(select(Attempt).join(Question).where(Question.doc_id == doc_id).order_by(Attempt.id)).all()
        outcomes = {attempt.question_id: attempt.correct for attempt in attempts}
        rows = [q for q in rows if outcomes.get(q.id) is False]
    else:
        completed = session.exec(select(Generation).where(Generation.doc_id == doc_id, Generation.kind == "quiz", Generation.status == "done").order_by(Generation.id.desc())).first()
        if completed:
            rows = [q for q in rows if q.generation_id == completed.id]
    return rows

@app.get("/api/documents/{doc_id}/questions")
def questions(doc_id: int, wrong_only: bool = False, session: Session = Depends(get_session)):
    document(session, doc_id)
    return [{**q.model_dump(exclude={"answer", "explanation", "evidence"}), "choices": json.loads(q.choices)} for q in question_rows(session, doc_id, wrong_only)]

class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=3000)

@app.post("/api/questions/{question_id}/answer")
def answer_question(question_id: int, body: AnswerRequest, session: Session = Depends(get_session)):
    question = session.get(Question, question_id)
    if not question:
        raise HTTPException(404, "문제를 찾을 수 없습니다.")
    try:
        correct, feedback = grade_question(question, body.answer.strip())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc))
    with jobs.lock:
        session.expire_all()
        if not session.get(Question, question_id):
            raise HTTPException(409, "채점 중 문서가 삭제되었습니다.")
        attempt = Attempt(question_id=question_id, user_answer=body.answer, correct=correct, feedback=feedback)
        session.add(attempt)
        session.commit()
    return {"correct": correct, "feedback": feedback, "answer": question.answer,
            "explanation": question.explanation, "evidence": json.loads(question.evidence)}

def card_output(card):
    result = card.model_dump(exclude={"fsrs_state"})
    result["evidence"] = json.loads(card.evidence)
    result["due_at"] = card.due_at.isoformat() + "Z"
    return result

@app.get("/api/cards")
def cards(doc_id: int | None = None, due_only: bool = False, session: Session = Depends(get_session)):
    query = select(Card)
    if doc_id is not None:
        document(session, doc_id)
        query = query.where(Card.doc_id == doc_id)
    if due_only:
        query = query.where(Card.due_at <= datetime.utcnow())
    return [card_output(c) for c in session.exec(query.order_by(Card.due_at, Card.id)).all()]

class CardEdit(BaseModel):
    front: str = Field(min_length=1, max_length=1000)
    back: str = Field(min_length=1, max_length=5000)
    version: int = Field(ge=0)

@app.patch("/api/cards/{card_id}")
def edit_card(card_id: int, body: CardEdit, session: Session = Depends(get_session)):
    with jobs.lock:
        card = session.get(Card, card_id)
        if not card:
            raise HTTPException(404, "카드를 찾을 수 없습니다.")
        if body.version != card.version:
            raise HTTPException(409, "다른 화면에서 카드가 변경되었습니다. 새로고침해 주세요.")
        if not body.front.strip() or not body.back.strip():
            raise HTTPException(400, "앞면과 뒷면을 입력해 주세요.")
        card.front, card.back, card.edited = body.front.strip(), body.back.strip(), True
        card.version += 1
        session.add(card)
        session.commit()
        session.refresh(card)
        return card_output(card)

class RatingRequest(BaseModel):
    rating: int = Field(ge=1, le=4)
    version: int = Field(ge=0)

@app.post("/api/cards/{card_id}/review")
def rate_card(card_id: int, body: RatingRequest, session: Session = Depends(get_session)):
    with jobs.lock:
        card = session.get(Card, card_id)
        if not card:
            raise HTTPException(404, "카드를 찾을 수 없습니다.")
        if card.version != body.version:
            raise HTTPException(409, "이미 처리했거나 변경된 카드입니다. 새로고침해 주세요.")
        log = review(card, body.rating)
        session.add(Review(card_id=card_id, rating=body.rating, log=log))
        session.add(card)
        session.commit()
        session.refresh(card)
        return card_output(card)

@app.get("/api/dashboard")
def dashboard(session: Session = Depends(get_session)):
    return {"documents": session.exec(select(func.count(Document.id))).one(),
            "cards": session.exec(select(func.count(Card.id))).one(),
            "due": session.exec(select(func.count(Card.id)).where(Card.due_at <= datetime.utcnow())).one(),
            "attempts": session.exec(select(func.count(Attempt.id))).one(),
            "correct": session.exec(select(func.count(Attempt.id)).where(Attempt.correct == True)).one()}

@app.get("/api/documents/{doc_id}/messages")
def messages(doc_id: int, session: Session = Depends(get_session)):
    document(session, doc_id)
    return [tutor.output(m) for m in session.exec(select(Message).where(Message.doc_id == doc_id).order_by(Message.id)).all()]

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=3000)
    mode: Literal["explain", "socratic"] = "explain"

@app.post("/api/documents/{doc_id}/chat")
async def chat(doc_id: int, body: ChatRequest, session: Session = Depends(get_session)):
    with tutor.guard:
        doc = document(session, doc_id)
        if doc.status != "ready":
            raise HTTPException(409, "문서 처리를 먼저 완료해 주세요.")
        if doc_id in tutor.active:
            raise HTTPException(409, "앞선 답변을 생성 중입니다.")
        tutor.active.add(doc_id)
    task = asyncio.create_task(asyncio.to_thread(tutor.answer, doc_id, body.question, body.mode))
    def event(name, data):
        return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    async def events():
        yield event("status", {"message": "관련 원문을 찾아 답변과 출처를 검증하고 있습니다."})
        while not task.done():
            await asyncio.wait({task}, timeout=10)
            if not task.done():
                yield ": keep-alive\n\n"
        try:
            result = task.result()
            yield event("message", result)
            yield event("done", {})
        except Exception as exc:
            yield event("error", {"message": str(exc)[:1000]})
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/llm/ping")
def ping():
    try:
        return {"result": llm.generate("한 문장으로 인사해 주세요.", timeout=120, retries=0)}
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc))

@app.get("/api/backup")
def backup(background: BackgroundTasks):
    temporary = Path(tempfile.mkdtemp(prefix="study-backup-"))
    archive = temporary / f"study-ai-{datetime.now():%Y%m%d-%H%M%S}.zip"
    try:
        with jobs.lock:
            snapshot = temporary / "study.db"
            with closing(sqlite3.connect(DB_PATH)) as source, closing(sqlite3.connect(snapshot)) as target:  # with만 쓰면 연결이 닫히지 않아 Windows에서 파일이 잠긴다
                source.backup(target)
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(snapshot, "study.db")
                with closing(sqlite3.connect(snapshot)) as saved:
                    filenames = [row[0] for row in saved.execute("SELECT filename FROM document")]
                for filename in filenames:
                    file = UPLOAD_DIR / Path(filename).name
                    if file.is_file():
                        bundle.write(file, "uploads/" + file.name)
        background.add_task(shutil.rmtree, temporary)
        return FileResponse(archive, filename=archive.name, media_type="application/zip")
    except Exception:
        shutil.rmtree(temporary)
        raise

# Production: one loopback server serves both the API and the built PWA.
distribution = ROOT / "frontend" / "dist"
if distribution.exists():
    assets = distribution / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "API를 찾을 수 없습니다.")
        candidate = (distribution / path).resolve()
        if candidate.is_relative_to(distribution.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(distribution / "index.html", headers={"Cache-Control": "no-cache"})
