import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit
from fastapi import Request
from fastapi.responses import JSONResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature
from .config import APP_PASSWORD, DATA_DIR

secret_path = DATA_DIR / ".session-secret"
if not secret_path.exists():
    secret_path.write_text(secrets.token_hex(32), encoding="ascii")
serializer = URLSafeTimedSerializer(secret_path.read_text(encoding="ascii"), salt=hashlib.sha256(APP_PASSWORD.encode()).hexdigest())
_attempts = defaultdict(deque)

def authenticated(request: Request) -> bool:
    if not APP_PASSWORD:
        return True
    try:
        return serializer.loads(request.cookies.get("study_session", ""), max_age=12 * 3600) == "owner"
    except BadSignature:
        return False

def check_password(password: str, address: str) -> bool:
    now = time.monotonic()
    queue = _attempts[address]
    while queue and queue[0] < now - 60:
        queue.popleft()
    if len(queue) >= 10:
        return False
    queue.append(now)
    valid = bool(APP_PASSWORD) and hmac.compare_digest(password.encode(), APP_PASSWORD.encode())
    if valid:
        queue.clear()
    return valid

async def guard(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    host = request.headers.get("host", "")
    hostname = urlsplit("//" + host).hostname
    peer = request.client.host if request.client else ""
    if not APP_PASSWORD and (hostname not in ("localhost", "127.0.0.1", "::1", "testserver") or peer not in ("127.0.0.1", "::1", "testclient")):
        return JSONResponse({"detail": "외부 기기 접속에는 APP_PASSWORD 설정이 필요합니다."}, status_code=403)
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and urlsplit(origin).netloc != host:
        return JSONResponse({"detail": "다른 사이트에서 보낸 요청은 허용하지 않습니다."}, status_code=403)
    public = {"/api/health", "/api/auth", "/api/auth/login"}
    if request.url.path not in public and not authenticated(request):
        return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
    return await call_next(request)
