# Study AI

PDF를 업로드해 원문, 요약·마인드맵, 검증된 퀴즈, 플래시카드·FSRS 복습, 문서 기반 튜터를 사용하는 개인 학습 도구입니다.

## 실행

Windows에서 Python 3.11 이상, Node.js 20.19 이상이 필요합니다. 기본 AI 공급자는 기존 Claude Code 구독입니다. `claude`가 설치되고 로그인돼 있어야 AI 생성이 동작합니다.

```powershell
cd C:\Users\82106\Desktop\univ\study-ai
.\start.ps1
```

브라우저에서 **http://127.0.0.1:8000**을 엽니다. 최초 실행에는 의존성을 설치하고 프론트엔드를 빌드합니다. 이후에는 의존성 파일이 바뀐 경우만 설치합니다. API와 화면을 서버 하나에서 제공합니다. 개발 서버의 자동 재시작이 긴 AI 작업을 끊지 않도록 기본 실행에는 reload를 쓰지 않습니다.

```powershell
.\stop.ps1
.\start.ps1 -NoBrowser
# 8000번 포트가 다른 앱에서 사용 중인 경우
.\start.ps1 -Port 8010
```

실행 로그: `.runtime/server.log`, `.runtime/server-error.log`. 설정 변경 후에는 종료하고 다시 실행합니다.

## 사용 순서

1. 자료실에서 PDF를 업로드합니다. 여러 파일을 선택하거나 끌어 놓을 수 있습니다.
2. 자료를 열고 요약 탭에서 생성합니다. 마인드맵은 같은 결과에서 만들어집니다. 출처 버튼은 실제 원문 페이지로 이동합니다.
3. 퀴즈 탭에서 개수와 유형을 고르고 생성합니다. 객관식·OX는 즉시 채점, 단답형의 의미 판정은 AI가 처리합니다. 최근 답이 틀린 문제만 다시 풀거나 해당 개념으로 새 문제를 생성할 수 있습니다.
4. 플래시카드 탭에서 생성·편집합니다. 홈의 복습 수는 **현재 시각까지 기한이 된 카드 수**입니다. 다시/어려움/보통/쉬움은 실제 FSRS 스케줄러에 기록됩니다.
5. 튜터에서 설명 모드나 질문 모드를 선택합니다. 검색된 원문 인용과 문단별 검증을 통과한 답변만 저장합니다.

모든 생성은 진행 상태를 표시하고 취소할 수 있습니다. 같은 종류의 중복 요청은 기존 작업을 반환합니다. 취소나 실패 시 이전 완료 결과가 유지됩니다. PDF 처리 중 삭제는 막고, 취소된 생성이 삭제된 문서에 결과를 다시 쓰지 못하도록 했습니다. 서버 재시작 시 요약·퀴즈·카드 작업은 실패 상태로 정리하며 PDF 추출은 제한된 워커에서 재개합니다.

## AI 공급자 설정

`.env.example`을 `.env`로 복사하고 필요한 항목만 변경합니다. API 키는 프론트엔드에 전송하거나 백업 ZIP에 넣지 않습니다.

| 모드 | 설정 | 필요한 것 |
|---|---|---|
| Claude Code 구독 | `LLM_PROVIDER=claude_cli`, `LLM_MODEL=sonnet` | Claude Code 로그인·인터넷 |
| Claude API | `LLM_PROVIDER=api`, `LLM_MODEL=claude-sonnet-5-5`, `ANTHROPIC_API_KEY=...` | 사용 가능한 모델·API 키·인터넷 |
| Ollama | `LLM_PROVIDER=ollama`, `LLM_MODEL=설치한_모델명` | 실행 중인 Ollama와 내려받은 모델 |

CLI 모드는 자식 프로세스에서 API 키 환경변수를 제거합니다. 앱·DB·PDF는 로컬에 저장되지만 **Claude 모드에서는 생성에 필요한 문서 내용이 Claude로 전송됩니다.** Ollama와 로컬 검색만 사용하면 모델 설치 후 오프라인으로 생성할 수 있습니다.

구조화 출력은 공급자 기능 외에 서버에서도 JSON Schema로 재검증합니다. API 모드는 시스템 프롬프트의 prompt caching을 요청하지만, 캐시 적중·비용 절감은 프롬프트 길이와 서비스 정책에 따라 달라집니다.

## 로컬 검색·임베딩·OCR

기본 검색은 모델 다운로드 없이 작동하는 한영 키워드 검색입니다. 문서를 페이지 번호가 붙은 최대 2,400자 청크로 나누며, 한국어 부분 단어 검색도 지원합니다.

의미 검색을 켜려면 아래 명령으로 sentence-transformers 모델을 **명시적으로** 설치합니다. 기본 BGE-M3와 실행 패키지는 큰 다운로드와 메모리가 필요합니다.

```powershell
.\setup-embeddings.ps1
```

출력된 `EMBEDDING_MODEL=...`을 `.env`에 넣고 재시작합니다. 기존 문서는 API의 `POST /api/documents/{id}/retry`로 다시 처리해 임베딩을 만듭니다. 벡터는 SQLite에 보관하며 sqlite-vec 코사인 거리와 키워드 점수를 결합합니다. 앱은 실행 중 모델을 자동 다운로드하지 않습니다.

