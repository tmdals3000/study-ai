from app.grounding import find_quote

PAGES = {
    3: "이 방식은 대규모 데이터에는\n권장하지 않는다.",
    4: "• 스택은 데이터를 한쪽 끝(top)에서만 삽입하고 삭\n-제하는 선형 자료구조이다.",
    5: "원형 큐에서 인덱스는 (index + 1) % capacity 로 계산한다.",
}


def test_negation_is_not_matched():
    # 리뷰에서 재현된 사례: 몇 글자 차이로 의미가 뒤집히는 인용은 거부해야 한다
    assert find_quote("이 방식은 대규모 데이터에는 권장한다.", PAGES) is None


def test_exact_quote_matches_despite_pdf_line_breaks_and_bullets():
    assert find_quote("스택은 데이터를 한쪽 끝(top)에서만 삽입하고 삭제하는 선형 자료구조이다.", PAGES) == 4


def test_matched_page_overrides_claimed_page():
    assert find_quote("(index + 1) % capacity 로 계산한다", PAGES, prefer=3) == 5


def test_math_symbols_are_significant():
    assert find_quote("(index - 1) % capacity 로 계산한다", PAGES) is None


def test_too_short_quote_is_rejected():
    assert find_quote("한다.", PAGES) is None
