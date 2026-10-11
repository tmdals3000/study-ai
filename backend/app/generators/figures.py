"""그림 판독: 그림이 있는 페이지를 이미지로 보고 그림 속 글자·구조를 옮겨 적는다 (환각 방지).

1. 판독  : 페이지 이미지 + 이미 추출된 텍스트를 주고, 그림 속 글자(그대로)와 눈에 보이는 관계만 적게 한다.
2. 검증  : 별도 호출에서 같은 이미지와 항목을 대조해, 이미지에서 직접 확인되는 항목만 남긴다.
3. 저장  : 통과한 내용만 Page.figure_text에 저장하고 검색 청크를 다시 만든다.
           이후 요약·퀴즈·카드·튜터는 이 내용을 원문과 같은 방식(정확 인용 + 검증)으로 근거로 쓴다.
취소·실패 시 기존 판독 결과는 바뀌지 않는다.
"""
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

import fitz
from sqlmodel import Session, select

from .. import llm
from ..config import LLM_PARALLEL, MODEL_GENERATE, MODEL_VERIFY, UPLOAD_DIR
from ..db import engine
from ..grounding import page_source
from ..jobs import JobStopped, checkpoint, lock, update_job
from ..models import Document, Generation, Page
from ..prompts import load_prompt
from ..retrieval import index_pages
from ..schemas import array, obj
from .verify import VERIFY_SCHEMA

_TEXT = {"type": "string", "maxLength": 500}
FIGURE_SCHEMA = obj({"figures": array(obj({
    "caption": {"type": "string", "maxLength": 300},
    "texts": array(_TEXT, 0, 60),
    "structure": array(_TEXT, 0, 20)}), 0, 8)})

RENDER_ZOOM = 2.0  # 슬라이드(약 450pt 폭) 기준 약 900px. 작은 글자도 읽히는 정도.
MIN_FIGURE_AREA = 0.03  # 페이지 면적 대비 이보다 작은 이미지는 아이콘·로고로 본다
MIN_DRAWINGS = 12  # 벡터 도형이 이만큼 있으면 다이어그램으로 본다


def render_png(path, page_no: int, zoom: float = RENDER_ZOOM) -> bytes:
    with fitz.open(path) as pdf:
        return pdf[page_no - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")


def figure_pages(path) -> list[int]:
    """그림이 있는 페이지 번호. 여러 페이지에 반복되는 이미지(배경·로고)와 작은 아이콘은 제외한다."""
    with fitz.open(path) as pdf:
        usage = Counter(xref for page in pdf for xref in {img[0] for img in page.get_images(full=True)})
        repeated = {xref for xref, n in usage.items() if n >= max(3, pdf.page_count * 0.3)}
        result = []
        for page in pdf:
            area = page.rect.width * page.rect.height
            images = [i for i in page.get_image_info(xrefs=True)
                      if i["xref"] not in repeated and fitz.Rect(i["bbox"]).get_area() >= area * MIN_FIGURE_AREA]
            if images or len(page.get_drawings()) >= MIN_DRAWINGS:
                result.append(page.number + 1)
        return result


def read_page(title: str, page_no: int, text: str, image: bytes) -> tuple[str | None, dict]:
    """한 페이지를 판독·검증해 (저장할 텍스트 또는 None, 통계)를 반환한다."""
    out = llm.generate(load_prompt("figures_read", TITLE=title, PAGE=str(page_no), TEXT=text.strip() or "(없음)"),
                       system=load_prompt("system_grounded"), schema=FIGURE_SCHEMA, model=MODEL_GENERATE, images=[image])
    items: dict[str, str] = {}
    for f, figure in enumerate(out["figures"]):
        if figure["caption"].strip():
            items[f"f{f}-c"] = figure["caption"].strip()
        for t, value in enumerate(figure["texts"]):
            if value.strip():
                items[f"f{f}-t{t}"] = value.strip()
        for r, value in enumerate(figure["structure"]):
            if value.strip():
                items[f"f{f}-s{r}"] = value.strip()
    stats = {"generated": len(items), "kept": 0}
    if not items:
        return None, stats
    checkpoint()
    payload = [{"id": key, "kind": "구조" if "-s" in key else "텍스트", "claim": value} for key, value in items.items()]
    verdicts = llm.generate(load_prompt("figures_verify", ITEMS=json.dumps(payload, ensure_ascii=False)),
                            system=load_prompt("system_grounded"), schema=VERIFY_SCHEMA, model=MODEL_VERIFY,
                            images=[image])["verdicts"]
    counts = Counter(v["id"] for v in verdicts)
    supported = {v["id"] for v in verdicts if v["verdict"] == "supported" and counts[v["id"]] == 1}

    blocks = []
    for f, figure in enumerate(out["figures"]):
        caption = items.get(f"f{f}-c") if f"f{f}-c" in supported else None
        texts = [items[k] for k in (f"f{f}-t{t}" for t in range(len(figure["texts"]))) if k in supported]
        structure = [items[k] for k in (f"f{f}-s{r}" for r in range(len(figure["structure"]))) if k in supported]
        if not (caption or texts or structure):
            continue
        lines = [f"그림: {caption}" if caption else "그림:"]
        lines += [f"- {value}" for value in texts]
        lines += [f"· {value}" for value in structure]
        blocks.append("\n".join(lines))
    stats["kept"] = len(supported & set(items))
    return ("\n\n".join(blocks) or None), stats


def run_figures(job_id: int) -> None:
    with Session(engine) as session:
        job = session.get(Generation, job_id)
        doc = session.get(Document, job.doc_id) if job else None
        if not job or not doc:
            raise JobStopped()
        doc_id, title, path = doc.id, doc.title, UPLOAD_DIR / doc.filename
        texts = {p.page_no: p.text for p in session.exec(select(Page).where(Page.doc_id == doc_id)).all()}
    targets = [n for n in figure_pages(path) if n in texts]
    update_job(job_id, progress=f"그림 판독·검증 중 (0/{len(targets)}페이지)")

    results: dict[int, str | None] = {}
    stats = {"pages": len(targets), "pages_with_figures": 0, "generated": 0, "kept": 0}

    def work(page_no):
        checkpoint()
        return page_no, read_page(title, page_no, texts[page_no], render_png(path, page_no))

    # 작업 취소(checkpoint)가 하위 스레드에서도 동작하도록 현재 컨텍스트를 복사해 실행한다
    with ThreadPoolExecutor(max_workers=LLM_PARALLEL) as pool:
        futures = [pool.submit(copy_context().run, work, n) for n in targets]
        try:
            for done, future in enumerate(futures, 1):
                page_no, (figure_text, page_stats) = future.result()
                results[page_no] = figure_text
                stats["generated"] += page_stats["generated"]
                stats["kept"] += page_stats["kept"]
                stats["pages_with_figures"] += figure_text is not None
                update_job(job_id, progress=f"그림 판독·검증 중 ({done}/{len(targets)}페이지)")
        except BaseException:
            for future in futures:
                future.cancel()
            raise

    checkpoint()
    with lock, Session(engine) as session:
        job = session.get(Generation, job_id)
        if not job or job.status not in ("queued", "running"):
            raise JobStopped()
        pages = session.exec(select(Page).where(Page.doc_id == doc_id).order_by(Page.page_no)).all()
        for page in pages:
            page.figure_text = results.get(page.page_no)
            session.add(page)
        index_pages(session, doc_id, [(p.page_no, page_source(p.text, p.figure_text)) for p in pages])
        job.status, job.progress = "done", None
        job.data = json.dumps(stats, ensure_ascii=False)
        session.add(job)
        session.commit()
