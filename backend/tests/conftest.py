import os
import sys
import tempfile
from pathlib import Path
import pytest

TEST_DATA = tempfile.TemporaryDirectory(prefix="study-ai-tests-")
os.environ["STUDY_DATA_DIR"] = TEST_DATA.name
os.environ["APP_PASSWORD"] = ""
os.environ["LLM_PROVIDER"] = "claude_cli"
os.environ["EMBEDDING_MODEL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, delete
from app.db import engine
from app.main import app
from app import jobs

@pytest.fixture
def client(monkeypatch):
    with TestClient(app) as client:
        with Session(engine) as session:
            for table in reversed(SQLModel.metadata.sorted_tables):
                session.exec(delete(table))
            session.commit()
        monkeypatch.setattr(jobs, "submit", lambda job_id, action: jobs._run(job_id, action))
        yield client

def pytest_sessionfinish(session, exitstatus):
    jobs.stop_workers()
    engine.dispose()
    TEST_DATA.cleanup()
