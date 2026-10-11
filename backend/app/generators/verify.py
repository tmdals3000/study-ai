"""별도 LLM 호출로 생성 결과를 원문과 대조하는 검증 단계. 요약·퀴즈·튜터에서 공통으로 쓴다."""
from .. import llm
from ..config import MODEL_VERIFY
from ..prompts import load_prompt
import json

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
                    "issues": {"type": "string"},
                    "corrected": {"type": "string"},
                },
                "required": ["id", "verdict", "issues", "corrected"],
            },
        }
    },
    "required": ["verdicts"],
}


def verify_claims(
    claims: dict[str, str], source: str, cites: dict[str, list[str]] | None = None
) -> dict[str, dict]:
    """claims({id: 텍스트})를 source와 대조해 {id: verdict} 를 반환한다.

    cites({claim id: [note id]})를 주면 각 claim은 자신이 인용한 note만 근거로 판정된다.
    그래야 claim에 붙은 출처(페이지)가 실제 근거와 일치한다.
    """
    if not claims:
        return {}

    def tag(cid: str) -> str:
        if cites is None:
            return f'<claim id="{cid}">'
        return f'<claim id="{cid}" cites="{",".join(cites.get(cid, []))}">'

    claims_text = "\n\n".join(f"{tag(cid)}\n{text}\n</claim>" for cid, text in claims.items())
    out = llm.generate(
        load_prompt("verify", SOURCE=source, CLAIMS=claims_text),
        system=load_prompt("system_grounded"),
        schema=VERIFY_SCHEMA,
        model=MODEL_VERIFY,
    )
    return {v["id"]: v for v in out["verdicts"]}


def apply_verdict(original: str, verdict: dict | None) -> tuple[str | None, bool]:
    """(최종 텍스트 또는 None(제외), 수정 여부). 판정이 누락된 항목은 검증되지 않았으므로 제외한다."""
    if verdict is None:
        return None, False
    if verdict["verdict"] == "supported":
        return original, False
    corrected = verdict.get("corrected", "").strip()
    if verdict["verdict"] == "partial" and corrected:
        return corrected, True
    return None, False


def verify_scoped(items: dict[str, tuple[str, str]]) -> dict[str, dict]:
    if not items:
        return {}
    payload = [{"id": key, "claim": claim, "source": source} for key, (claim, source) in items.items()]
    out = llm.generate(load_prompt("verify_scoped", ITEMS=json.dumps(payload, ensure_ascii=False)),
                       system=load_prompt("system_grounded"), schema=VERIFY_SCHEMA, model=MODEL_VERIFY)
    counts = {}
    for verdict in out["verdicts"]:
        counts[verdict["id"]] = counts.get(verdict["id"], 0) + 1
    return {v["id"]: v for v in out["verdicts"] if v["id"] in items and counts[v["id"]] == 1}
