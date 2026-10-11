from app.generators.summary import split_sections


def test_long_page_is_split_under_limit():
    # 리뷰에서 재현된 사례: 13,000자 페이지가 12,000자 제한을 넘던 문제
    text = "".join(f"{i:05d} 줄의 내용입니다. 스택과 큐.\n" for i in range(600))
    assert len(text) > 13000
    sections = split_sections([(1, "짧은 페이지"), (2, text), (3, "마지막")], limit=12000)
    for sec in sections:
        assert sum(len(t) for _, t in sec) <= 12000
    pieces = [p for sec in sections for p in sec]
    assert "".join(t for n, t in pieces if n == 2) == text  # 내용 손실 없음, 페이지 번호 유지
    assert [n for n, _ in pieces][0] == 1 and [n for n, _ in pieces][-1] == 3


def test_single_line_longer_than_limit_is_hard_cut():
    text = "가" * 25000
    sections = split_sections([(7, text)], limit=12000)
    assert all(sum(len(t) for _, t in sec) <= 12000 for sec in sections)
    assert "".join(t for sec in sections for _, t in sec) == text


def test_small_pages_are_grouped():
    sections = split_sections([(1, "a" * 100), (2, "b" * 100)], limit=12000)
    assert len(sections) == 1


def test_section_title_must_appear_in_source():
    from app.generators.summary import section_title
    pages = [(2, "1. 스택 (Stack)\n스택은 LIFO 구조이다."), (3, "2. 큐")]
    assert section_title("1. 스택 (Stack)", pages) == "1. 스택 (Stack)"
    assert section_title("스택과 큐의 모든 것", pages) == "p.2–3 구간"  # 원문에 없는 제목은 쓰지 않음
    assert section_title("x", [(4, "x")]) == "p.4 구간"
