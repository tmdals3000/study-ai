import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)
DATA_DIR = Path(os.getenv("STUDY_DATA_DIR", str(ROOT / "data"))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "study.db"
PROMPT_DIR = ROOT / "backend" / "prompts"
LLM_SANDBOX_DIR = DATA_DIR / "llm_sandbox"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude_cli")
LLM_DEFAULT_MODEL = os.getenv("LLM_MODEL", {"claude_cli": "sonnet", "api": "claude-sonnet-5-5", "ollama": "qwen3:8b"}.get(LLM_PROVIDER, "sonnet"))
MODEL_GENERATE = LLM_DEFAULT_MODEL
MODEL_VERIFY = os.getenv("LLM_VERIFY_MODEL", LLM_DEFAULT_MODEL)
LLM_PARALLEL = max(1, int(os.getenv("LLM_PARALLEL", "2")))
MAX_SECTION_CHARS = 12000
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "100")) * 1024 * 1024
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "2000"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "").strip()
OCR_ENABLED = os.getenv("OCR_ENABLED", "false").lower() == "true"
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "kor+eng")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
for directory in (UPLOAD_DIR, LLM_SANDBOX_DIR):
    directory.mkdir(parents=True, exist_ok=True)
