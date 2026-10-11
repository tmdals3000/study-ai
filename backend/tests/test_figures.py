import json
import fitz
from sqlmodel import Session, select
from app import llm
from app.config import PAGE_IMAGE_DIR, UPLOAD_DIR
from app.db import engine
from app.generators import figures
from app.grounding import match_evidence, page_source
from app.ingest import extract_text
from app.models import Chunk, Document, Generation, Page

def png(width, height, color=(200, 30, 30)):
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
    pix.set_rect(pix.irect, color)
    return pix.tobytes("png")

def test_spacing_encoded_only_as_glyph_gaps_is_restored():
    # beamer/kotex PDF처럼 공백 문자 없이 글자 위치로만 띄어쓰기를 표현한 줄
    doc = fitz.open()
    page = doc.new_page()
    writer = fitz.TextWriter(page.rect)
    font = fitz.Font("cjk")
    _, end = writer.append((72, 100), "사용자가", font=font, fontsize=10)
    writer.append((end.x + 3.3, 100), "자연어로", font=font, fontsize=10)
    writer.write_text(page)
    assert "사용자가자연어로" in page.get_text().replace("\n", "")  # 기존 추출: 띄어쓰기 손실
    assert "사용자가 자연어로" in extract_text(page)

def test_figure_pages_skip_repeated_logo_and_tiny_icons(tmp_path):
    doc = fitz.open()
    logo = png(300, 100)
    for i in range(4):
        page = doc.new_page()
        page.insert_image(fitz.Rect(10, 10, 60, 27), stream=logo)  # 모든 페이지에 반복되는 로고
        page.insert_text((72, 100), f"page {i + 1}")
    doc[1].insert_image(fitz.Rect(100, 200, 500, 500), stream=png(400, 300, (10, 120, 200)))  # 실제 그림
    doc[2].insert_image(fitz.Rect(100, 200, 112, 212), stream=png(12, 12, (0, 0, 0)))  # 작은 아이콘
    path = tmp_path / "f.pdf"
    doc.save(path)
    assert figures.figure_pages(path) == [2]

def test_figure_reading_keeps_only_verified_items_and_feeds_generation(client, monkeypatch):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Medical AI overview")
    page.insert_image(fitz.Rect(72, 120, 500, 500), stream=png(400, 300))
    content = pdf.tobytes()
    doc_id = client.post("/api/documents", files={"file": ("fig.pdf", content, "application/pdf")}).json()["id"]
    calls = []

    def fake(prompt, *, schema=None, images=None, **kwargs):
        assert images and images[0].startswith(b"\x89PNG")  # 페이지 이미지가 실제로 전달됨
        calls.append(schema)
        if "figures" in schema["properties"]:
            return {"figures": [{"caption": "Watson diagnosis", "texts": ["Patient data", "Invented label"],
                                 "structure": ["Patient data → Diagnosis arrow"]}]}
        ids = [item["id"] for item in json.loads(prompt[prompt.index("["):])]
        return {"verdicts": [{"id": i, "verdict": "unsupported" if i == "f0-t1" else "supported", "issues": "", "corrected": ""} for i in ids]}

    monkeypatch.setattr(llm, "generate", fake)
    assert client.post(f"/api/documents/{doc_id}/generate/figures", json={}).status_code == 202
    job = client.get(f"/api/documents/{doc_id}/generations/figures").json()
    assert job["status"] == "done", job
    assert job["data"] == {"pages": 1, "pages_with_figures": 1, "generated": 4, "kept": 3}
    assert len(calls) == 2  # 판독 1회 + 이미지 대조 검증 1회

    with Session(engine) as session:
        stored = session.exec(select(Page).where(Page.doc_id == doc_id)).one()
        assert "Patient data" in stored.figure_text and "Patient data → Diagnosis arrow" in stored.figure_text
        assert "Invented label" not in stored.figure_text  # 검증 실패 항목은 저장 안 함
        chunks = " ".join(c.text for c in session.exec(select(Chunk).where(Chunk.doc_id == doc_id)).all())
        assert "Patient data" in chunks  # 퀴즈·튜터 검색 근거에도 포함
        source = {1: page_source(stored.text, stored.figure_text)}
    evidence = match_evidence([{"page": 1, "quote": "Patient data → Diagnosis arrow"},
                               {"page": 1, "quote": "Medical AI overview"}], source)
    assert evidence[0].get("figure") is True and "figure" not in evidence[1]

    # 다시 처리(retry)해도 판독 결과는 유지된다
    assert client.post(f"/api/documents/{doc_id}/retry").status_code == 200
    with Session(engine) as session:
        assert "Patient data" in session.exec(select(Page).where(Page.doc_id == doc_id)).one().figure_text

def test_page_image_is_rendered_cached_and_removed_with_document(client):
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "hello")
    doc_id = client.post("/api/documents", files={"file": ("p.pdf", pdf.tobytes(), "application/pdf")}).json()["id"]
    response = client.get(f"/api/documents/{doc_id}/pages/1/image")
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    assert (PAGE_IMAGE_DIR / str(doc_id) / "1.png").is_file()
    assert client.get(f"/api/documents/{doc_id}/pages/2/image").status_code == 404
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert not (PAGE_IMAGE_DIR / str(doc_id)).exists()

def test_cli_sends_images_as_stream_json(monkeypatch):
    captured = {}

    class FakeProcess:
        returncode = 0
        def __init__(self, args, **kwargs):
            captured["args"] = args
        def communicate(self, input=None, timeout=None):
            captured["input"] = input
            result = {"type": "result", "is_error": False, "result": "", "structured_output": {"ok": True}}
            return '{"type":"system"}\n' + json.dumps(result) + "\n", ""
        def poll(self):
            return 0

    monkeypatch.setattr(llm.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(llm.subprocess, "Popen", FakeProcess)
    out = llm._claude_cli("read", None, {"type": "object"}, "sonnet", 30, images=[b"\x89PNGdata"])
    assert out == {"ok": True}
    assert captured["args"][captured["args"].index("--input-format") + 1] == "stream-json"
    message = json.loads(captured["input"])
    assert [block["type"] for block in message["message"]["content"]] == ["image", "text"]
