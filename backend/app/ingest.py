import fitz
from sqlmodel import Session, delete
from .config import UPLOAD_DIR, MAX_PDF_PAGES, OCR_ENABLED, OCR_LANGUAGES
from .db import engine
from .models import Document, Page
from .retrieval import index_pages

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
                    text = page.get_text("text", sort=True)
                    if OCR_ENABLED and (len(text.strip()) < 30 or text.count("�") > 5):
                        textpage = page.get_textpage_ocr(language=OCR_LANGUAGES, dpi=150, full=True)
                        text = page.get_text("text", textpage=textpage, sort=True)
                    extracted.append((number, text))
            session.exec(delete(Page).where(Page.doc_id == doc_id))
            for number, text in extracted:
                session.add(Page(doc_id=doc_id, page_no=number, text=text))
            index_pages(session, doc_id, extracted)
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
