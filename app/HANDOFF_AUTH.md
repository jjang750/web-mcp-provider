# HANDOFF — 관리 UI JWT 인증/인가

## 요약
관리 UI(`backend.app:app`)에 JWT 기반 로그인(HttpOnly 쿠키, 1일 만료)을 추가했다.
- 인증 방식: HttpOnly 쿠키에 JWT 저장 → same-origin `fetch`가 자동 전송, 기존 프론트 코드 무수정.
- 계정: 단일 계정, 자격증명은 `.env` 평문(`APP_AUTH_USER` / `APP_AUTH_PASSWORD`).
- 만료: 기본 24h(`APP_JWT_EXPIRE_HOURS`) → "1일 1회" 로그인.
- 폴백: `APP_AUTH_USER`/`PASSWORD` 미설정 시 `AUTH_ENABLED=False` → 무인증(기존 동작 유지).

## 변경 파일
- `backend/auth.py` (신규): JWT 발급/검증, 자격증명 검증(타이밍 안전), 쿠키 헬퍼, public 경로 판정.
- `backend/app.py`: `require_auth` HTTP 미들웨어 + `GET/POST /login`, `GET/POST /logout` 라우트.
- `templates/login.html` (신규): 인라인 스타일 로그인 페이지(토큰 테마 반영).
- `.env.example`: `APP_AUTH_USER/PASSWORD/JWT_SECRET/JWT_EXPIRE_HOURS/COOKIE_SECURE` 추가.
- `requirements.txt`: `PyJWT>=2.8` 명시(이미 설치돼 있음).

## 인가 정책(미들웨어)
- public 경로(`/login`, `/logout`, `/static`, `/healthz`, `/favicon.ico`)는 무인증 통과.
- 그 외 미인증 요청: `/api/*`는 `401 JSON`, 나머지 페이지는 `302 → /login?next=<원경로>`.
- 로그인 성공 시 `next`(내부 경로만 허용, 오픈 리다이렉트 방지)로 복귀.

## .env 설정 (운영)
```
APP_AUTH_USER=admin
APP_AUTH_PASSWORD=<강력한-비밀번호>
APP_JWT_SECRET=<openssl rand -hex 32 결과>
APP_JWT_EXPIRE_HOURS=24
APP_COOKIE_SECURE=true   # HTTPS(리버스 프록시 TLS 종단)면 true
```
docker-compose `ui` 서비스는 `env_file: .env`로 위 변수를 자동 주입한다.

## 테스트 (사용자 진행용)

### 콘솔 (로컬)
```
cd app
export APP_AUTH_USER=admin APP_AUTH_PASSWORD=secret123 \
       APP_JWT_SECRET=test-secret-xyz APP_COOKIE_SECURE=false
python -m uvicorn backend.app:app --host 127.0.0.1 --port 9090
```

### URL (브라우저)
1. `http://127.0.0.1:9090/` 접속 → `/login`으로 리다이렉트 확인.
2. admin / secret123 로그인 → 홈 진입.
3. 새로고침·API 호출 정상(쿠키 자동 전송).
4. `http://127.0.0.1:9090/logout` → 다시 로그인 페이지.

### 자동 검증 결과 (curl, 2026-07-21)
| # | 케이스 | 기대 | 결과 |
|---|--------|------|------|
| 1 | 미인증 홈 | 302 →/login | ✅ |
| 2 | 미인증 /api/specs | 401 JSON | ✅ |
| 3 | /login 페이지 | 200 | ✅ |
| 4 | 틀린 비번 | 401 | ✅ |
| 5 | 올바른 로그인 | 302 + HttpOnly Set-Cookie | ✅ |
| 6 | 쿠키로 홈 | 200 | ✅ |
| 7 | 쿠키로 API | 200 | ✅ |
| 8 | healthz 무인증 | 200 | ✅ |
| 9 | 로그아웃 후 홈 | 302 | ✅ |
| - | 만료/위조 토큰 decode | None | ✅ |

## 세션 타임아웃 & 로그아웃 (추가)
- 무활동 30분(`APP_SESSION_IDLE_MINUTES`) 초과 시 자동 만료. 인증 요청마다 쿠키 `Max-Age=1800`으로 슬라이딩 갱신.
- 로그인 후 절대 상한 24h(`APP_JWT_EXPIRE_HOURS`) 유지("1일 1회"). 토큰의 `lat`(login-at)로 고정 판정.
- 메인 화면 상단바에 `로그아웃` 버튼(POST `/logout`) 추가 → 쿠키 삭제 후 `/login` 이동.
- 검증(2026-07-21): 정상/무활동30분초과/24h상한초과/슬라이딩 lat유지·exp재연장/로그아웃 모두 ✅.

## 이슈/리스크
- 평문 비밀번호(.env) — 기존 `MCP_AUTH_TOKEN` 패턴과 동일. 파일 권한 관리 필요.
- HTTPS 환경에서는 `APP_COOKIE_SECURE=true` 필수(미설정 시 HTTP로 쿠키 전송 위험).
- 단일 계정. 다중 계정 필요 시 `auth.verify_credentials` 확장.
- MCP HTTP 서버(`mcp_http_server.py`)는 별도 Bearer(`MCP_AUTH_TOKEN`) 인증으로 이번 변경 범위 밖.
