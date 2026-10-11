"""Provider boundary. Schema validation and global concurrency apply to every caller."""
import base64
import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any
import httpx
from jsonschema import validate, ValidationError
from .config import LLM_DEFAULT_MODEL, LLM_PROVIDER, LLM_SANDBOX_DIR, LLM_PARALLEL, OLLAMA_URL
from .jobs import checkpoint, JobStopped

_slots = threading.BoundedSemaphore(LLM_PARALLEL)

class LLMError(RuntimeError):
    pass

def _subscription_env():
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env

def _image_blocks(images):
    return [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
             "data": base64.b64encode(image).decode("ascii")}} for image in images or []]

def _claude_cli(prompt, system, schema, model, timeout, images=None):
    exe = shutil.which("claude")
    if not exe:
        raise LLMError("Claude Code가 없습니다. 설치·로그인하거나 .env에서 다른 LLM을 선택하세요.")
    args = [exe, "-p", "--model", model, "--tools", "", "--strict-mcp-config", "--no-session-persistence"]
    if images:
        # 이미지는 stream-json 입력(이미지 블록이 든 user 메시지 한 줄)으로만 넘길 수 있다
        args += ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
        prompt = json.dumps({"type": "user", "message": {"role": "user",
            "content": _image_blocks(images) + [{"type": "text", "text": prompt}]}}) + "\n"
    else:
        args += ["--output-format", "json"]
    if system:
        args += ["--system-prompt", system]
    if schema:
        args += ["--json-schema", json.dumps(schema)]
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=_subscription_env(), cwd=LLM_SANDBOX_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    start, first = time.monotonic(), True
    try:
        while True:
            checkpoint()
            if time.monotonic() - start > timeout:
                raise LLMError(f"Claude 응답 제한 시간({timeout}초)을 넘었습니다.")
            try:
                stdout, stderr = proc.communicate(input=prompt if first else None, timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                first = False
        if proc.returncode:
            raise LLMError((stderr or stdout or "Claude 실행 실패").strip()[:1000])
        if images:
            events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            result = next((e for e in reversed(events) if e.get("type") == "result"), None)
            if result is None:
                raise LLMError("Claude 응답에서 결과를 찾지 못했습니다.")
        else:
            result = json.loads(stdout)
        if result.get("is_error"):
            raise LLMError(str(result.get("result", "Claude 실행 실패"))[:1000])
        return result.get("structured_output") if schema else result.get("result", "")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

def _api_schema(value):
    if isinstance(value, list):
        return [_api_schema(x) for x in value]
    if not isinstance(value, dict):
        return value
    constraints = {"minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "pattern"}
    result = {k: _api_schema(v) for k, v in value.items() if k not in constraints}
    if value.get("type") == "object":
        result["additionalProperties"] = False
    return result

def _api(prompt, system, schema, model, timeout, images=None):
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise LLMError(".env에 ANTHROPIC_API_KEY를 설정하세요.")
    body = {"model": model, "max_tokens": 16000, "messages": [{"role": "user", "content": _image_blocks(images) + [{"type": "text", "text": prompt}] if images else prompt}]}
    if system:
        body["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    if schema:
        body["output_config"] = {"format": {"type": "json_schema", "schema": _api_schema(schema)}}
    with httpx.Client(timeout=timeout) as client:
        response = client.post("https://api.anthropic.com/v1/messages", json=body,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    if response.is_error:
        raise LLMError(f"Claude API 오류 {response.status_code}: {response.text[:600]}")
    data = response.json()
    if data.get("stop_reason") == "max_tokens":
        raise LLMError("출력이 최대 길이를 넘었습니다. 더 작은 구간으로 시도하세요.")
    text = "".join(x.get("text", "") for x in data.get("content", []) if x.get("type") == "text")
    return json.loads(text) if schema else text

def _ollama(prompt, system, schema, model, timeout, images=None):
    user = {"role": "user", "content": prompt}
    if images:
        user["images"] = [base64.b64encode(image).decode("ascii") for image in images]
    messages = ([{"role": "system", "content": system}] if system else []) + [user]
    body = {"model": model, "messages": messages, "stream": False}
    if schema:
        body["format"] = schema
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        response = client.post(f"{OLLAMA_URL}/api/chat", json=body)
    if response.is_error:
        raise LLMError(f"Ollama 오류 {response.status_code}: {response.text[:600]}")
    text = response.json()["message"]["content"]
    return json.loads(text) if schema else text

def generate(prompt: str, *, system: str | None = None, schema: dict | None = None,
             model: str = LLM_DEFAULT_MODEL, timeout: int = 600, retries: int = 1,
             images: list[bytes] | None = None) -> Any:
    """images: PNG 바이트 목록. 주면 모델이 이미지와 함께 prompt를 본다."""
    provider = {"claude_cli": _claude_cli, "api": _api, "ollama": _ollama}.get(LLM_PROVIDER)
    if provider is None:
        raise LLMError(f"지원하지 않는 LLM_PROVIDER: {LLM_PROVIDER}")
    while not _slots.acquire(timeout=0.2):
        checkpoint()
    try:
        for attempt in range(retries + 1):
            checkpoint()
            try:
                output = provider(prompt, system, schema, model, timeout, images)
                checkpoint()
                if schema:
                    validate(output, schema)
                elif not isinstance(output, str) or not output.strip():
                    raise LLMError("모델이 빈 응답을 반환했습니다.")
                return output
            except (httpx.HTTPError, ValueError, KeyError, ValidationError, OSError, LLMError) as exc:
                if attempt == retries:
                    raise LLMError(str(exc)[:1500]) from exc
    finally:
        _slots.release()
