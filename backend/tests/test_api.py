"""Regression scenarios retained from the original implementation, using isolated fixtures."""
import time
import fitz
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app import ingest, main
from app.db import engine
from app.ingest import ingest_pdf
from app.models import Document, Generation, Page
from .test_workflow import pdf_bytes, upload

def test_upload_and_extract(client):
    doc = upload(client)
    assert client.get(f"/api/documents/{doc}").json()["status"] == "ready"
    assert client.get(f"/api/documents/{doc}/pages").json()[0]["page_no"] == 1

def test_upload_rejects_non_pdf_content(client):
    result = client.post("/api/documents", files={"file": ("fake.pdf", b"not a pdf")})
    assert result.status_code == 400

def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 0)
    assert client.post("/api/documents", files={"file": ("lecture.pdf", pdf_bytes())}).status_code == 413

def test_ingest_skips_document_deleted_during_extraction(client, tmp_path, monkeypatch):
    (tmp_path / "a.pdf").write_bytes(pdf_bytes())
    monkeypatch.setattr(ingest, "UPLOAD_DIR", tmp_path)
    with Session(engine) as session:
        doc = Document(title="a", filename="a.pdf")
        session.add(doc); session.commit(); doc_id = doc.id
    real_open = fitz.open
    def open_then_delete(*args, **kwargs):
        with Session(engine) as session:
            session.delete(session.get(Document, doc_id)); session.commit()
        return real_open(*args, **kwargs)
    monkeypatch.setattr(ingest.fitz, "open", open_then_delete)
    ingest_pdf(doc_id)
    with Session(engine) as session:
        assert not session.exec(select(Page).where(Page.doc_id == doc_id)).all()

def test_restart_recovers_processing_docs_and_running_jobs(client):
    doc_id = upload(client)
    with Session(engine) as session:
        doc = session.get(Document, doc_id); doc.status = "processing"
        session.add(doc); session.add(Generation(doc_id=doc_id, kind="summary", status="running")); session.commit()
    with TestClient(main.app) as restarted:
        for _ in range(100):
            if restarted.get(f"/api/documents/{doc_id}").json()["status"] == "ready":
                break
            time.sleep(0.02)
        assert restarted.get(f"/api/documents/{doc_id}").json()["status"] == "ready"
        assert restarted.get(f"/api/documents/{doc_id}/summary").json()["status"] == "error"

def test_cancel_endpoint_restores_previous_summary(client):
    doc_id = upload(client)
    with Session(engine) as session:
        session.add(Generation(doc_id=doc_id, kind="summary", status="done", data='{"ok": 1}')); session.commit()
        session.add(Generation(doc_id=doc_id, kind="summary", status="running")); session.commit()
    assert client.post(f"/api/documents/{doc_id}/summary/cancel").status_code == 204
    result = client.get(f"/api/documents/{doc_id}/summary").json()
    assert result["status"] == "done" and result["data"] == {"ok": 1}
