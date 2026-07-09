# HANDOFF — 빈 쿼리 파라미터 0건 문제 수정 (dummy_api.py)

작성일: 2026-07-09 · 대상: `tools/dummy_api.py`

## 요약
MCP 에디터에서 필수값(`aptcd`)만 넣어도 결과가 0건이던 문제를 백엔드에서 수정.
원인은 선택 파라미터가 **빈 문자열(`dong=`, `car_no=`)로 함께 전송**되어 필터로 작동한 것.

## 원인 → 영향 → 조치
- **원인**: `_filter_units`가 `if dong is not None:`으로 검사 → 빈 문자열(`""`)도 필터로 인식해 `dong == ""` 매칭 0건. (`car_no`는 `if car_no`라 무관했음.)
- **영향**: 직접 API 호출(`?aptcd=001023`)은 4건, MCP 에디터(`?aptcd=001023&car_no=&dong=`)는 0건.
- **조치**:
  1. `_filter_units`의 `dong`/`ho` 검사를 `is not None` → **truthiness(`if dong:`)** 로 변경. 빈 문자열=미지정 취급. (`/occp/unit`의 `if dong and ho:`도 동일 정렬.)
  2. **`StripEmptyQueryMiddleware`** 추가 — 라우팅 전에 빈 값 쿼리(`key=`)를 제거. 모든 선택 파라미터에 일괄 적용되어 재발 방지. 필수 파라미터가 빈 값이면 제거되어 FastAPI가 422(누락)로 응답.

## 변경 파일
- `tools/dummy_api.py`
  - import: `from urllib.parse import parse_qsl, urlencode`
  - `StripEmptyQueryMiddleware` 클래스 추가 + `app.add_middleware(StripEmptyQueryMiddleware)` (CORS 다음)
  - `_filter_units`: `dong`/`ho` truthiness 처리
  - `/occp/unit`: `if dong and ho:`

## 검증 결과 (동일 로직 재현 앱, uvicorn)
| 케이스 | 요청 | count |
|---|---|---|
| 필수값만 | `?aptcd=001023` | 4 |
| MCP식 빈값 포함 | `?aptcd=001023&car_no=&dong=` | 4 ✅(기존 0) |
| dong 실제 필터 | `?aptcd=001023&dong=101` | 2 |
| car_no 실제 필터 | `?aptcd=001023&car_no=12가3456` | 1 |
| 필수 빈값 | `?aptcd=` | HTTP 422 |

## 사용자 테스트 방법
로컬 기동 후 아래 두 URL 비교(둘 다 4건이면 정상):
```
uvicorn dummy_api:app --host 0.0.0.0 --port 8000    # tools 폴더에서
```
- `http://localhost:8000/park/vehicle?aptcd=001023`
- `http://localhost:8000/park/vehicle?aptcd=001023&car_no=&dong=`
- Swagger: `http://localhost:8000/docs`

운영/DDNS 확인: `https://panthip.ddns.net:18800/park/vehicle?aptcd=001023&car_no=&dong=` → count 4
MCP 에디터: 실행 #에서 `car_no`/`dong` 빈 값으로 두고 재실행 → items 채워짐 확인.

## 배포 시 주의
- `dummy_api.py`가 실행 중인 서버(:8000 / 프록시 :18800)를 **재기동**해야 반영됨(인메모리, 미들웨어는 기동 시 등록).
- 빌드 환경 함정은 `[[web-mcp-provider-env]]` 참고(마운트 캐시 truncate — bash에서 편집본이 stale로 보일 수 있음).

---

## 추가: MCP provider 측 근본 수정 (권장)

### 배경 — API 호출 관례
표준 클라이언트(Swagger UI, 대부분 SDK)는 **값 없는 선택 쿼리 파라미터를 전송하지 않음**.
`key=`(빈 값) 전송은 의미가 모호하며 OpenAPI `allowEmptyValue`도 deprecated.
→ 관례를 어긴 쪽은 provider의 요청 조립부. 백엔드 방어와 별개로 provider도 표준을 따르도록 수정.

### 조치
- 파일: `app/engine/http_client.py`
- `_drop_empty_query(query)` 추가 — 값이 `None`/`""`인 쿼리 항목 제거.
- `call()`·`preview()`가 전송/미리보기 직전 이 함수를 사용.
- 근거: executor는 이미 `""`을 '미입력'으로 취급(`executor.py` 514~525, `if _secobj[_k] in (None, "")`). 전송 단계만 예외였음 → 일관성 확보.
- apikey(query 위치) 인증값은 `_apply_auth`가 이후 주입하므로 영향 없음(검증됨).

### 검증 (httpx MockTransport, 격리)
| 입력 query | 실제 전송 URL |
|---|---|
| `{aptcd:001023, car_no:"", dong:""}` | `...?aptcd=001023` ✅ 빈값 생략 |
| `{aptcd:001023, dong:101}` | `...?aptcd=001023&dong=101` ✅ 유지 |
| `{aptcd:001023, car_no:""}` + apikey(query) | `...?aptcd=001023&api_key=K` ✅ 인증 유지 |

### 사용자 테스트 방법(콘솔)
- MCP 에디터에서 `car_no`/`dong` 빈 값으로 두고 재실행 → INPUT의 query에 빈 항목이 있어도 실제 호출에서 제외되어 items가 채워짐.
- provider 앱 재기동 필요.
- ※ 마운트 캐시 stale로 sandbox pytest 신뢰 불가 → `app/tests/`의 `test_executor.py`는 로컬 콘솔에서 직접 실행 권장.
