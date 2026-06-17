# Handoff: MCP Provider — 워크플로우 빌더 UI 리디자인

## Overview
MCP Provider는 OpenAPI/Swagger 스펙을 업로드하면 각 API 오퍼레이션을 "노드"로 만들고, 드래그앤드롭 캔버스에서 노드를 엣지로 연결해 워크플로우를 구성·실행하는 노코드 빌더입니다. 완성된 워크플로우는 MCP 서버로 외부 MCP 클라이언트(Claude Desktop 등)에 도구로 노출됩니다. 사용자에는 **API에 익숙하지 않은 실무자**가 포함되며, **UI 언어는 한국어**입니다.

이 핸드오프는 빌더 전반의 **비주얼 시스템(디자인 토큰), 컴포넌트, 핵심 화면 목업, 접근성 기준, 제어 흐름(IF/Loop/Switch/Batch/Merge/Filter) 노드, 캔버스 정렬 도구**를 정의합니다.

## About the Design Files
이 번들의 파일은 **HTML로 만든 디자인 레퍼런스**입니다 — 의도한 룩앤필과 동작을 보여주는 프로토타입이며, 그대로 복사해 배포하는 프로덕션 코드가 아닙니다.

**구현 목표 환경(중요 제약):**
- 서버 렌더(**Jinja2 템플릿**) + **htmx** + **Drawflow** 캔버스. 빌드 도구 없음(CDN/정적 에셋).
- **Tailwind 컴파일 불가** → 디자인 토큰은 **순수 CSS 변수(`:root`)** 로 제공됨. 그대로 가져다 쓰세요.
- **Drawflow** 라이브러리라서 노드 DOM 바깥 구조는 크게 바꾸기 어렵습니다 → 스타일은 **노드 카드 "내부"** 중심으로 적용.
- **데스크톱 우선**(넓은 캔버스). 한국어 라벨 길이를 고려할 것.

따라서 작업은 "HTML을 그대로 이식"이 아니라, **위 환경의 패턴(Jinja2 partial, htmx 트리거, Drawflow 노드 템플릿)으로 이 디자인을 재현**하는 것입니다.

## Fidelity
**High-fidelity (hifi).** 최종 색·타이포·간격·상태·인터랙션이 모두 확정된 픽셀 단위 목업입니다. 아래 토큰/사양의 정확한 값(hex, px, weight)을 그대로 사용해 재현하세요.

---

## Design Tokens

라이트(기본) + 다크(토글) 두 테마. `:root`는 라이트, `[data-theme="dark"]`로 다크 오버라이드. **그대로 `tokens.css`로 사용 가능.**

