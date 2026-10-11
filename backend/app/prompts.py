from functools import cache

from .config import PROMPT_DIR


@cache
def _read(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def load_prompt(name: str, **values: str) -> str:
    """prompts/{name}.md를 읽어 {{KEY}} 자리표시자를 채운다."""
    text = _read(name)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text