OCR은 선택 기능입니다. Tesseract와 `kor`, `eng` 언어 데이터를 별도로 설치한 뒤 `OCR_ENABLED=true`를 설정합니다. 필요한 경우 `TESSDATA_PREFIX`도 지정합니다. 텍스트가 거의 없거나 손상된 페이지에 PyMuPDF OCR을 적용합니다. 수식·표·다단 레이아웃의 추출 품질은 원문 화면에서 확인해야 합니다.

## 휴대폰 PWA·Tailscale

PWA manifest, 아이콘, 앱 화면용 service worker가 포함돼 있습니다. 브라우저 캐시에 문서·정답·로그인 API 응답을 저장하지 않습니다. **PC의 서버가 켜져 있고 휴대폰에서 연결 가능해야 복습·생성이 동작합니다.**

127.0.0.1은 다른 기기에서 직접 접속할 수 없습니다. 휴대폰 연결은 Tailscale Serve가 로컬 서버 앞에서 HTTPS를 제공하는 구성으로 사용합니다.

1. PC와 휴대폰을 본인의 Tailscale 네트워크에 연결합니다.
2. `.env`에 충분히 긴 `APP_PASSWORD`를 설정하고, HTTPS 접속에는 `COOKIE_SECURE=true`로 설정합니다.
3. 앱을 재시작하고 PC에서 `tailscale serve --bg http://127.0.0.1:8000`을 실행합니다.
4. 표시된 HTTPS 주소를 휴대폰에서 열어 로그인하고 홈 화면에 추가합니다.

Tailscale 계정 연결·Serve 설정·실제 휴대폰 설치는 이 코드 작업에서 수행하지 않았습니다. 비밀번호가 없으면 앱은 외부 Host/클라이언트의 API 접근을 거부합니다. `COOKIE_SECURE=true`일 때 로그인은 HTTPS 주소로 이용하세요.

## 백업과 복원

자료실의 **연결 확인과 백업 → 자료·학습 기록 백업**에서 ZIP을 받습니다. 실행 중 SQLite도 안전한 스냅샷으로 저장합니다. DB와 연결된 PDF가 들어 있으며 API 키·세션 비밀키·다운로드 모델은 제외됩니다.

복원은 서버를 종료한 뒤 ZIP을 **새 빈 폴더**에 풉니다. 그 폴더에는 `study.db`와 `uploads/`가 있어야 합니다. 기존 자료를 보존한 채 `.env`의 `STUDY_DATA_DIR=C:/.../복원폴더`로 새 폴더를 지정하고 실행하면 됩니다. 기존 data 폴더 위에 실행 중 덮어쓰지 마세요.

## 개발·검증

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm ci
npm run build
```

개발 모드: backend 폴더에서 `..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, frontend 폴더에서 `npm run dev`를 실행합니다.

브라우저 E2E는 실제 사용자 데이터와 다른 임시 DB 및 고정 LLM 응답을 사용합니다.

```powershell
# 별도 터미널, 프로젝트 루트
.\.venv\Scripts\python.exe backend/tests/browser_server.py
# frontend 폴더
npx playwright test
```

Windows에서는 설치된 Chrome을 사용합니다. Chrome이 없으면 `npx playwright install chromium`이 필요합니다. 실제 Claude 검사: 루트에서 `.\.venv\Scripts\python.exe backend/tests/live_smoke.py`. 개인 자료 대신 합성 PDF를 사용하며 **실제 모델 사용량이 발생합니다.**

## 검증 범위와 남은 제약

- 실제 Claude CLI로 요약·퀴즈·카드·튜터 생성과 출처 저장을 확인했습니다.
- 자동 브라우저 검사로 업로드, 요약, 마인드맵, 오답 풀이, 카드 편집, FSRS 복습, 튜터 출처 이동과 모바일 화면을 확인했습니다.
- Claude API·Ollama는 구현 및 모의 HTTP 검사 대상이며, 사용자 API 키나 로컬 모델로 실제 호출하지 않았습니다.
- 선택형 임베딩 모델·OCR 엔진은 사용자 PC에 설치해야 합니다. 임베딩 연결과 sqlite-vec 계산은 자동 테스트로 검사합니다.
- 튜터는 SSE로 진행 상태를 보내고 **검증 완료된 답변을 전달**합니다. 미검증 토큰을 먼저 보여주지는 않습니다.
- 품질 검증은 원문 밖의 내용을 줄이지만 완전한 정확성을 보장하지 않습니다. “20문제 중 이상한 문제 2개 이하”는 실제 강의 자료와 사람의 평가로 확인할 수 있는 별도 수용 기준입니다.
- 로컬 단일 서버/단일 사용자용입니다. 여러 uvicorn worker나 같은 DB를 쓰는 두 서버를 동시에 실행하지 마세요.

참고: [FSRS](https://github.com/open-spaced-repetition/py-fsrs), [Claude 구조화 출력](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Ollama Chat](https://docs.ollama.com/api/chat), [sqlite-vec Python](https://github.com/asg017/sqlite-vec/blob/main/examples/simple-python/demo.py), [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