```css
:root{
  /* surfaces */
  --canvas:#F4F6F9; --canvas-dots:#D5DAE2;
  --surface:#FFFFFF; --surface-2:#F7F9FB; --surface-3:#EEF1F5;
  --border:#E6EAEF; --border-strong:#D5DAE2;
  /* text */
  --text-1:#1A2231; --text-2:#5C6675; --text-3:#8A94A6;
  /* brand + semantic */
  --brand:#0E9E74; --brand-hover:#0B8A65; --brand-weak:#E3F7EE; --brand-text:#0E8A5F;
  --success:#16A34A; --success-weak:#E3F7EE;
  --danger:#E5484D;  --danger-weak:#FDE8E8;
  --warn:#B7791F;    --warn-weak:#FFF3DD;
  --skip:#98A2B3;    --skip-weak:#EEF1F5;
  --focus:rgba(14,158,116,.40);
  /* method badges */
  --m-get:#1D6FE0;    --m-get-bg:#E5F0FF;
  --m-post:#0E8A5F;   --m-post-bg:#E3F7EE;
  --m-put:#B7791F;    --m-put-bg:#FFF3DD;
  --m-patch:#6D45D6;  --m-patch-bg:#F0EBFF;
  --m-delete:#D03939; --m-delete-bg:#FDE8E8;
  /* control-flow (logic) nodes */
  --logic-branch:#7C5CFF; --logic-branch-bg:#F0EBFF; --logic-branch-text:#6D45D6;
  --logic-loop:#E8883B;   --logic-loop-bg:#FDF0E3;   --logic-loop-text:#B7791F;
  --logic-merge:#3B82F6;  --logic-merge-bg:#E8F1FE;  --logic-merge-text:#1D6FE0;
  /* type + shape */
  --font-ui:'Plus Jakarta Sans',system-ui,sans-serif;
  --font-mono:'JetBrains Mono',ui-monospace,monospace;
  --r-sm:6px; --r-md:8px; --r-lg:12px; --r-xl:16px; --r-pill:999px;
  --sh-1:0 1px 2px rgba(16,24,40,.06);
  --sh-2:0 2px 8px rgba(16,24,40,.08);
  --sh-3:0 8px 24px -6px rgba(16,24,40,.16);
}
[data-theme="dark"]{
  --canvas:#0C0F16; --canvas-dots:#1E2533;
  --surface:#151A23; --surface-2:#1A2029; --surface-3:#222A36;
  --border:#262E3B; --border-strong:#313B4A;
  --text-1:#EAEDF3; --text-2:#8A94A6; --text-3:#5B6577;
  --brand:#2DD4A7; --brand-hover:#34E0B3; --brand-weak:rgba(45,212,167,.14); --brand-text:#2DD4A7;
  --success:#34D399; --success-weak:rgba(52,211,153,.14);
  --danger:#FB6F84;  --danger-weak:rgba(251,111,132,.14);
  --warn:#FBBF24;    --warn-weak:rgba(251,191,36,.14);
  --skip:#5B6577;    --skip-weak:#222A36;
  --focus:rgba(45,212,167,.45);
  --m-get:#4DA3FF;    --m-get-bg:rgba(77,163,255,.14);
  --m-post:#34D399;   --m-post-bg:rgba(52,211,153,.14);
  --m-put:#FBBF24;    --m-put-bg:rgba(251,191,36,.16);
  --m-patch:#B69CFF;  --m-patch-bg:rgba(182,156,255,.16);
  --m-delete:#FB6F84; --m-delete-bg:rgba(251,111,132,.16);
  --sh-2:0 4px 14px rgba(0,0,0,.45);
  --sh-3:0 8px 28px rgba(0,0,0,.55);
}
```

### Typography
- **UI 폰트**: `Plus Jakarta Sans` (Google Fonts, weights 400/500/600/700/800)
- **코드/경로 폰트**: `JetBrains Mono` (weights 400/500/600)
- 스케일: 30/800/-2% (페이지 H1) · 22/700 (섹션) · 16/600 (패널 헤더·노드 제목) · 13/500 (UI 기본) · 12/400 (캡션) · mono 12 (경로/코드)

### Spacing / Radius / Shadow
- 간격(4px 베이스): 4 · 8 · 12 · 16 · 24 · 32
- 라운드: 6(sm) · 8(md) · 12(lg) · 16(xl) · 999(pill)
- 그림자: `--sh-1`(미세) · `--sh-2`(카드) · `--sh-3`(팝오버/모달)

---

## Screens / Views

### 1) 에디터 (3분할) — 핵심 화면
빌더의 메인 화면. **상단 2단 툴바 + 좌측 오퍼레이션 패널 + 중앙 캔버스 + 우측 속성/로그 패널.**

**Layout**
- 전체: 세로 flex. 툴바 2줄(52px + 46px) 후 본문 `display:flex; height:100%`.
- 좌측 패널: `width:236px`, `background:var(--surface-2)`, 우측 보더.
- 중앙 캔버스: `flex:1`, `background:var(--canvas)` + 도트 그리드 `radial-gradient(var(--canvas-dots) 1.2px, transparent 1.2px); background-size:20px 20px`.
- 우측 패널: `width:296px`, `background:var(--surface)`, 좌측 보더.

