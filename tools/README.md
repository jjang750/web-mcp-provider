# XpERP 입주자 관리 더미 API

provider 앱(`../app`)과 **분리된 독립 서버**. MCP 워크플로우 / end-to-end 테스트용.
STT 통화분석(`STT_API설계_분석.xlsx`) 기반 XpERP API 설계를 모사. 포트 `:8000`, 인메모리 저장(재기동 시 초기값 리셋).

공통 필수 파라미터: `aptcd`(단지코드, 6자리 숫자, 예 `001023`), 조회년월 `yearmon`(YYYYMM, 예 `202510`).
시드 단지: `001023`(○○아파트, 세대 5 / 직원 4 / 민원 3).

## 엔드포인트
| 그룹 | 메서드 | 경로 | 필수 파라미터 | 설명 |
|---|---|---|---|---|
| APT 단지 | GET | `/apt/code` | name | 아파트명(부분일치)으로 단지코드 조회. 단건이면 `aptcd` 최상위 반환 + 되묻기 힌트 필드 |
| APT 단지 | GET | `/apt/list` | - | 단지 목록 |
| IMPO 관리비 | GET | `/impo/detail` | aptcd, yearmon | 관리비·부과 조회(dong·ho 선택) |
| RECP 수납 | GET | `/recp/unpaid` | aptcd, yearmon | 미납·연체 요약(months 선택) |
| RECP 수납 | GET | `/recp/unpaid/list` | aptcd, yearmon | 미납 세대 목록 |
| RECP 수납 | GET | `/recp/status` | aptcd, dong, ho, yearmon | 세대 수납 현황 |
| RECP 수납 | GET | `/recp/detail` | aptcd, dong, ho, yearmon | 수납 이력 상세 |
| INSP 검침 | GET | `/insp/status` | aptcd, yearmon | 검침 현황 요약(type·dong·ho 선택) |
| INSP 검침 | GET | `/insp/usage` | aptcd, yearmon | 세대별 사용량 |
| INSP 검침 | GET | `/insp/missing` | aptcd, yearmon | 미검침 세대 목록 |
| OCCP 입주자 | GET | `/occp/unit` | aptcd | 입주자·세대 조회(dong·ho 선택) |
| OCCP 입주자 | GET | `/occp/list` | aptcd | 세대 목록(status 선택, 전출 포함) |
| OCCP 입주자 | POST | `/occp/unit` | (body) | 입주자 등록 |
| OCCP 입주자 | PUT | `/occp/unit` | aptcd, dong, ho | 입주자 정보 전체 교체 |
| OCCP 입주자 | PATCH | `/occp/unit` | aptcd, dong, ho | 부분 수정 / 전출 처리 |
| OCCP 입주자 | DELETE | `/occp/unit` | aptcd, dong, ho | 세대 삭제 |
| CMPL 민원 | GET | `/cmpl/list` | aptcd | 민원 목록(status 선택) |
| CMPL 민원 | GET | `/cmpl/{cmpl_id}` | (path) | 민원 단건 |
| ACCT 회계 | GET | `/acct/summary` | aptcd, yearmon | 월별 회계 요약 |
| ACCT 회계 | GET | `/acct/budget` | aptcd | 예산 집행률(year 선택) |
| HR 인사 | GET | `/hr/staff` | aptcd | 직원·급여 현황(yearmon 선택) |
| PARK 차량 | GET | `/park/vehicle` | aptcd | 차량 조회(car_no·dong 선택) |
| 공통 | GET | `/health` | - | 헬스 체크 |

검증: `aptcd` 6자리 숫자 아니면 400, 없는 세대 404, 필수 파라미터 누락 422, `type`/`status` 허용값 외 400.

OpenAPI: http://localhost:8000/openapi.json · Swagger UI: http://localhost:8000/docs

## 로컬 실행 (venv)
```bash
cd tools
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn dummy_api:app --host 0.0.0.0 --port 8000
```

> 호스트 포트는 **18000** 으로 매핑됨(컨테이너 내부는 8000). 접속 URL: **http://localhost:18000** (예: `/docs`, `/openapi.json`).

