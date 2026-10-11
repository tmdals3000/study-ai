"""Map/reduce with exact quotations and independently scoped evidence verification."""
import json
from sqlmodel import Session, select
from .. import llm
from ..config import MAX_SECTION_CHARS, MODEL_GENERATE
from ..db import engine
from ..grounding import match_evidence, normalize
from ..jobs import checkpoint, update_job
from ..models import Document, Generation, Page
from ..prompts import load_prompt
from ..retrieval import split_text
from ..schemas import obj, string, array, EVIDENCE
from .mindmap import build_mindmap
from .verify import verify_scoped

KINDS = ["정의", "원리", "절차", "예시", "비교", "수식", "특징", "기타"]
MAP_SCHEMA = obj({"title": string(200), "points": array(obj({
    "heading": string(200), "kind": {"type": "string", "enum": KINDS},
    "content": string(2000), "evidence": EVIDENCE}), 0, 50)})
REFS = array(string(100), 1, 20)
REDUCE_SCHEMA = obj({
    "one_line": obj({"text": string(1500), "based_on": REFS}),
    "key_concepts": array(obj({"name": string(200), "description": string(1500), "based_on": REFS}), 0, 12),
    "exam_points": array(obj({"text": string(1500), "based_on": REFS}), 0, 10)})

def _split_long_text(text, limit):
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return parts

def split_sections(pages, limit=MAX_SECTION_CHARS):
    fragments = [(number, part) for number, text in pages for part in _split_long_text(text, limit)]
    sections, current, size = [], [], 0
    for fragment in fragments:
        if current and size + len(fragment[1]) > limit:
            sections.append(current)
            current, size = [], 0
        current.append(fragment)
        size += len(fragment[1])
    if current:
        sections.append(current)
    return sections

def analyze_section(index, title, pages):
    source = "\n".join(f'<page n="{n}">\n{text}\n</page>' for n, text in pages)
    out = llm.generate(load_prompt("summary_map", TITLE=title, FIRST=str(pages[0][0]), LAST=str(pages[-1][0]), SECTION=source),
                       system=load_prompt("system_grounded"), schema=MAP_SCHEMA, model=MODEL_GENERATE)
    page_text = {}
    for number, text in pages:
        page_text[number] = page_text.get(number, "") + "\n" + text
    stats = {"generated": len(out["points"]), "no_evidence": 0, "unsupported": 0, "corrected": 0}
    candidates = []
    for i, item in enumerate(out["points"]):
        evidence = match_evidence(item["evidence"], page_text)
        if not evidence:
            stats["no_evidence"] += 1
            continue
        candidates.append({**item, "id": f"s{index + 1}-p{i + 1}", "evidence": evidence,
                           "pages": sorted({e["page"] for e in evidence}), "corrected": False})
    verdicts = verify_scoped({p["id"]: (p["heading"] + "\n" + p["content"], "\n".join(e["quote"] for e in p["evidence"])) for p in candidates})
    kept = [p for p in candidates if verdicts.get(p["id"], {}).get("verdict") == "supported"]
    stats["unsupported"] = len(candidates) - len(kept)
    return {"title": section_title(out["title"], pages), "pages": [pages[0][0], pages[-1][0]], "points": kept}, stats

def section_title(proposed, pages):
    """모델이 제안한 제목은 원문에 그대로 있는 헤딩일 때만 쓰고, 아니면 페이지 범위로 표시한다."""
    if len(normalize(proposed)) >= 2 and normalize(proposed) in normalize("\n".join(text for _, text in pages)):
        return proposed.strip()
    first, last = pages[0][0], pages[-1][0]
    return f"p.{first} 구간" if first == last else f"p.{first}–{last} 구간"

