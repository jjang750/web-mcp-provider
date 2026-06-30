"""XpERP 입주자 관리 더미 API 서버 (:8000) — 독립 실행형.

STT 통화분석(STT_API설계_분석.xlsx) 기반 XpERP API 설계를 그대로 모사한 테스트용 서버.
provider 앱(`../app`)과 분리된 독립 서버이며, MCP 워크플로우 / e2e 테스트에 사용한다.

로컬 기동(이 폴더에서):
    uvicorn dummy_api:app --host 0.0.0.0 --port 8000
Docker:
    docker compose up --build        # 호스트 18000 → 컨테이너 8000

OpenAPI: http://localhost:8000/openapi.json   ·   Swagger UI: http://localhost:8000/docs

────────────────────────────────────────────────────────────────────────────
엔드포인트
  APT  단지(명→코드)  GET  /apt/code, /apt/list
  IMPO 관리비·부과    GET  /impo/detail
  RECP 미납·연체      GET  /recp/unpaid, /recp/unpaid/list
  RECP 수납·이력      GET  /recp/status, /recp/detail
  INSP 검침·사용량    GET  /insp/status, /insp/usage, /insp/missing
  OCCP 입주자·세대    GET  /occp/unit, /occp/list
                      POST /occp/unit   PUT /occp/unit   PATCH /occp/unit   DELETE /occp/unit  (쓰기/전출처리)
  CMPL 민원           GET  /cmpl/list, /cmpl/{cmpl_id}
  ACCT 회계·예산      GET  /acct/summary, /acct/budget
  HR   인사·급여      GET  /hr/staff
  PARK 차량·주차      GET  /park/vehicle
  공통               GET  /health
공통 필수 파라미터: aptcd(단지코드, 6자리). 조회년월: yearmon(YYYYMM).
저장은 인메모리 → 서버 재기동 시 초기값으로 리셋.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

# servers 정책 — 도메인 하드코딩 금지, 배포지/프록시 변경 시 자동 반영.
#  1) DUMMY_PUBLIC_URL 설정 시 그 값을 우선 사용(명시적 고정이 필요한 경우만).
#  2) 미설정 시 요청 헤더(X-Forwarded-Proto/Host → Host)에서 실제 외부 주소를 동적 산출.
#     → 어떤 서버/도메인에 배포해도 openapi.json 의 servers 가 그 주소로 맞춰짐.
# 기본 /openapi.json·/docs 는 비활성화하고 아래에서 요청 기반으로 직접 제공한다.
_PUBLIC_URL = os.getenv("DUMMY_PUBLIC_URL")

app = FastAPI(
    title="XpERP 입주자 관리 더미 API",
    description="STT 통화분석 기반 XpERP API 설계 모사(관리비·수납·검침·입주자·민원·회계·인사·차량). 테스트용.",
    version="3.0.0",
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)


def _resolve_server_url(request: Request) -> str:
    """요청이 들어온 실제 외부 주소를 산출(프록시/DDNS 뒤에서도 정확)."""
    if _PUBLIC_URL:
        return _PUBLIC_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    # X-Forwarded-Host 는 'host[:port]' 형태이며 다중일 경우 첫 항목 사용.
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    # 프록시가 호스트에 포트를 안 붙였으면 X-Forwarded-Port 로 보완(비표준 포트만).
    fwd_port = request.headers.get("x-forwarded-port")
    if host and ":" not in host and fwd_port and fwd_port not in ("80", "443"):
        host = f"{host}:{fwd_port}"
    if host:
        return f"{proto}://{host}"
    return str(request.base_url).rstrip("/")


@app.get("/openapi.json", include_in_schema=False)
def custom_openapi(request: Request):
    if not app.openapi_schema:
        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
    # 요청마다 실제 호스트로 servers 를 갱신(고정 도메인 미사용).
    app.openapi_schema["servers"] = [{"url": _resolve_server_url(request)}]
    return app.openapi_schema


@app.get("/docs", include_in_schema=False)
def swagger_ui():
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")

# 테스트 더미 서버 → 교차 출처 호출 허용(any origin). 운영 전환 시 도메인 화이트리스트로 제한 권장.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

APT_NAME = "○○아파트"

# 단지 레지스트리(아파트명 ↔ 단지코드). 챗봇이 발화에서 추출한 아파트명을 aptcd 로 변환할 때 사용.
_APARTMENTS: list[dict] = [
    {"aptcd": "001023", "name": APT_NAME, "address": "서울시 강남구"},
    {"aptcd": "001045", "name": "한빛마을아파트", "address": "서울시 송파구"},
    {"aptcd": "002011", "name": "푸른숲아파트", "address": "경기도 성남시 분당구"},
    {"aptcd": "002099", "name": "강변래미안", "address": "서울시 광진구"},
    {"aptcd": "003007", "name": "햇살가득아파트", "address": "인천시 연수구"},
]


# ===========================================================================
# 인메모리 시드 데이터 — 단지 001023
# ===========================================================================
def _seed_units() -> list[dict]:
    return [
        {
            "aptcd": "001023", "dong": "101", "ho": "305",
            "name": "홍길동", "phone": "010-1234-5678",
            "movein": "2022-03-15", "moveout": None, "members": 3, "status": "정상",
            "charge": {"공용관리비": 45200, "전기료": 28000, "수도료": 12800, "기타": 42000},
            "paid": True, "pay_date": "2025-10-05", "pay_method": "계좌이체", "payer": "홍길동",
            "unpaid_months": 0,
            "meter": {"수도": {"usage": 12.3, "prev": 11.8}, "전기": {"usage": 240, "prev": 250},
                      "가스": {"usage": 18, "prev": 22}, "난방": {"usage": 0.4, "prev": 0.5}},
            "vehicles": [{"car_no": "12가3456", "model": "현대 소나타", "reg_date": "2024-03-15", "cancel_date": None}],
        },
        {
            "aptcd": "001023", "dong": "101", "ho": "202",
            "name": "김영수", "phone": "010-2222-3333",
            "movein": "2021-07-01", "moveout": None, "members": 2, "status": "정상",
            "charge": {"공용관리비": 40100, "전기료": 19000, "수도료": 9800, "기타": 31000},
            "paid": True, "pay_date": "2025-10-04", "pay_method": "자동이체", "payer": "김영수",
            "unpaid_months": 0,
            "meter": {"수도": {"usage": 8.6, "prev": 9.0}, "전기": {"usage": 180, "prev": 175},
                      "가스": {"usage": 14, "prev": 13}, "난방": {"usage": 0.3, "prev": 0.3}},
            "vehicles": [{"car_no": "34나7890", "model": "기아 K5", "reg_date": "2022-01-10", "cancel_date": None}],
        },
        {
            "aptcd": "001023", "dong": "101", "ho": "101",
            "name": "이순신", "phone": "010-4444-5555",
            "movein": "2020-01-10", "moveout": None, "members": 4, "status": "정상",
            "charge": {"공용관리비": 52300, "전기료": 33000, "수도료": 15200, "기타": 48000},
            "paid": False, "pay_date": None, "pay_method": None, "payer": None,
            "unpaid_months": 3,
            "meter": {"수도": {"usage": 16.1, "prev": 15.0}, "전기": {"usage": 310, "prev": 300},
                      "가스": {"usage": 25, "prev": 24}, "난방": {"usage": 0.6, "prev": 0.5}},
            "vehicles": [],
        },
        {
            "aptcd": "001023", "dong": "102", "ho": "501",
            "name": "박미경", "phone": "010-6666-7777",
            "movein": "2023-05-20", "moveout": None, "members": 1, "status": "정상",
            "charge": {"공용관리비": 38800, "전기료": 15000, "수도료": 7600, "기타": 22000},
            "paid": False, "pay_date": None, "pay_method": None, "payer": None,
            "unpaid_months": 1,
            "meter": {"수도": {"usage": 6.2, "prev": 6.0}, "전기": {"usage": 120, "prev": 130},
                      "가스": {"usage": 9, "prev": 10}, "난방": {"usage": 0.2, "prev": 0.2}},
            "vehicles": [{"car_no": "56다1234", "model": "테슬라 모델3", "reg_date": "2023-06-01", "cancel_date": None}],
        },
        {
            "aptcd": "001023", "dong": "103", "ho": "808",
            "name": "최강", "phone": "010-8888-9999",
            "movein": "2019-11-05", "moveout": "2025-09-30", "members": 0, "status": "전출",
            "charge": {"공용관리비": 0, "전기료": 0, "수도료": 0, "기타": 0},
            "paid": True, "pay_date": "2025-09-28", "pay_method": "현금", "payer": "최강",
            "unpaid_months": 0,
            "meter": {"수도": {"usage": 0, "prev": 5.0}, "전기": {"usage": 0, "prev": 90},
                      "가스": {"usage": 0, "prev": 8}, "난방": {"usage": 0, "prev": 0.1}},
            "vehicles": [{"car_no": "78라5678", "model": "폭스바겐 골프", "reg_date": "2020-02-01", "cancel_date": "2025-09-30"}],
        },
    ]


_UNITS: list[dict] = _seed_units()

_COMPLAINTS: list[dict] = [
    {"cmpl_id": "C2025-0034", "aptcd": "001023", "type": "누수", "dong": "101", "ho": "303",
     "recv_date": "2025-10-18", "summary": "천장 누수 발생", "status": "처리중",
     "manager": "김관리", "result": "배관팀 점검 예정"},
    {"cmpl_id": "C2025-0035", "aptcd": "001023", "type": "주차", "dong": "102", "ho": "501",
     "recv_date": "2025-10-20", "summary": "주차 불편 민원", "status": "처리중",
     "manager": "김관리", "result": "주차구획 재배정 검토"},
    {"cmpl_id": "C2025-0030", "aptcd": "001023", "type": "소음", "dong": "101", "ho": "202",
     "recv_date": "2025-10-10", "summary": "층간소음 신고", "status": "완료",
     "manager": "이주임", "result": "당사자 협의 완료"},
]

_STAFF: list[dict] = [
    {"aptcd": "001023", "name": "김관리", "title": "관리소장", "phone": "010-0000-1111",
     "salary": 3800000, "join_date": "2018-03-01", "status": "재직"},
    {"aptcd": "001023", "name": "이경비", "title": "경비원", "phone": "010-0000-2222",
     "salary": 2300000, "join_date": "2020-06-15", "status": "재직"},
    {"aptcd": "001023", "name": "박미화", "title": "미화원", "phone": "010-0000-3333",
     "salary": 2100000, "join_date": "2021-09-01", "status": "재직"},
    {"aptcd": "001023", "name": "정설비", "title": "시설기사", "phone": "010-0000-4444",
     "salary": 3200000, "join_date": "2019-01-20", "status": "재직"},
]


# ===========================================================================
# 헬퍼
# ===========================================================================
def _check_aptcd(aptcd: str) -> None:
    if not (aptcd and aptcd.isascii() and aptcd.isdigit() and len(aptcd) == 6):
        raise HTTPException(status_code=400, detail="aptcd 는 6자리 숫자 단지코드여야 합니다 (예: 001023)")


def _filter_units(aptcd: str, dong: Optional[str] = None, ho: Optional[str] = None) -> list[dict]:
    out = [u for u in _UNITS if u["aptcd"] == aptcd]
    if dong is not None:
        out = [u for u in out if u["dong"] == dong]
    if ho is not None:
        out = [u for u in out if u["ho"] == ho]
    return out


def _charge_total(u: dict) -> int:
    return sum(u["charge"].values())


# ===========================================================================
# 응답 모델 — OpenAPI 응답 스키마 노출용(에디터 '리턴값 미리보기'가 이 스키마를 사용)
# ===========================================================================
class AptItem(BaseModel):
    aptcd: str
    name: str
    address: Optional[str] = None


class AptCodeResp(BaseModel):
    query: str
    count: int
    items: list[AptItem]
    aptcd: Optional[str] = None
    name: Optional[str] = None
    resolved: Optional[bool] = None
    needs_input: Optional[bool] = None
    reason: Optional[str] = None
    message: Optional[str] = None


class AptListResp(BaseModel):
    count: int
    items: list[AptItem]


class ImpoItem(BaseModel):
    dong: str
    ho: str
    name: str
    yearmon: str
    total: int
    breakdown: dict


class ImpoDetailResp(BaseModel):
    apt_name: str
    aptcd: str
    yearmon: str
    count: int
    total_sum: int
    items: list[ImpoItem]


class RecpUnpaidResp(BaseModel):
    aptcd: str
    yearmon: str
    months: int
    unpaid_count: int
    unpaid_sum: int
    collection_rate: float
    total_units: int


class UnpaidRow(BaseModel):
    dong: str
    ho: str
    name: str
    amount: int
    unpaid_months: int


class RecpUnpaidListResp(BaseModel):
    aptcd: str
    yearmon: str
    months: int
    count: int
    items: list[UnpaidRow]


class RecpStatusResp(BaseModel):
    aptcd: str
    dong: str
    ho: str
    yearmon: str
    name: str
    paid: bool
    amount: int
    pay_date: Optional[str] = None
    pay_method: Optional[str] = None
    payer: Optional[str] = None


class RecpHistory(BaseModel):
    seq: str
    pay_date: Optional[str] = None
    amount: int
    method: Optional[str] = None
    payer: Optional[str] = None
    yearmon: str


class RecpDetailResp(BaseModel):
    aptcd: str
    dong: str
    ho: str
    name: str
    history: list[RecpHistory]


class InspStatusResp(BaseModel):
    aptcd: str
    yearmon: str
    type: str
    total: int
    done: int
    missing: int
    avg_usage: float


class InspUsageRow(BaseModel):
    dong: str
    ho: str
    usage: float
    prev: float
    diff: float
    abnormal: bool


class InspUsageResp(BaseModel):
    aptcd: str
    yearmon: str
    type: str
    count: int
    items: list[InspUsageRow]


class InspMissingRow(BaseModel):
    dong: str
    ho: str
    name: str


class InspMissingResp(BaseModel):
    aptcd: str
    yearmon: str
    type: str
    count: int
    items: list[InspMissingRow]


class UnitView(BaseModel):
    aptcd: str
    dong: str
    ho: str
    name: str
    phone: Optional[str] = None
    movein: Optional[str] = None
    moveout: Optional[str] = None
    members: int
    status: str


class OccpListResp(BaseModel):
    aptcd: str
    count: int
    items: list[UnitView]


class Complaint(BaseModel):
    cmpl_id: str
    aptcd: str
    type: str
    dong: str
    ho: str
    recv_date: str
    summary: str
    status: str
    manager: str
    result: str


class CmplListResp(BaseModel):
    aptcd: str
    count: int
    items: list[Complaint]


class AcctSummaryResp(BaseModel):
    aptcd: str
    yearmon: str
    income: int
    expense: int
    balance: int
    prev_balance: int


class BudgetItem(BaseModel):
    name: str
    budget: int
    spent: int
    rate: float


class AcctBudgetResp(BaseModel):
    aptcd: str
    year: str
    items: list[BudgetItem]


class Staff(BaseModel):
    aptcd: str
    name: str
    title: str
    phone: str
    salary: int
    join_date: str
    status: str


class HrStaffResp(BaseModel):
    aptcd: str
    apt_name: str
    yearmon: Optional[str] = None
    count: int
    salary_sum: int
    items: list[Staff]


class VehicleRow(BaseModel):
    dong: str
    ho: str
    name: str
    car_no: str
    model: str
    reg_date: str
    cancel_date: Optional[str] = None
    status: str


class ParkVehicleResp(BaseModel):
    aptcd: str
    count: int
    items: list[VehicleRow]


# ===========================================================================
# APT — 단지(아파트명 → 단지코드) 조회
# ===========================================================================
@app.get("/apt/code", response_model=AptCodeResp, summary="아파트명으로 단지코드 조회", tags=["APT 단지"])
def apt_code(
    name: str = Query(..., description="아파트명(부분 일치)", example="래미안"),
):
    """아파트명(부분 일치)으로 단지코드(aptcd)를 조회한다.

    공백 제거 부분 문자열(대소문자 무시) 매칭.
    응답에 챗봇 되묻기 힌트 필드를 포함한다:
      - resolved   : 단지코드가 한 곳으로 확정됐는지(bool)
      - needs_input: 사용자에게 추가/정정 입력을 요청해야 하는지(bool)
      - reason     : "ok" | "ambiguous"(다건) | "not_found"(무매칭)
      - message    : 챗봇이 그대로 사용할 안내 문구
    단건(resolved=True)이면 aptcd·name 을 최상위로도 반환해 후속 API(/impo/detail 등)에 바로 체이닝한다.
    """
    key = name.replace(" ", "").lower()
    rows = [a for a in _APARTMENTS if key in a["name"].replace(" ", "").lower()]
    result = {"query": name, "count": len(rows), "items": rows}
    if len(rows) == 1:
        result.update({
            "aptcd": rows[0]["aptcd"], "name": rows[0]["name"],
            "resolved": True, "needs_input": False, "reason": "ok",
            "message": f"단지코드 {rows[0]['aptcd']}({rows[0]['name']})로 조회합니다.",
        })
    elif len(rows) == 0:
        result.update({
            "resolved": False, "needs_input": True, "reason": "not_found",
            "message": f"'{name}'에 해당하는 단지를 찾지 못했습니다. 아파트명을 다시 확인해 주세요.",
        })
    else:
        names = ", ".join(a["name"] for a in rows)
        result.update({
            "resolved": False, "needs_input": True, "reason": "ambiguous",
            "message": f"'{name}'에 해당하는 단지가 {len(rows)}곳입니다({names}). 어느 단지인지 선택해 주세요.",
        })
    return result


@app.get("/apt/list", response_model=AptListResp, summary="단지 목록", tags=["APT 단지"])
def apt_list():
    return {"count": len(_APARTMENTS), "items": _APARTMENTS}


# ===========================================================================
# IMPO — 관리비·부과 조회
# ===========================================================================
@app.get("/impo/detail", response_model=ImpoDetailResp, summary="관리비·부과 조회", tags=["IMPO 관리비"])
def impo_detail(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    yearmon: str = Query(..., description="조회년월 YYYYMM", example="202510"),
    dong: Optional[str] = Query(None, description="동", example="101"),
    ho: Optional[str] = Query(None, description="호수", example="305"),
):
    _check_aptcd(aptcd)
    units = _filter_units(aptcd, dong, ho)
    items = [{
        "dong": u["dong"], "ho": u["ho"], "name": u["name"],
        "yearmon": yearmon, "total": _charge_total(u), "breakdown": u["charge"],
    } for u in units if u["status"] != "전출"]
    return {
        "apt_name": APT_NAME, "aptcd": aptcd, "yearmon": yearmon,
        "count": len(items), "total_sum": sum(i["total"] for i in items),
        "items": items,
    }


# ===========================================================================
# RECP — 미납·연체 / 수납·이력
# ===========================================================================
@app.get("/recp/unpaid", response_model=RecpUnpaidResp, summary="미납·연체 현황 요약", tags=["RECP 수납"])
def recp_unpaid(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    yearmon: str = Query(..., description="기준년월 YYYYMM", example="202510"),
    months: int = Query(1, description="체납 기준 개월수", example=3),
):
    _check_aptcd(aptcd)
    active = [u for u in _filter_units(aptcd) if u["status"] != "전출"]
    unpaid = [u for u in active if not u["paid"] and u["unpaid_months"] >= months]
    unpaid_sum = sum(_charge_total(u) for u in unpaid)
    rate = round((len(active) - len([u for u in active if not u["paid"]])) / len(active) * 100, 1) if active else 0.0
    return {
        "aptcd": aptcd, "yearmon": yearmon, "months": months,
        "unpaid_count": len(unpaid), "unpaid_sum": unpaid_sum,
        "collection_rate": rate, "total_units": len(active),
    }


@app.get("/recp/unpaid/list", response_model=RecpUnpaidListResp, summary="미납 세대 목록", tags=["RECP 수납"])
def recp_unpaid_list(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    yearmon: str = Query(..., description="기준년월 YYYYMM", example="202510"),
    months: int = Query(1, description="체납 기준 개월수", example=3),
):
    _check_aptcd(aptcd)
    rows = [{
        "dong": u["dong"], "ho": u["ho"], "name": u["name"],
        "amount": _charge_total(u), "unpaid_months": u["unpaid_months"],
    } for u in _filter_units(aptcd)
        if u["status"] != "전출" and not u["paid"] and u["unpaid_months"] >= months]
    return {"aptcd": aptcd, "yearmon": yearmon, "months": months, "count": len(rows), "items": rows}


@app.get("/recp/status", response_model=RecpStatusResp, summary="세대 수납 현황", tags=["RECP 수납"])
def recp_status(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    dong: str = Query(..., description="동", example="101"),
    ho: str = Query(..., description="호수", example="202"),
    yearmon: str = Query(..., description="조회년월 YYYYMM", example="202510"),
):
    _check_aptcd(aptcd)
    units = _filter_units(aptcd, dong, ho)
    if not units:
        raise HTTPException(status_code=404, detail=f"세대 없음: {aptcd} {dong}-{ho}")
    u = units[0]
    return {
        "aptcd": aptcd, "dong": dong, "ho": ho, "yearmon": yearmon, "name": u["name"],
        "paid": u["paid"], "amount": _charge_total(u),
        "pay_date": u["pay_date"], "pay_method": u["pay_method"], "payer": u["payer"],
    }


@app.get("/recp/detail", response_model=RecpDetailResp, summary="수납 이력 상세", tags=["RECP 수납"])
def recp_detail(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    dong: str = Query(..., description="동", example="101"),
    ho: str = Query(..., description="호수", example="202"),
    yearmon: str = Query(..., description="조회년월 YYYYMM", example="202510"),
):
    _check_aptcd(aptcd)
    units = _filter_units(aptcd, dong, ho)
    if not units:
        raise HTTPException(status_code=404, detail=f"세대 없음: {aptcd} {dong}-{ho}")
    u = units[0]
    history = []
    if u["paid"]:
        history.append({
            "seq": "20251005-0001", "pay_date": u["pay_date"], "amount": _charge_total(u),
            "method": u["pay_method"], "payer": u["payer"], "yearmon": yearmon,
        })
    return {"aptcd": aptcd, "dong": dong, "ho": ho, "name": u["name"], "history": history}


# ===========================================================================
# INSP — 검침·사용량
# ===========================================================================
_METER_TYPES = ["수도", "전기", "가스", "난방"]


@app.get("/insp/status", response_model=InspStatusResp, summary="검침 현황 요약", tags=["INSP 검침"])
def insp_status(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    yearmon: str = Query(..., description="조회년월 YYYYMM", example="202510"),
    type: str = Query("수도", description="검침종류(수도·전기·가스·난방)", example="수도"),
    dong: Optional[str] = Query(None, description="동"),
    ho: Optional[str] = Query(None, description="호수"),
):
    _check_aptcd(aptcd)
    if type not in _METER_TYPES:
        raise HTTPException(status_code=400, detail=f"type 은 {_METER_TYPES} 중 하나")
    units = [u for u in _filter_units(aptcd, dong, ho) if u["status"] != "전출"]
    done = [u for u in units if u["meter"][type]["usage"] > 0]
    avg = round(sum(u["meter"][type]["usage"] for u in done) / len(done), 1) if done else 0.0
    return {
        "aptcd": aptcd, "yearmon": yearmon, "type": type,
        "total": len(units), "done": len(done), "missing": len(units) - len(done),
        "avg_usage": avg,
    }


@app.get("/insp/usage", response_model=InspUsageResp, summary="세대별 검침 사용량", tags=["INSP 검침"])
def insp_usage(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    yearmon: str = Query(..., description="조회년월 YYYYMM", example="202510"),
    type: str = Query("수도", description="검침종류", example="수도"),
    dong: Optional[str] = Query(None, description="동"),
    ho: Optional[str] = Query(None, description="호수"),
):
    _check_aptcd(aptcd)
    if type not in _METER_TYPES:
        raise HTTPException(status_code=400, detail=f"type 은 {_METER_TYPES} 중 하나")
    rows = []
    for u in _filter_units(aptcd, dong, ho):
        if u["status"] == "전출":
            continue
        m = u["meter"][type]
        diff = round(m["usage"] - m["prev"], 1)
        rows.append({
            "dong": u["dong"], "ho": u["ho"], "usage": m["usage"], "prev": m["prev"],
            "diff": diff, "abnormal": abs(diff) >= 3,
        })
    return {"aptcd": aptcd, "yearmon": yearmon, "type": type, "count": len(rows), "items": rows}


@app.get("/insp/missing", response_model=InspMissingResp, summary="미검침 세대 목록", tags=["INSP 검침"])
def insp_missing(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    yearmon: str = Query(..., description="조회년월 YYYYMM", example="202510"),
    type: str = Query("수도", description="검침종류", example="수도"),
):
    _check_aptcd(aptcd)
    if type not in _METER_TYPES:
        raise HTTPException(status_code=400, detail=f"type 은 {_METER_TYPES} 중 하나")
    rows = [{"dong": u["dong"], "ho": u["ho"], "name": u["name"]}
            for u in _filter_units(aptcd)
            if u["status"] != "전출" and u["meter"][type]["usage"] <= 0]
    return {"aptcd": aptcd, "yearmon": yearmon, "type": type, "count": len(rows), "items": rows}


# ===========================================================================
# OCCP — 입주자·세대 정보 (조회 + 쓰기/전출처리)
# ===========================================================================
def _unit_view(u: dict) -> dict:
    return {
        "aptcd": u["aptcd"], "dong": u["dong"], "ho": u["ho"], "name": u["name"],
        "phone": u["phone"], "movein": u["movein"], "moveout": u["moveout"],
        "members": u["members"], "status": u["status"],
    }


@app.get("/occp/unit", summary="입주자·세대 단건/조건 조회", tags=["OCCP 입주자"])
def occp_unit(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    dong: Optional[str] = Query(None, description="동", example="101"),
    ho: Optional[str] = Query(None, description="호수", example="305"),
):
    _check_aptcd(aptcd)
    units = _filter_units(aptcd, dong, ho)
    if dong is not None and ho is not None:
        if not units:
            raise HTTPException(status_code=404, detail=f"세대 없음: {aptcd} {dong}-{ho}")
        return _unit_view(units[0])
    return {"aptcd": aptcd, "count": len(units), "items": [_unit_view(u) for u in units]}


@app.get("/occp/list", response_model=OccpListResp, summary="세대 목록(전출 포함)", tags=["OCCP 입주자"])
def occp_list(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    status: Optional[str] = Query(None, description="세대 상태(정상·전출·공실)", example="전출"),
):
    _check_aptcd(aptcd)
    units = _filter_units(aptcd)
    if status:
        units = [u for u in units if u["status"] == status]
    return {"aptcd": aptcd, "count": len(units), "items": [_unit_view(u) for u in units]}


class UnitCreate(BaseModel):
    aptcd: str
    dong: str
    ho: str
    name: str
    phone: Optional[str] = None
    movein: Optional[str] = None
    members: int = 1


class UnitReplace(BaseModel):
    """PUT — 세대 정보 전체 교체."""
    name: str
    phone: Optional[str] = None
    movein: Optional[str] = None
    moveout: Optional[str] = None
    members: int = 1
    status: str = "정상"


class UnitPatch(BaseModel):
    """PATCH — 부분 수정(전출 처리 등). 보낸 필드만 갱신."""
    name: Optional[str] = None
    phone: Optional[str] = None
    movein: Optional[str] = None
    moveout: Optional[str] = None
    members: Optional[int] = None
    status: Optional[str] = None


def _new_unit_defaults(rec: dict) -> dict:
    rec.setdefault("moveout", None)
    rec.setdefault("status", "정상")
    rec.setdefault("charge", {"공용관리비": 0, "전기료": 0, "수도료": 0, "기타": 0})
    rec.setdefault("paid", False)
    rec.setdefault("pay_date", None)
    rec.setdefault("pay_method", None)
    rec.setdefault("payer", None)
    rec.setdefault("unpaid_months", 0)
    rec.setdefault("meter", {t: {"usage": 0, "prev": 0} for t in _METER_TYPES})
    rec.setdefault("vehicles", [])
    return rec


@app.post("/occp/unit", status_code=201, summary="입주자 등록", tags=["OCCP 입주자"])
def occp_create(body: UnitCreate):
    _check_aptcd(body.aptcd)
    if _filter_units(body.aptcd, body.dong, body.ho):
        raise HTTPException(status_code=409, detail=f"이미 존재하는 세대: {body.aptcd} {body.dong}-{body.ho}")
    rec = _new_unit_defaults({
        "aptcd": body.aptcd, "dong": body.dong, "ho": body.ho,
        "name": body.name, "phone": body.phone, "movein": body.movein, "members": body.members,
    })
    _UNITS.append(rec)
    return {"status": "created", "unit": _unit_view(rec)}


@app.put("/occp/unit", summary="입주자 정보 전체 교체", tags=["OCCP 입주자"])
def occp_replace(
    body: UnitReplace,
    aptcd: str = Query(..., description="단지코드(6자리)"),
    dong: str = Query(..., description="동"),
    ho: str = Query(..., description="호수"),
):
    _check_aptcd(aptcd)
    units = _filter_units(aptcd, dong, ho)
    if not units:
        raise HTTPException(status_code=404, detail=f"세대 없음: {aptcd} {dong}-{ho}")
    u = units[0]
    u.update({"name": body.name, "phone": body.phone, "movein": body.movein,
              "moveout": body.moveout, "members": body.members, "status": body.status})
    return {"status": "replaced", "unit": _unit_view(u)}


@app.patch("/occp/unit", summary="입주자 부분 수정/전출 처리", tags=["OCCP 입주자"])
def occp_patch(
    body: UnitPatch,
    aptcd: str = Query(..., description="단지코드(6자리)"),
    dong: str = Query(..., description="동"),
    ho: str = Query(..., description="호수"),
):
    _check_aptcd(aptcd)
    units = _filter_units(aptcd, dong, ho)
    if not units:
        raise HTTPException(status_code=404, detail=f"세대 없음: {aptcd} {dong}-{ho}")
    u = units[0]
    changes = body.model_dump(exclude_unset=True)
    u.update(changes)
    return {"status": "patched", "changed": list(changes.keys()), "unit": _unit_view(u)}


@app.delete("/occp/unit", summary="세대 삭제", tags=["OCCP 입주자"])
def occp_delete(
    aptcd: str = Query(..., description="단지코드(6자리)"),
    dong: str = Query(..., description="동"),
    ho: str = Query(..., description="호수"),
):
    _check_aptcd(aptcd)
    units = _filter_units(aptcd, dong, ho)
    if not units:
        raise HTTPException(status_code=404, detail=f"세대 없음: {aptcd} {dong}-{ho}")
    _UNITS.remove(units[0])
    return {"status": "deleted", "aptcd": aptcd, "dong": dong, "ho": ho}


# ===========================================================================
# CMPL — 민원 접수·처리
# ===========================================================================
@app.get("/cmpl/list", response_model=CmplListResp, summary="민원 목록", tags=["CMPL 민원"])
def cmpl_list(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    status: Optional[str] = Query(None, description="처리상태(접수·처리중·완료)", example="처리중"),
):
    _check_aptcd(aptcd)
    rows = [c for c in _COMPLAINTS if c["aptcd"] == aptcd]
    if status:
        rows = [c for c in rows if c["status"] == status]
    return {"aptcd": aptcd, "count": len(rows), "items": rows}


@app.get("/cmpl/{cmpl_id}", response_model=Complaint, summary="민원 단건 조회", tags=["CMPL 민원"])
def cmpl_get(cmpl_id: str):
    for c in _COMPLAINTS:
        if c["cmpl_id"] == cmpl_id:
            return c
    raise HTTPException(status_code=404, detail=f"민원 없음: {cmpl_id}")


# ===========================================================================
# ACCT — 회계·예산
# ===========================================================================
@app.get("/acct/summary", response_model=AcctSummaryResp, summary="월별 회계 현황 요약", tags=["ACCT 회계"])
def acct_summary(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    yearmon: str = Query(..., description="조회년월 YYYYMM", example="202510"),
):
    _check_aptcd(aptcd)
    income, expense = 45230000, 38120000
    return {
        "aptcd": aptcd, "yearmon": yearmon,
        "income": income, "expense": expense, "balance": income - expense,
        "prev_balance": 6480000,
    }


@app.get("/acct/budget", response_model=AcctBudgetResp, summary="예산 집행률", tags=["ACCT 회계"])
def acct_budget(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    year: Optional[str] = Query(None, description="예산 기준연도", example="2025"),
):
    _check_aptcd(aptcd)
    items = [
        {"name": "일반관리비", "budget": 120000000, "spent": 92400000},
        {"name": "청소·경비", "budget": 84000000, "spent": 70200000},
        {"name": "수선유지", "budget": 60000000, "spent": 31800000},
        {"name": "전기·수도", "budget": 96000000, "spent": 78500000},
    ]
    for it in items:
        it["rate"] = round(it["spent"] / it["budget"] * 100, 1)
    return {"aptcd": aptcd, "year": year or "2025", "items": items}


# ===========================================================================
# HR — 인사·급여
# ===========================================================================
@app.get("/hr/staff", response_model=HrStaffResp, summary="직원·급여 현황", tags=["HR 인사"])
def hr_staff(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    yearmon: Optional[str] = Query(None, description="급여년월 YYYYMM", example="202510"),
):
    _check_aptcd(aptcd)
    rows = [s for s in _STAFF if s["aptcd"] == aptcd]
    return {
        "aptcd": aptcd, "apt_name": APT_NAME, "yearmon": yearmon,
        "count": len(rows), "salary_sum": sum(s["salary"] for s in rows), "items": rows,
    }


# ===========================================================================
# PARK — 차량·주차
# ===========================================================================
@app.get("/park/vehicle", response_model=ParkVehicleResp, summary="차량·주차 조회", tags=["PARK 차량"])
def park_vehicle(
    aptcd: str = Query(..., description="단지코드(6자리)", example="001023"),
    car_no: Optional[str] = Query(None, description="차량번호", example="12가3456"),
    dong: Optional[str] = Query(None, description="동", example="101"),
):
    _check_aptcd(aptcd)
    rows = []
    for u in _filter_units(aptcd, dong):
        for v in u["vehicles"]:
            if car_no and v["car_no"] != car_no:
                continue
            rows.append({
                "dong": u["dong"], "ho": u["ho"], "name": u["name"],
                "car_no": v["car_no"], "model": v["model"],
                "reg_date": v["reg_date"], "cancel_date": v["cancel_date"],
                "status": "해지" if v["cancel_date"] else "정상",
            })
    return {"aptcd": aptcd, "count": len(rows), "items": rows}


# ===========================================================================
# 공통
# ===========================================================================
@app.get("/", summary="루트(연결 테스트용)", tags=["공통"])
def root():
    # MCP 콘솔의 '연결 테스트'가 Base URL 루트(/)를 호출하므로 200 을 반환해야 한다.
    return {"ok": True, "service": app.title, "version": app.version, "docs": "/docs"}


@app.get("/health", summary="헬스 체크", tags=["공통"])
def health():
    return {"ok": True, "units": len(_UNITS)}
