"""Formatting normalization only: fuzzy matching can reverse negation or numbers."""
import re
import unicodedata
MIN_QUOTE_CHARS = 6
_TRANS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", "\u00ad": None})

def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(_TRANS)
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
            result.append({"page": page, "quote": item["quote"].strip()})
    return result
