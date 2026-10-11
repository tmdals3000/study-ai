from datetime import datetime
from sqlmodel import Field, SQLModel

class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    filename: str
    pages: int = 0
    status: str = "processing"
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

class Page(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="document.id", index=True)
    page_no: int
    text: str

class Generation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="document.id", index=True)
    kind: str
    status: str = "queued"
    progress: str | None = None
    data: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    options: str = "{}"

class Chunk(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="document.id", index=True)
    page_start: int
    page_end: int
    text: str
    embedding: str | None = None
    embedding_model: str = "lexical"

class Question(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="document.id", index=True)
    generation_id: int = Field(foreign_key="generation.id", index=True)
    type: str
    question: str
    choices: str = "[]"
    answer: str
    explanation: str
    evidence: str
    difficulty: str = "medium"
    concept: str = ""

class Attempt(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="question.id", index=True)
    user_answer: str
    correct: bool
    feedback: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="document.id", index=True)
    front: str
    back: str
    evidence: str = "[]"
    fsrs_state: str = ""
    due_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    version: int = 0
    edited: bool = False

class Review(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="card.id", index=True)
    rating: int
    log: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="document.id", index=True)
    role: str
    content: str
    citations: str = "[]"
    mode: str = "explain"
    created_at: datetime = Field(default_factory=datetime.utcnow)
