"""Deterministic fixture responses: never enabled by the application."""
import re
TEXT = "Water freezes at zero degrees Celsius. The Earth orbits the Sun."
EVIDENCE = [{"page": 1, "quote": "Water freezes at zero degrees Celsius."}]
def respond(prompt, system, schema, model, timeout, images=None):
    props = schema.get("properties", {}) if schema else {}
    if not schema:
        return "Connected."
    if "figures" in props:
        return {"figures": [{"caption": "Phase diagram", "texts": ["Ice", "Liquid water"], "structure": ["Ice → Liquid water arrow"]}]}
    if "points" in props:
        return {"title": "Water", "points": [{"heading": "Freezing point", "kind": "정의", "content": "Water freezes at zero degrees Celsius.", "evidence": EVIDENCE}]}
    if "one_line" in props:
        refs = re.findall(r'<note id="([^"]+)">', prompt)
        return {"one_line": {"text": "Water freezes at zero degrees Celsius.", "based_on": refs[:1]},
                "key_concepts": [{"name": "Freezing point", "description": "Water freezes at zero degrees Celsius.", "based_on": refs[:1]}],
                "exam_points": [{"text": "Water freezes at zero degrees Celsius.", "based_on": refs[:1]}]}
    if "verdicts" in props:
        ids = list(dict.fromkeys(re.findall(r'"id":\s*"([^"]+)"', prompt)))
        if "valid" in props["verdicts"]["items"]["properties"]:
            return {"verdicts": [{"id": i, "valid": True, "quality": 5, "issues": ""} for i in ids]}
        return {"verdicts": [{"id": i, "verdict": "supported", "issues": "", "corrected": ""} for i in ids]}
    if "items" in props:
        if "front" in props["items"]["items"]["properties"]:
            return {"items": [{"front": "When does water freeze?", "back": "At zero degrees Celsius.", "evidence": EVIDENCE}]}
        return {"items": [
            {"type": "multiple", "question": "At what temperature does water freeze?", "choices": ["0 C", "10 C", "20 C", "30 C"], "answer": "0 C", "explanation": TEXT.split(". ")[0] + ".", "evidence": EVIDENCE, "concept": "Freezing", "difficulty": "easy"},
            {"type": "ox", "question": "Water freezes at zero degrees Celsius.", "choices": ["O", "X"], "answer": "O", "explanation": TEXT.split(". ")[0] + ".", "evidence": EVIDENCE, "concept": "Freezing", "difficulty": "easy"},
            {"type": "short", "question": "What does the Earth orbit?", "choices": [], "answer": "Sun", "explanation": "The Earth orbits the Sun.", "evidence": [{"page": 1, "quote": "The Earth orbits the Sun."}], "concept": "Orbit", "difficulty": "easy"}
        ]}
    if "paragraphs" in props:
        return {"paragraphs": [{"text": "Water freezes at zero degrees Celsius.", "evidence": EVIDENCE}]}
    if "correct" in props:
        return {"correct": True, "feedback": "The Earth orbits the Sun."}
    raise AssertionError(f"Unknown schema: {list(props)}")
