"""요약 파이프라인을 가짜 LLM으로 검증한다 (claude 호출 없음)."""
import json
import re

import pytest
from sqlmodel import Session

import app.llm
from app import jobs
from app.db import engine
from app.generators import summary
from app.generators.verify import VERIFY_SCHEMA
from app.models import Document, Generation, Page

MAP_OUT = {
    "title": "스택과 큐",
    "points": [
        {  # 모델이 페이지를 2로 잘못 주장 → 실제 매칭된 1로 교정되어야 함
            "heading": "스택", "kind": "정의", "content": "스택은 LIFO 구조이다.",
            "evidence": [{"quote": "스택은 LIFO 구조이다", "page": 2}],
        },
        {  # 원문에 없는(의미가 뒤집힌) 인용 → 제외되어야 함
            "heading": "큐 오류", "kind": "정의", "content": "큐는 FIFO가 아니다.",
            "evidence": [{"quote": "큐는 FIFO 구조가 아니다", "page": 2}],
        },
        {
            "heading": "큐", "kind": "정의", "content": "큐는 FIFO 구조이다.",
            "evidence": [{"quote": "큐는 FIFO 구조이다", "page": 2}],
        },
    ],
}

REDUCE_OUT = {
    "one_line": {"text": "스택과 큐를 다룬다.", "based_on": ["s1-p1", "s1-p3"]},
    "key_concepts": [
        {"name": "스택", "description": "LIFO 구조", "based_on": ["s1-p1"]},
        {"name": "가짜", "description": "없는 노트를 인용", "based_on": ["s9-p9"]},
    ],
    "exam_points": [{"text": "큐는 FIFO", "based_on": ["s1-p3"]}],
}


def fake_llm(calls: list, on_map=None):
    def generate(prompt, *, system=None, schema=None, model=None, **kw):
        calls.append((schema, prompt))
        if schema is summary.MAP_SCHEMA:
            if on_map:
                on_map()
            return MAP_OUT
        if schema is summary.REDUCE_SCHEMA:
            return REDUCE_OUT
        if schema is VERIFY_SCHEMA:
            ids = re.findall(r'"id":\s*"([^"]+)"', prompt)
            return {"verdicts": [{"id": i, "verdict": "supported", "issues": "", "corrected": ""} for i in ids]}
        raise AssertionError("unexpected schema")

    return generate


@pytest.fixture
def gen_id(client):
    with Session(engine) as s:
        doc = Document(title="자료구조", filename="x.pdf", status="ready", pages=2)
        s.add(doc)
        s.commit()
        s.add_all([
            Page(doc_id=doc.id, page_no=1, text="스택은 LIFO 구조이다."),
            Page(doc_id=doc.id, page_no=2, text="큐는 FIFO 구조이다."),
        ])
        gen = Generation(doc_id=doc.id, kind="summary")
        s.add(gen)
        s.commit()
        return gen.id


def test_pipeline_drops_ungrounded_and_fixes_pages(gen_id, monkeypatch):
    calls = []
    monkeypatch.setattr(app.llm, "generate", fake_llm(calls))
    jobs._run(gen_id, summary.run_summary)

    with Session(engine) as s:
        gen = s.get(Generation, gen_id)
    assert gen.status == "done", gen.error
    data = json.loads(gen.data)

    assert data["stats"]["no_evidence"] == 1
    points = {p["heading"]: p for p in data["sections"][0]["points"]}
    assert set(points) == {"스택", "큐"}
    assert points["스택"]["pages"] == [1]  # 교정된 페이지
    assert points["큐"]["pages"] == [2]

    # 전체 요약: 존재하지 않는 노트를 인용한 항목은 제외, 페이지는 인용 노트 기준
    assert [c["name"] for c in data["key_concepts"]] == ["스택"]
    assert data["key_concepts"][0]["pages"] == [1]
    assert data["exam_points"][0]["pages"] == [2]
    assert data["one_line"]["pages"] == [1, 2]

    # 전체 요약 검증은 각 항목이 인용한 노트만으로 하도록 cites가 전달되어야 한다
    reduce_verify = [p for sch, p in calls if sch is VERIFY_SCHEMA and '"id": "kc-0"' in p]
    assert reduce_verify
    scoped = json.loads(reduce_verify[0][reduce_verify[0].index('[{"id"'):])
    concept_source = next(item["source"] for item in scoped if item["id"] == "kc-0")
    assert "LIFO" in concept_source and "FIFO" not in concept_source


def test_cancel_during_run_stops_quietly(gen_id, monkeypatch):
    def cancel():  # 취소 API와 같은 동작: 작업 행 삭제
        with Session(engine) as s:
            s.delete(s.get(Generation, gen_id))
            s.commit()

    calls = []
    monkeypatch.setattr(app.llm, "generate", fake_llm(calls, on_map=cancel))
    jobs._run(gen_id, summary.run_summary)  # 워커가 취소를 정상 종료로 처리

    with Session(engine) as s:
        assert s.get(Generation, gen_id) is None  # 취소된 작업이 되살아나지 않음
    assert not any(sch is summary.REDUCE_SCHEMA for sch, _ in calls)  # 이후 단계는 실행 안 됨


def test_document_deleted_before_start(gen_id):
    with Session(engine) as s:
        gen = s.get(Generation, gen_id)
        s.delete(gen)
        s.commit()
    summary.run_summary(gen_id)  # 예외 없이 끝나야 한다

