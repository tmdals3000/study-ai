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


def test_quote_starting_with_list_bullet_matches():
    # 회귀: 원문 "\n- 항목"은 하이픈이 지워지고 인용 "- 항목"은 남아 매칭에 실패하던 문제
    page = {59: "그림: 왓슨을 사용한 의료 진단\n- 환자 데이터\n의사 노트,\n각종 테스트 결과\n- 환자 설문"}
    assert find_quote("- 환자 데이터\n의사 노트,\n각종 테스트 결과", page) == 59
    assert find_quote("환자 데이터 의사 노트, 각종 테스트 결과", page) == 59
    assert find_quote("• 환자 설문 응답 내용", {1: "목록\n• 환자 설문 응답 내용"}) == 1


def test_bullet_removal_keeps_negative_numbers():
    assert find_quote("온도는 -20도이다.", {1: "온도는 20도이다."}) is None
    assert find_quote("-20도에서 언다", {1: "목록\n20도에서 언다"}) is None
