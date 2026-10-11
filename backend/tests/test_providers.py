import json
import httpx
import pytest
from sqlmodel import Session
from app import llm, retrieval
from app.db import engine
from app.models import Chunk, Document

def test_api_uses_structured_output_and_validates_response(monkeypatch):
    real_client = httpx.Client
    def respond(request):
        body = json.loads(request.content)
        assert request.headers["x-api-key"] == "test-only-key"
        assert body["output_config"]["format"]["type"] == "json_schema"
        assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert body["model"] == "test-model"
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"value": 4}'}]})
    monkeypatch.setattr(llm.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-key")
    monkeypatch.setattr(llm, "LLM_PROVIDER", "api")
    schema = {"type": "object", "properties": {"value": {"type": "integer", "minimum": 2}}, "required": ["value"]}
    assert llm.generate("test", system="test", schema=schema, model="test-model", retries=0) == {"value": 4}

def test_ollama_uses_local_structured_chat(monkeypatch):
    real_client = httpx.Client
    def respond(request):
        assert request.url.host == "127.0.0.1"
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["format"]["type"] == "object"
        return httpx.Response(200, json={"message": {"content": '{"answer":"ok"}'}})
    monkeypatch.setattr(llm.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(llm, "LLM_PROVIDER", "ollama")
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    assert llm.generate("test", schema=schema, retries=0) == {"answer": "ok"}

def test_cli_subscription_does_not_forward_api_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-key")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-only-token")
    env = llm._subscription_env()
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env

def test_sqlite_vec_and_local_embedding_adapter(client, monkeypatch):
    monkeypatch.setattr(retrieval, "EMBEDDING_MODEL", "test-local")
    monkeypatch.setattr(retrieval, "encode", lambda texts: [[1.0, 0.0] for _ in texts])
    with Session(engine) as session:
        doc = Document(title="vectors", filename="vectors.pdf", status="ready")
        session.add(doc); session.commit(); session.refresh(doc)
        session.add(Chunk(doc_id=doc.id, page_start=1, page_end=1, text="unrelated material", embedding="[0.0, 1.0]", embedding_model="test-local"))
        session.add(Chunk(doc_id=doc.id, page_start=2, page_end=2, text="matching semantic material", embedding="[1.0, 0.0]", embedding_model="test-local"))
        session.commit()
        results = retrieval.retrieve(session, doc.id, "different wording")
        assert results[0]["page"] == 2
        assert results[0]["score"] == 1.0

def test_minus_sign_and_case_are_not_discarded():
    from app.grounding import find_quote
    assert find_quote("Temperature is 20 degrees.", {1: "Temperature is -20 degrees."}) is None
    assert find_quote("The symbol is a variable.", {1: "The symbol is A variable."}) is None
