"""Bounded local workers, persistent status and cooperative cancellation."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime
from sqlmodel import Session
from .db import engine
from .models import Generation

current_job: ContextVar[int | None] = ContextVar("current_job", default=None)
_executor: ThreadPoolExecutor | None = None
_cancelled: dict[int, threading.Event] = {}
lock = threading.RLock()

class JobStopped(Exception):
    pass

def checkpoint() -> None:
    job_id = current_job.get()
    event = _cancelled.get(job_id) if job_id is not None else None
    if event and event.is_set():
        raise JobStopped()

def update_job(job_id: int, **fields) -> bool:
    checkpoint()
    with lock, Session(engine) as session:
        job = session.get(Generation, job_id)
        if job is None or job.status == "cancelled":
            raise JobStopped()
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = datetime.now()
        session.add(job)
        session.commit()
    return True

def _run(job_id: int, action) -> None:
    token = current_job.set(job_id)
    try:
        update_job(job_id, status="running", progress="생성을 시작합니다")
        action(job_id)
    except JobStopped:
        pass
    except Exception as exc:
        try:
            update_job(job_id, status="error", progress=None, error=str(exc)[:1500])
        except JobStopped:
            pass
    finally:
        current_job.reset(token)
        with lock:
            _cancelled.pop(job_id, None)

def start_workers():
    global _executor
    _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="study")

def submit(job_id: int, action):
    with lock:
        if _executor is None:
            raise RuntimeError("작업 서버가 준비되지 않았습니다.")
        _cancelled[job_id] = threading.Event()
        _executor.submit(_run, job_id, action)

def resume_ingest(doc_id: int):
    from .ingest import ingest_pdf
    if _executor:
        _executor.submit(ingest_pdf, doc_id)

def cancel(job_id: int):
    with lock:
        event = _cancelled.get(job_id)
        if event:
            event.set()
        with Session(engine) as session:
            job = session.get(Generation, job_id)
            if job and job.status in ("queued", "running"):
                job.status, job.progress = "cancelled", None
                session.add(job)
                session.commit()

def stop_workers():
    global _executor
    with lock:
        for event in _cancelled.values():
            event.set()
    if _executor:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None

def output(job: Generation) -> dict:
    result = job.model_dump(exclude={"data", "options"})
    result["data"] = json.loads(job.data) if job.data else None
    return result