**툴바 1행 (52px, `--surface`, 하단 보더)**
- 좌: 뒤로(‹) 아이콘 버튼(30px) + 워크플로우 제목(15px/700) + 편집(✎) 글리프.
- 우: 저장상태 칩("방금 저장됨" — success 칩, 좌측 6px 점) · 테마 토글 버튼(🌗 라이트/🌙 다크) · `저장`(secondary) · `실행`(primary, ▶ 아이콘).

**툴바 2행 (46px, `#FAFBFC`, MCP 설정 바)**
- `+start`(브랜드 점선 버튼) · `+end`(중립 점선) · 구분선 · `도구 이름` 인풋(mono) · `MCP 그룹` 인풋(mono) · (우측) `MCP 노출` 라벨 + 토글(ON=brand) + 상태 텍스트.

**좌측 패널 — 오퍼레이션 리스트**
- 헤더 "오퍼레이션"(12.5/700) + 검색 인풋(⌕ placeholder).
- 리스트 아이템(드래그 가능, `cursor:grab`): 좌측 그립(⠿) + [메서드 배지 + 경로(mono 10px, ellipsis)] + 한 줄 요약(11.5px). 호버 시 brand 외곽선 `box-shadow:0 0 0 2px rgba(14,158,116,.12)`.
- 탭 토글 있음: **오퍼레이션**(스펙에서) / **로직**(빌트인 제어 노드, 섹션 "제어 흐름 노드" 참조).

**중앙 캔버스**
- 좌하단 줌 컨트롤(+/−, 세로 스택, `--surface` + 보더 + `--sh-2`). 우상단 줌 배율 칩("100%").
- 노드는 절대 위치. 엣지는 SVG 베지어 곡선 + 화살표 마커.

**우측 패널 — 탭: 속성 / 실행 로그**
- 탭: 활성 = `--text-1`/700 + 하단 2px brand 보더, 비활성 = `--text-3`/600.
- **속성 탭(선택 노드)**: 메서드 배지 + 경로 헤더 → `Base URL` 인풋 → `Body`(JSON, 다크 코드블록 `#0C0F16`, 토큰 하이라이트: 문자열 `#34D399`, 변수 `#FBBF24`) → **엣지 데이터 매핑**(`노드1 · id  →  userId`, surface-2 박스, 화살표 brand).

### 2) 실행 다이얼로그 (모달)
**Layout**: 백드롭 딤 + 중앙 모달 `width:480px`, `--surface`, `--r-xl`, `--sh-3`.
- 헤더: 아이콘 타일(brand-weak) + "워크플로우 실행"(16/700) + 서브("…· API 노드 2개") + 닫기(✕).
- 모드 토글(세그먼트): `폼 모드`(활성=흰 배경+그림자) / `JSON 직접 편집`.
- **인증** 섹션: 라디오 세그먼트 `Bearer Token`(선택=brand-weak) / `API Key` + 토큰 인풋(mono, masked).
- **입력 파라미터**: 연결된 API 노드별 그룹 — [메서드 배지 + 노드명] 헤더 후 파라미터 행(`라벨(필수=*) + 인풋`). 이전 노드에서 자동 매핑되는 값은 점선 박스 + "이전 노드에서 자동 매핑" + 매핑 칩.
- 푸터: `취소`(ghost) / `실행하기`(primary, ▶).

### 3) 실행 로그 (우측 패널 탭)
- 실행 헤더: `실행 #12` 드롭다운 + 타임스탬프("방금 전 · 1.2s") + 전체 상태 칩(성공=brand-weak/✓, 실패=danger-weak/!).
- 노드 상태 카드(좌측 3px 상태 스트라이프): [상태 원형 아이콘 ✓/!/– + 메서드 배지 + 노드명 + 상태코드(200/401) + 소요시간 + 펼치기(▾/▴)].
- 펼친 카드: `input`/`output` 토글 + JSON 코드블록(다크). 실패 카드는 에러 메시지(danger) 노출. 스킵 노드는 점선 보더 + opacity 0.7.

