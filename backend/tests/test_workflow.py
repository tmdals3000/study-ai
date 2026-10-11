import io
import json
import sqlite3
import threading
import zipfile
from datetime import datetime, timezone
import fitz
import pytest
from sqlmodel import Session, select
from app import jobs, llm
from app.db import engine, init_db
from app.grounding import find_quote
from app.generators.summary import split_sections, _overall_batch
from app.generators import summary as summary_module
from app.models import Card, Document, Generation, Page, Question
from app.retrieval import retrieve
from app.srs import review
from fake_llm import TEXT, respond

def pdf_bytes():
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((50, 60), TEXT)
    data = pdf.tobytes()
    pdf.close()
    return data

def upload(client):
    result = client.post("/api/documents", files={"file": ("lecture.pdf", pdf_bytes(), "application/pdf")})
    assert result.status_code == 201, result.text
    return result.json()["id"]

@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(llm, "_claude_cli", respond)

def test_quote_does_not_accept_negation_or_number_changes():
    assert find_quote("The treatment is recommended for all patients.", {1: "The treatment is not recommended for all patients."}) is None
    assert find_quote("The dose is 100 milligrams.", {1: "The dose is 900 milligrams."}) is None
    assert find_quote("Water freezes at zero degrees Celsius.", {2: "Water freezes\nat zero degrees Celsius."}, 1) == 2

def test_long_page_is_bounded_without_losing_content():
    text = "x" * 25001
    sections = split_sections([(7, text)])
    assert all(sum(len(t) for _, t in section) <= 12000 for section in sections)
    assert "".join(t for section in sections for _, t in section) == text
    assert {n for section in sections for n, _ in section} == {7}

def test_summary_checks_only_claimed_notes(monkeypatch):
    points = {"a": {"heading": "Water", "content": "Water freezes.", "pages": [1]},
              "b": {"heading": "Earth", "content": "Earth orbits the Sun.", "pages": [2]}}
    monkeypatch.setattr(llm, "generate", lambda *a, **k: {"one_line": {"text": "Earth orbits the Sun.", "based_on": ["a"]}, "key_concepts": [], "exam_points": []})
    def verify(items):
        assert "Earth" not in items["one_line"][1]
        return {"one_line": {"verdict": "unsupported"}}
    monkeypatch.setattr(summary_module, "verify_scoped", verify)
    assert _overall_batch("test", points)["one_line"] is None