def _overall_batch(title, points):
    notes = "\n\n".join(f'<note id="{key}">\n{p["heading"]}: {p["content"]}\n</note>' for key, p in points.items())
    out = llm.generate(load_prompt("summary_reduce", TITLE=title, NOTES=notes),
                       system=load_prompt("system_grounded"), schema=REDUCE_SCHEMA, model=MODEL_GENERATE)
    items = {"one_line": out["one_line"]}
    items.update({f"kc-{i}": {"name": x["name"], "text": x["description"], "based_on": x["based_on"]} for i, x in enumerate(out["key_concepts"])})
    items.update({f"ex-{i}": x for i, x in enumerate(out["exam_points"])})
    items = {key: value for key, value in items.items() if value["based_on"] and all(ref in points for ref in value["based_on"])}
    scoped = {key: (value.get("name", "") + "\n" + value["text"],
                   "\n".join(points[ref]["heading"] + ": " + points[ref]["content"] for ref in value["based_on"]))
              for key, value in items.items()}
    verdicts = verify_scoped(scoped)
    result = {"one_line": None, "key_concepts": [], "exam_points": []}
    for key, item in items.items():
        if verdicts.get(key, {}).get("verdict") != "supported":
            continue
        pages = sorted({n for ref in item["based_on"] for n in points[ref]["pages"]})
        if key == "one_line":
            result["one_line"] = {"text": item["text"], "pages": pages}
        elif key.startswith("kc-"):
            result["key_concepts"].append({"name": item["name"], "description": item["text"], "pages": pages})
        else:
            result["exam_points"].append({"text": item["text"], "pages": pages})
    return result

def summarize_overall(title, sections):
    points = {p["id"]: p for section in sections for p in section["points"]}
    if not points:
        return {"one_line": None, "key_concepts": [], "exam_points": []}
    groups, group, size = [], {}, 0
    for key, point in points.items():
        length = len(point["heading"]) + len(point["content"]) + 100
        if group and size + length > 24000:
            groups.append(group)
            group, size = {}, 0
        group[key], size = point, size + length
    groups.append(group)
    results = [_overall_batch(title, group) for group in groups]
    if len(results) == 1:
        return results[0]
    condensed = []
    for i, result in enumerate(results):
        entries = ([result["one_line"]] if result["one_line"] else [])
        entries += [{"text": c["name"] + ": " + c["description"], "pages": c["pages"]} for c in result["key_concepts"]]
        entries += result["exam_points"]
        condensed += [{"id": f"r-{i}-{j}", "heading": "검증된 요약", "content": item["text"], "pages": item["pages"]} for j, item in enumerate(entries)]
    # Guarantee a strict reduction at every recursion level.
    if len(condensed) >= len(points):
        condensed = [{"id": f"r-{i}", "heading": "구간 요약", "content": r["one_line"]["text"], "pages": r["one_line"]["pages"]} for i, r in enumerate(results) if r["one_line"]]
    return summarize_overall(title, [{"points": condensed}])

def run_summary(job_id):
    with Session(engine) as session:
        job = session.get(Generation, job_id)
        if not job:
            return
        doc = session.get(Document, job.doc_id)
        if not doc:
            return
        title = doc.title
        pages = [(p.page_no, p.text) for p in session.exec(select(Page).where(Page.doc_id == job.doc_id).order_by(Page.page_no)).all() if p.text.strip()]
    if not pages:
        raise ValueError("추출된 텍스트가 없습니다. 스캔본은 OCR 설정 후 다시 처리해 주세요.")
    sections, stats = [], {"generated": 0, "no_evidence": 0, "unsupported": 0, "corrected": 0}
    chunks = split_sections(pages)
    for i, chunk in enumerate(chunks):
        checkpoint()
        update_job(job_id, progress=f"구간 분석·검증 중 ({i}/{len(chunks)})")
        section, counts = analyze_section(i, title, chunk)
        sections.append(section)
        for key in stats:
            stats[key] += counts[key]
    update_job(job_id, progress="전체 요약 생성·검증 중")
    summary = {"title": title, **summarize_overall(title, sections), "sections": sections}
    stats["kept"] = sum(len(s["points"]) for s in sections)
    summary["stats"] = stats
    summary["mindmap"] = build_mindmap(summary)
    update_job(job_id, status="done", progress=None, data=json.dumps(summary, ensure_ascii=False))