### 4) 노드 카드 (캔버스 내부) — 상태 변형
**공통 구조**: `--surface` 카드, `--r-lg`, `--sh-2`, 상단 4px 상태 스트라이프. 본문 = [메서드 배지 + 경로(mono) + 상태/스피너] + 노드 제목(13/600). 좌/우 가장자리에 포트 점(9px 원, 흰 배경 + 2px 컬러 보더).

| 상태 | 스트라이프/보더 | 표식 |
|---|---|---|
| default | `--border` | — |
| selected | brand 1.5px + 외곽 ring `0 0 0 3px rgba(14,158,116,.18)` | — |
| running | 그라데이션 스트라이프(파랑) + 1.5px `--m-get` | 우측 스피너(13px) |
| 성공 | `--success` 스트라이프 + 연한 success 보더 | ✓ + `200` (success) |
| 실패 | `--danger` 스트라이프 + 연한 danger 보더 | ! + `401` (danger) |
| 스킵 | 회색 점선 보더, opacity 0.75 | "스킵" 라벨(skip) |

- **start 노드**: brand 아이콘 타일(▶) + "시작". **end 노드**: 중립 타일(■) + "종료".

---

## Components 사양 (상태별)

### Buttons
- **Primary**: `--brand` 배경/흰 글씨, `--r-md`, padding `9px 16px`, 13/600. hover=`--brand-hover`, active=더 어둡게+`translateY(1px)`, disabled=`#A9D9C8`.
  - ⚠️ **접근성 주의**: 흰 글씨 on `--brand`(#0E9E74)는 3.0:1 → 일반 텍스트 AA 미달. **버튼 채움만 `#0A7D5A`(4.6:1)로 어둡게** 사용 권장. `--brand`는 테두리·아이콘·큰 텍스트용.
- **Secondary**: `--surface` + `--border-strong` 보더, `--text-1`.
- **Ghost**: `--surface-3` 배경, `--text-2`, 보더 없음.
- **Danger**: `--danger-weak` 배경 + `--danger-text`.
- **+start / +end**: 점선 보더 버튼(start=brand 점선, end=중립 점선).
- **Icon button**: 34px(md) 정사각, `--surface` + 보더. 사이즈: sm 28px / md 34px / lg 40px.

### Inputs
- 기본: `--surface` + `--border-strong` 보더, `--r-md`, padding `9px 11px`, mono 또는 UI 13px.
- focus: 1.5px `--brand` 보더 + `0 0 0 3px var(--focus)` ring.
- error: 1.5px `--danger` 보더 + 하단 에러 메시지(danger, "⚠ …").
- disabled: `--canvas` 배경 + `--text-3` + `cursor:not-allowed`.

### Toggle (MCP 노출 등)
- 40×23px 트랙, 19px 노브. ON=`--brand`, OFF=`--border-strong`.

### Tabs
- 세그먼트형(우측 패널): 컨테이너 `--canvas` + padding 3px, 활성 탭=흰 배경+`--sh-1`. 또는 언더라인형(2px brand 하단 보더).

### Method Badges
mono 11px/600, `--r-sm`, padding `3px 9px`. `색 = --m-{method}`, `배경 = --m-{method}-bg`. (GET 읽기 / POST 생성 / PUT 교체 / PATCH 수정 / DELETE 삭제)

### Edges (연결선)
- 기본: 2px `--border-strong`, 포트 = 흰 원 + 2px 보더, 끝에 화살표 마커.
- 활성/성공: 2.5px `--success` 또는 brand 그라데이션.
- 스킵: `--border-strong` + `stroke-dasharray:6 4`(점선).
- 매핑 라벨: 엣지 중앙에 mono 9.5px 작은 칩(`id → userId`).
- 구현: SVG `path` 베지어. 좌표는 노드 포트 픽셀과 동일 좌표계로(상단-좌측 고정). Drawflow에서는 `updateConnectionNodes()`로 갱신.

### Toast
- `--surface` + `--border`, 좌측 3px 상태 보더, `--r-lg`, `--sh-2`. 좌측 상태 원형 아이콘(✓/!) + 메시지(12.5/500). 성공/실패 변형.

---

## 제어 흐름 노드 (IF / Switch / Loop / Batch / Merge / Filter)

API(데이터) 노드와 구분되는 **로직 노드 패밀리**. HTTP 메서드 배지 대신 **색 아이콘 타일 + 타입 칩**으로 식별. 색 코드:
- **분기**(violet `--logic-branch`): IF · Switch · Filter
- **반복**(amber `--logic-loop`): Loop · Batch
- **병합**(blue `--logic-merge`): Merge · Wait

**다중 출력 포트 + 라벨** (우측 가장자리 포트, 라벨 + 상태색 점):
- **IF**: `참(true)`(success 점) / `거짓(false)`(skip 점). 입력 1.
- **Switch**: `case "x"` N개(branch 점) + `기본(default)`(skip 점).
- **Loop**: `루프(각 항목)`(loop 점) / `완료(done)`(success 점).
- **Batch**: `배치(N개씩)`(loop 점) / `완료(done)`. 속성: 배치 크기·최대 반복·병렬 토글.
- **Merge**: 입력 2개(skip 점, 좌측) → 출력 1개(merge 점).
- **Filter**: `통과(조건 충족)`(success) / `제외(discard)`(skip).

**IF 조건 빌더 (속성 패널)**: 행 = [필드 드롭다운] [연산자 칩(==, > …, logic-branch-bg)] [값 인풋]. 행 사이 `AND`/`OR` 칩 + `+ 조건 추가`(점선 버튼). 하단에 출력 라우팅 요약(참 → …, 거짓 → …).

**⚠️ 실행 모델 영향**: 분기·반복·병합이 들어가면 워크플로우는 단순 순차가 아니라 **그래프(DAG + 루프)**. 엔진은 토폴로지 순서로 평가하고, 선택되지 않은 분기는 **스킵** 처리(UI는 회색 점선 엣지 + 스킵 노드로 표시). MCP 도구 입력 스키마 정의 시 분기 입력 통합 정책 결정 필요.

---

## 캔버스 정렬 도구

캔버스 상단 중앙 **플로팅 바**. 자동 정렬은 항상 활성, 맞춤/분배는 **2개 이상 선택 시** 활성.

- **자동 정렬**: 전체 흐름을 좌→우 레이어드로 재배치. (라벨 버튼, brand-weak)
- **맞춤 정렬**(아이콘 버튼 32px): 위 / 아래 / 왼쪽 / 오른쪽 / 가로 가운데 / 세로 가운데. 아이콘 = 기준선(brand) + 박스(중립).
- **균등 분배**: 가로 균등 / 세로 균등.
- 아이콘 버튼 상태: default(`--surface`) / hover(`--surface-3`) / active(`--brand-weak`) / disabled(opacity 0.4).
- **선택 컨텍스트 바**(다크 `--text-1` 배경 알약): "노드 N개 선택됨" + 맞춤 액션 아이콘.

**구현 메모(Drawflow)**:
- 맞춤/분배는 라이브러리 없이 선택 노드의 `pos_x/pos_y`를 최소·평균·균등 간격으로 재작성.
- 자동 정렬은 `dagre` 또는 `elkjs`로 레이어드 좌표 계산 → Drawflow 노드에 적용 + `updateConnectionNodes()`로 엣지 갱신.
- 위치 변경 시 200ms 트랜지션(점프 방지). 자동 정렬 후 "실행 취소(⌘Z)" 안내 토스트 권장.

---

## Interactions & Behavior
- **드래그**: 좌측 오퍼레이션/로직 아이템 → 캔버스 드롭 시 노드 생성(Drawflow `addNode`). htmx로 노드 메타 로드 가능.
- **노드 선택**: 클릭 → 선택 스타일(brand 보더+ring), 우측 "속성" 탭에 해당 노드 폼 로드(htmx `hx-get`).
- **엣지 연결**: 출력 포트 → 입력 포트 드래그(Drawflow 기본). 연결 시 데이터 매핑 편집 가능.
- **저장**: 자동/수동. 상태 칩으로 "저장 중 / 방금 저장됨" 표시(htmx 응답 후 swap).
- **실행**: 툴바 실행 → 다이얼로그 → 제출 시 노드 순차/그래프 실행, 노드 상태색 실시간 갱신(SSE 또는 htmx polling), 완료 후 "실행 로그" 탭에 결과.
- **테마 토글**: `<html data-theme>` 전환, localStorage 영속.
- 트랜지션: 노드 위치 200ms, 패널/탭 전환 빠른 페이드. 상태 변화는 색 + 아이콘 + 코드(색만으로 구분 금지).

## State Management
- 현재 워크플로우(노드/엣지/메타: 도구 이름, MCP 그룹, 노출 ON/OFF), 선택 노드 id, 우측 탭(속성|로그), 테마(light|dark), 저장 상태(idle|saving|saved|error).
- 실행: 실행 id 목록, 실행별 노드 상태/입출력, 진행 중 노드 id.
- 다이얼로그: 모드(form|json), 인증(type, token), 파라미터 값.
- 데이터: 스펙 업로드(파일/URL) → 오퍼레이션 목록; 실행 결과 fetch.

## Assets
- 폰트: Google Fonts — Plus Jakarta Sans, JetBrains Mono.
- 아이콘: 모두 **인라인 SVG**(Feather 스타일, stroke 기반)로 그려짐 — git-branch(IF), repeat(Loop), grid(Batch), merge-arrows(Merge), funnel(Filter), 정렬 아이콘(기준선+박스), 화살표/별(자동 정렬). 외부 아이콘 폰트 의존 없음. 코드베이스의 아이콘 세트로 대체 가능.
- 이미지 에셋 없음.

## Files
- **`BUILD_GUIDELINES.md`** — ⭐ Claude Code가 "시안대로 정확히" 만들기 위한 **합격 기준 체크리스트 + DOM 구조 + 금지 사항**. 구현 시 이걸 1순위로 따르세요.
- **`tokens.css`** — 디자인 토큰(CSS 변수). 가장 먼저 로드.
- **`drawflow_node_styles.css`** — Drawflow 노드 카드 스타일(빨강 노드 버그 수정 포함). `tokens.css` 다음에 로드.
- **`디자인 시스템 (standalone).html`** — 전체 디자인 시스템 + 모든 화면 목업(섹션 1~6)을 담은 **자체완결형 HTML**. 외부 의존성·빌드·런타임 없이 아무 브라우저에서 바로 열려 디자인을 그대로 볼 수 있습니다. **메인 시각 레퍼런스.**
- `README.md` — 이 문서(단독으로 구현 가능한 명세).

### 이 디자인을 구현하는 방법 (Claude Code 용 안내)
1. `디자인 시스템 (standalone).html`을 브라우저로 열어 의도한 룩앤필을 확인합니다. (이 파일은 **읽어서 그대로 복붙하는 코드가 아닙니다** — 인라인 스타일로 작성된 시각 레퍼런스입니다.)
2. 구현의 단일 소스는 **이 README의 "Design Tokens" + "Components" + "Screens" 섹션**입니다. 토큰 CSS 변수는 그대로 `tokens.css`로 채택하세요.
3. 실제 환경(**Jinja2 템플릿 + htmx + Drawflow**, 빌드 도구 없음)에서 디자인을 **재현**합니다 — HTML을 그대로 이식하는 것이 아닙니다.
4. 노드 스타일은 Drawflow 노드 **내부** 마크업에만 적용하고, 엣지는 SVG + `updateConnectionNodes()`로 다룹니다.

> ⚠️ 이전 버전 번들에 들어 있던 `.dc.html` / `support.js`는 전용 프리뷰 런타임 포맷이라 일반 환경에서 바로 렌더되지 않아 제외했습니다. 위 standalone HTML을 사용하세요.