def test_full_workflow_and_backup(client, fake):
    doc_id = upload(client)
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["status"] == "ready"
    assert client.get(f"/api/documents/{doc_id}/pages").json()[0]["page_no"] == 1
    with Session(engine) as session:
        assert retrieve(session, doc_id, "water freezes")[0]["page"] == 1
    for kind in ("summary", "quiz", "cards"):
        response = client.post(f"/api/documents/{doc_id}/generate/{kind}", json={"count": 3})
        assert response.status_code == 202, response.text
        result = client.get(f"/api/documents/{doc_id}/generations/{kind}").json()
        assert result["status"] == "done", result
        assert client.post(f"/api/documents/{doc_id}/generate/{kind}", json={}).json()["id"] == result["id"]
    summary = client.get(f"/api/documents/{doc_id}/summary").json()["data"]
    assert summary["stats"]["kept"] == 1 and summary["mindmap"]
    questions = client.get(f"/api/documents/{doc_id}/questions").json()
    assert len(questions) == 3 and "answer" not in questions[0]
    answer = client.post(f"/api/questions/{questions[0]['id']}/answer", json={"answer": "10 C"}).json()
    assert answer["correct"] is False and answer["answer"] == "0 C"
    assert len(client.get(f"/api/documents/{doc_id}/questions?wrong_only=true").json()) == 1
    assert client.post(f"/api/questions/{questions[0]['id']}/answer", json={"answer": "0 C"}).json()["correct"]
    assert not client.get(f"/api/documents/{doc_id}/questions?wrong_only=true").json()
    card = client.get("/api/cards?due_only=true").json()[0]
    edited = client.patch(f"/api/cards/{card['id']}", json={"front": "Edited question", "back": card["back"], "version": card["version"]}).json()
    assert edited["edited"] and edited["version"] == 1
    rated = client.post(f"/api/cards/{card['id']}/review", json={"rating": 3, "version": 1})
    assert rated.status_code == 200, rated.text
    assert datetime.fromisoformat(rated.json()["due_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc)
    assert client.post(f"/api/cards/{card['id']}/review", json={"rating": 3, "version": 1}).status_code == 409
    chat = client.post(f"/api/documents/{doc_id}/chat", json={"question": "When does water freeze?", "mode": "explain"})
    assert chat.status_code == 200 and "event: message" in chat.text, chat.text
    messages = client.get(f"/api/documents/{doc_id}/messages").json()
    assert len(messages) == 2 and messages[-1]["citations"][0]["page"] == 1
    archive = client.get("/api/backup")
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        assert "study.db" in bundle.namelist()
        assert any(name.startswith("uploads/") for name in bundle.namelist())
        assert not any(".env" in name or "secret" in name for name in bundle.namelist())
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get("/api/cards").json() == []
    assert client.get(f"/api/documents/{doc_id}/pages").status_code == 404

def test_invalid_uploads_and_size_limit(client, monkeypatch):
    from app import main
    assert client.post("/api/documents", files={"file": ("x.pdf", b"fake")}).status_code == 400
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
    assert client.post("/api/documents", files={"file": ("x.pdf", pdf_bytes())}).status_code == 413
    assert client.get("/api/documents").json() == []

def test_cancel_delete_and_restart(client, monkeypatch):
    doc_id = upload(client)
    monkeypatch.setattr(jobs, "submit", lambda *args: None)
    first = client.post(f"/api/documents/{doc_id}/generate/summary").json()
    second = client.post(f"/api/documents/{doc_id}/generate/summary").json()
    assert first["id"] == second["id"]
    assert client.delete(f"/api/documents/{doc_id}").status_code == 409
    assert client.post(f"/api/generations/{first['id']}/cancel").status_code == 200
    with pytest.raises(jobs.JobStopped):
        jobs.update_job(first["id"], status="done")
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    with pytest.raises(jobs.JobStopped):
        jobs.update_job(first["id"], status="done")
    doc_id = upload(client)
    with Session(engine) as session:
        doc = session.get(Document, doc_id); doc.status = "processing"; session.add(doc)
        session.add(Generation(doc_id=doc_id, kind="quiz", status="running")); session.commit()
    init_db()
    assert client.get(f"/api/documents/{doc_id}").json()["status"] == "error"
    assert client.get(f"/api/documents/{doc_id}/generations/quiz").json()["status"] == "error"

def test_schema_validation_and_missing_verdict_fail_closed(client, monkeypatch):
    monkeypatch.setattr(llm, "_claude_cli", lambda *args: {"unexpected": True})
    with pytest.raises(llm.LLMError):
        llm.generate("test", schema={"type": "object", "required": ["expected"]}, retries=0)
    from app.generators.verify import verify_scoped
    monkeypatch.setattr(llm, "_claude_cli", lambda *args: {"verdicts": []})
    assert verify_scoped({"a": ("claim", "source")}) == {}

def test_auth_and_cross_origin_requests(client, monkeypatch):
    from app import auth, main
    assert client.post("/api/llm/ping", headers={"Origin": "https://other.example"}).status_code == 403
    monkeypatch.setattr(auth, "APP_PASSWORD", "test-password")
    monkeypatch.setattr(main, "APP_PASSWORD", "test-password")
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/auth/login", json={"password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "test-password"}).status_code == 200
    assert client.get("/api/documents").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/documents").status_code == 401
