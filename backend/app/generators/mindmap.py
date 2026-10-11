"""Build labels deterministically; never load remote Markdown assets."""
import re
def _label(text: str) -> str:
    text = re.sub(r"[#*_\x60\[\]<>!\\\\]", "", text)
    return re.sub(r"\s+", " ", text).strip()
def _pages(pages):
    return " (" + ", ".join(f"p.{n}" for n in sorted(set(pages))) + ")" if pages else ""
def build_mindmap(summary):
    lines = [f"# {_label(summary['title'])}"]
    if summary["key_concepts"]:
        lines.append("## 핵심 개념")
        for concept in summary["key_concepts"]:
            lines.append(f"- {_label(concept['name'])}{_pages(concept['pages'])}")
    for section in summary["sections"]:
        if section["points"]:
            lines.append(f"## {_label(section['title'])}")
            for point in section["points"]:
                lines.append(f"- {_label(point['kind'])} · {_label(point['heading'])}{_pages(point['pages'])}")
    return "\n".join(lines)
