"""Isolated deterministic server for browser QA; never used by start.ps1."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["STUDY_DATA_DIR"] = tempfile.mkdtemp(prefix="study-browser-")
os.environ["APP_PASSWORD"] = ""
os.environ["LLM_PROVIDER"] = "claude_cli"
os.environ["EMBEDDING_MODEL"] = ""
from app import llm
from fake_llm import respond
llm._claude_cli = respond
from app.main import app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8011)