## Docker Compose 실행 (권장)
```bash
cd tools
docker compose up --build      # 포그라운드(빌드+기동), Ctrl+C로 종료
docker compose up -d           # 백그라운드(detached)
docker compose logs -f         # 로그 확인
docker compose down            # 중지 + 컨테이너 제거
```
`healthcheck` 포함 → `docker compose ps` 로 상태 확인 가능. 호스트 포트 변경은 `docker-compose.yml` 의 `ports`(`"18000:8000"`)에서.

## Docker 단독 실행 (compose 없이)
```bash
cd tools
docker build -t dummy-api .
docker run --rm -p 18000:8000 dummy-api            # 포그라운드
docker run -d --name dummy-api -p 18000:8000 dummy-api   # 백그라운드
docker logs -f dummy-api; docker stop dummy-api; docker rm dummy-api
```
기동 후 http://localhost:18000/docs 접속해 동작 확인.

## 빠른 호출 예시 (curl)
> 한글 쿼리값(type=수도, status=전출 등)은 `-G --data-urlencode` 로 URL 인코딩해야 합니다.
```bash
# 조회
curl "http://localhost:8000/impo/detail?aptcd=001023&yearmon=202510&dong=101&ho=305"
curl "http://localhost:8000/recp/unpaid/list?aptcd=001023&yearmon=202510&months=3"
curl "http://localhost:8000/occp/unit?aptcd=001023&dong=101&ho=305"
curl -G "http://localhost:8000/insp/status" --data-urlencode "aptcd=001023" --data-urlencode "yearmon=202510" --data-urlencode "type=수도"
curl -G "http://localhost:8000/cmpl/list"   --data-urlencode "aptcd=001023" --data-urlencode "status=처리중"

# 입주자 쓰기(등록 → 전출처리 → 삭제)
curl -X POST  http://localhost:8000/occp/unit -H "Content-Type: application/json" \
  -d '{"aptcd":"001023","dong":"102","ho":"303","name":"신규입주","phone":"010-1111-2222","members":2}'
curl -X PATCH "http://localhost:8000/occp/unit?aptcd=001023&dong=102&ho=303" -H "Content-Type: application/json" \
  -d '{"status":"전출","moveout":"2025-12-31"}'
curl -X DELETE "http://localhost:8000/occp/unit?aptcd=001023&dong=102&ho=303"
```

## 챗봇 되묻기(needs_input) 설계

발화에서 단지코드를 확정하지 못하면 사용자에게 추가 입력을 요청하는 흐름을 위해, `/apt/code` 응답에 힌트 필드를 둔다. 단지코드 확정은 챗봇/LLM이 이 필드로 판단하고, 더미 API는 신호만 제공한다.

| 필드 | 의미 |
|---|---|
| `resolved` | 단지코드가 한 곳으로 확정됐는지(bool) |
| `needs_input` | 사용자에게 추가/정정 입력을 요청해야 하는지(bool) |
| `reason` | `ok`(단건) · `ambiguous`(다건) · `not_found`(무매칭) |
| `message` | 챗봇이 그대로 사용할 안내 문구 |

분기별 응답:

- **단건**: `resolved=true, needs_input=false, reason="ok"`, `aptcd`·`name` 최상위 반환 → 후속 API로 바로 체이닝.
- **다건(모호)**: `resolved=false, needs_input=true, reason="ambiguous"`, `items` 에 후보 목록 → "어느 단지인가요?" 되묻기/선택지 제시.
- **무매칭**: `resolved=false, needs_input=true, reason="not_found"` → "아파트명을 다시 확인" 안내.

권장 챗봇 흐름(예: "○○아파트 2026년 05월 관리비"):

1. `/apt/code?name=○○` 호출.
2. `needs_input=true` → `message` 로 되묻기(다건이면 `items` 선택지). `false` → 다음 단계.
3. 확정된 `aptcd` + 추출한 `yearmon`(YYYYMM)로 `/impo/detail` 호출. (세대 단위 금액이 필요하면 `dong`·`ho` 추가 요청.)

참고: `/impo/detail` 등 핵심 API의 필수값(`aptcd`·`yearmon`)이 비면 더미 API가 `422`(누락)·`400`(형식오류)를 반환하므로, 이를 2차 되묻기 트리거로도 쓸 수 있다.
