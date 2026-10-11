import fitz
from sqlmodel import Session, delete, select
from .config import UPLOAD_DIR, MAX_PDF_PAGES, OCR_ENABLED, OCR_LANGUAGES
from .db import engine
from .grounding import page_source
from .models import Document, Page
from .retrieval import index_pages

# 글자 사이 간격이 글꼴 크기의 이 비율보다 크면 띄어쓰기로 본다.
# LaTeX(beamer/kotex) 등으로 만든 PDF는 공백 문자 없이 글자 위치만으로 띄어쓰기를 표현한다.
SPACE_GAP = 0.2
# PDF 내부 순서를 그대로 쓴다. 위치 정렬은 2단 레이아웃의 두 단을 한 줄씩 섞어 버린다.
SORT_BLOCKS = False


def extract_text(page: fitz.Page) -> str:
    """PyMuPDF 텍스트 추출 + 공백 문자 없이 간격으로만 표현된 띄어쓰기 복원."""
    lines = []
    for block in page.get_text("rawdict", sort=SORT_BLOCKS)["blocks"]:
        for line in block.get("lines", []):
            horizontal = abs(line["dir"][1]) < 0.1
            out, prev, prev_size = [], None, 0.0
            for span in line["spans"]:
                for char in span["chars"]:
                    c = char["c"]
                    if horizontal and prev is not None and not c.isspace() and not prev["c"].isspace():
                        if char["bbox"][0] - prev["bbox"][2] > SPACE_GAP * max(span["size"], prev_size):
                            out.append(" ")
                    out.append(c)
                    prev, prev_size = char, span["size"]
            lines.append("".join(out))
    return "\n".join(lines) + ("\n" if lines else "")


def ingest_pdf(doc_id: int) -> None:
    with Session(engine) as session:
        doc = session.get(Document, doc_id)
        if doc is None:
            return
        try:
            extracted = []
            with fitz.open(UPLOAD_DIR / doc.filename) as pdf:
                if pdf.needs_pass:
                    raise ValueError("암호가 걸린 PDF입니다. 암호를 해제한 파일을 올려 주세요.")
                if not 0 < pdf.page_count <= MAX_PDF_PAGES:
                    raise ValueError(f"PDF는 1~{MAX_PDF_PAGES}페이지까지 지원합니다.")
                for number, page in enumerate(pdf, 1):
                    text = extract_text(page)
                    if OCR_ENABLED and (len(text.strip()) < 30 or text.count("�") > 5):
                        textpage = page.get_textpage_ocr(language=OCR_LANGUAGES, dpi=150, full=True)
                        text = page.get_text("text", textpage=textpage, sort=True)
                    extracted.append((number, text))
            # 다시 처리해도 같은 파일이므로 이미 판독한 그림 내용은 유지한다
            figures = {p.page_no: p.figure_text for p in session.exec(select(Page).where(Page.doc_id == doc_id)).all() if p.figure_text}
            session.exec(delete(Page).where(Page.doc_id == doc_id))
            for number, text in extracted:
                session.add(Page(doc_id=doc_id, page_no=number, text=text, figure_text=figures.get(number)))
            index_pages(session, doc_id, [(n, page_source(t, figures.get(n))) for n, t in extracted])
            doc.pages, doc.status, doc.error = len(extracted), "ready", None
            session.add(doc)
            session.commit()
        except Exception as exc:
            session.rollback()
            doc = session.get(Document, doc_id)
            if doc:
                doc.status, doc.error = "error", str(exc)[:1500]
                session.add(doc)
                session.commit()
