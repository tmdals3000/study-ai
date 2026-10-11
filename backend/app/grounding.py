"""Formatting normalization only: fuzzy matching can reverse negation or numbers."""
import re
import unicodedata
MIN_QUOTE_CHARS = 6
# 그림 판독 결과는 페이지 원문 뒤에 이 표시와 함께 붙는다. 인용이 이 뒤에서만 발견되면 "그림 근거"로 표시한다.
FIGURE_MARKER = "[그림에서 읽은 내용]"

def page_source(text: str, figure_text: str | None) -> str:
    """생성·검색에 쓰는 페이지 근거 텍스트: 추출 원문 + (있으면) 검증된 그림 판독 내용."""
    return f"{text}\n\n{FIGURE_MARKER}\n{figure_text}" if figure_text else text

_TRANS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", "\u00ad": None})

def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(_TRANS)
    # 줄 맨 앞 글머리표("- ", "• " 등 뒤에 공백)는 원문·인용 양쪽에서 지운다.
    # 아래 하이픈 연결 규칙이 원문 쪽 "\n- 항목"의 하이픈만 지워, "- 항목"으로 시작하는 인용이 탈락하던 문제 방지.
    value = re.sub(r"(^|\n)[ \t]*[-•·▪◦][ \t]+", r"\1", value)
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    value = re.sub(r"(?<=[가-힣])\s*\n\s*-\s*(?=[가-힣])", "", value)
    return re.sub(r"\s+", "", value)

def find_quote(quote: str, pages: dict[int, str], prefer: int | None = None) -> int | None:
    query = normalize(quote)
    if len(query) < MIN_QUOTE_CHARS:
        return None
    for page in sorted(pages, key=lambda n: n != prefer):
        if query in normalize(pages[page]):
            return page
    return None

def match_evidence(evidence: list[dict], pages: dict[int, str]) -> list[dict]:
    result = []
    for item in evidence:
        page = find_quote(item["quote"], pages, item["page"])
        if page is not None:
            entry = {"page": page, "quote": item["quote"].strip()}
            body, _, figure = pages[page].partition(FIGURE_MARKER)
            if figure and normalize(item["quote"]) not in normalize(body):
                entry["figure"] = True
            result.append(entry)
    return result
