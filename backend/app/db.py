from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine
import sqlite_vec
from .config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False, "timeout": 30})

@event.listens_for(engine, "connect")
def sqlite_options(connection, _):
    connection.enable_load_extension(True)
    try:
        sqlite_vec.load(connection)
    finally:
        connection.enable_load_extension(False)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")

def init_db() -> None:
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        pending = [row[0] for row in conn.execute(text("SELECT id FROM document WHERE status='processing'"))]
        conn.execute(text("PRAGMA journal_mode=WAL"))
        columns = {r[1] for r in conn.execute(text("PRAGMA table_info(generation)"))}
        if "figure_text" not in {r[1] for r in conn.execute(text("PRAGMA table_info(page)"))}:
            conn.execute(text("ALTER TABLE page ADD COLUMN figure_text TEXT"))
        if "options" not in columns:
            conn.execute(text("ALTER TABLE generation ADD COLUMN options TEXT NOT NULL DEFAULT '{}'"))
        conn.execute(text("UPDATE generation SET status='error', progress=NULL, error='서버가 재시작되어 중단되었습니다. 다시 생성해 주세요.' WHERE status IN ('running','queued')"))
        conn.execute(text("UPDATE document SET status='error', error='텍스트 추출이 중단되었습니다. 다시 처리해 주세요.' WHERE status='processing'"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS one_active_generation ON generation(doc_id, kind) WHERE status IN ('queued','running')"))
        conn.execute(text("PRAGMA user_version=2"))
    return pending

def get_session():
    with Session(engine) as session:
        yield session
