# 빌드 가이드라인 — Claude Code가 "시안대로 정확히" 구현하기 위한 규칙

이 문서는 `디자인 시스템 (standalone).html` 시안을 **픽셀 단위로 정확히** 재현하기 위한 강제 규칙입니다.
구현 환경: **Jinja2 + htmx + Drawflow**, 빌드 도구 없음(CDN/정적). Tailwind 불가 → `tokens.css`(순수 CSS 변수) 사용.

> 작업 순서: ① `tokens.css` 적용 → ② `drawflow_node_styles.css` 적용 → ③ 아래 화면별 합격 기준을 하나씩 통과시키기. 각 항목은 **체크 가능한 단언문**으로 썼습니다. 전부 ✅ 되어야 "시안대로"입니다.

---

## 0. 절대 규칙 (DO / DON'T)

**DO**
- 색·간격·폰트·라운드는 **반드시 `var(--*)` 토큰**으로만. 하드코딩 hex 금지.
- 상태(성공/실패/스킵/실행중)는 **색 + 아이콘 + 텍스트(상태코드)** 3가지로 동시 표현.
- 노드 상태색은 **상단 4px 스트라이프 + 1px 테두리**에만 적용.
- 폰트: UI = `Plus Jakarta Sans`, 경로/코드/숫자 = `JetBrains Mono`. 둘 다 Google Fonts에서 로드.

**DON'T (실제로 나왔던 버그)**
- ❌ **노드 카드 배경 전체를 상태색으로 칠하지 마라.** 빨강 채움 노드는 버그다. 빨강 = 실패(error) **전용**, 그것도 스트라이프/테두리에만.
- ❌ **노드 제목에 경로를 반복하지 마라.** 배지 옆 = 경로(`/impo/detail`), 제목 = **사람이 읽는 요약**(`단지 부과 상세 정보 조회`). 둘이 같으면 안 된다.
- ❌ 정렬 아이콘을 흐리게 두지 마라. 기준선 = `var(--brand)`, 박스 = `var(--text-3)`.
- ❌ Drawflow 기본 노드 크롬(파란 selected 박스, 회색 배경)을 남기지 마라. `.drawflow-node{background:transparent;border:none;box-shadow:none}`로 제거하고 내부 `.wf-node`를 직접 스타일.
- ❌ `var(--없는토큰)` 쓰지 마라. 미정의 변수는 조용히 깨진다 — `tokens.css`에 있는 이름만.

---

## 1. 디자인 토큰 (정본)
`tokens.css` 파일을 그대로 사용. 핵심만 재확인:

| 용도 | 라이트 | 다크 |
|---|---|---|
| 캔버스 | `--canvas:#F4F6F9` (도트 `--canvas-dots:#D5DAE2`) | `#0C0F16` (도트 `#1E2533`) |
| 카드 | `--surface:#FFFFFF` | `#151A23` |
| 테두리 | `--border:#E6EAEF` / `--border-strong:#D5DAE2` | `#262E3B` / `#313B4A` |
| 본문/보조/3차 | `#1A2231 / #5C6675 / #8A94A6` | `#EAEDF3 / #8A94A6 / #5B6577` |
| 브랜드 | `--brand:#0E9E74` (버튼채움은 `#0A7D5A`) | `#2DD4A7` |
| 성공/실패/스킵 | `#16A34A / #E5484D / #98A2B3` | `#34D399 / #FB6F84 / #5B6577` |
| 메서드 GET/POST/PUT/PATCH/DELETE | `#1D6FE0 / #0E8A5F / #B7791F / #6D45D6 / #D03939` (+`-bg`) | (다크 오버라이드) |
| 로직 분기/반복/병합 | `#7C5CFF / #E8883B / #3B82F6` | 동일 |

- 캔버스 도트 그리드: `background:var(--canvas); background-image:radial-gradient(var(--canvas-dots) 1.2px, transparent 1.2px); background-size:20px 20px;`
- 라운드: sm 6 / md 8 / lg 12 / xl 16 / pill 999. 그림자: `--sh-1/2/3`.

---

## 2. 합격 기준 — 에디터 (3분할)

**레이아웃**
- [ ] 세로 구조: 툴바1(52px) → 툴바2(46px) → 본문(`flex:1`).
- [ ] 본문 가로: 좌 패널 `236px` + 캔버스 `flex:1` + 우 패널 `296px`. 좌/우 패널은 캔버스와 1px 보더로 구분.
- [ ] 좌 패널 배경 `--surface-2`, 우 패널 `--surface`, 캔버스 도트 그리드.

**툴바 1행 (`--surface`)**
- [ ] 좌: 뒤로(‹, 30px 아이콘버튼) · 제목(15px/700) · 편집 글리프(✎).
- [ ] 우: 저장상태 칩(성공톤, 좌 6px 점) · **테마 토글**(🌗 라이트/🌙 다크) · `저장`(secondary) · `실행`(primary+▶).

**툴바 2행 (`#FAFBFC`)**
- [ ] `+start`(브랜드 점선) · `+end`(중립 점선) · 구분선 · `도구 이름`(mono input) · `MCP 그룹`(mono input) · (우) `MCP 노출` + 토글(ON=brand).

**좌 패널 — 오퍼레이션**
- [ ] 헤더 "오퍼레이션"(12.5/700) + 검색 input(⌕).
- [ ] 아이템: 그립(⠿) + [메서드 배지 + 경로(mono, ellipsis)] + 요약(11.5px). `cursor:grab`. hover 시 `box-shadow:0 0 0 2px rgba(14,158,116,.12)`.
- [ ] 탭 토글: **오퍼레이션 / 로직**(빌트인 제어 노드).

**캔버스**
- [ ] 좌하단 줌 컨트롤(+/− 세로 스택, surface+보더+sh-2). 우상단 줌 배율 칩.
- [ ] 노드 = 아래 §4 구조. 엣지 = SVG 베지어 + 화살표 마커, 노드 포트 좌표와 동일 좌표계.

**우 패널 — 탭(속성/실행로그)**
- [ ] 활성 탭 = `--text-1`/700 + 하단 2px `--brand`. 비활성 = `--text-3`/600.
- [ ] 속성: 메서드+경로 헤더 → `Base URL` input → `Body`(JSON, 다크 코드블록 `#0C0F16`, 문자열 `#34D399`/변수 `#FBBF24`) → 엣지 매핑(`노드1 · id → userId`).

---

## 3. 합격 기준 — 실행 다이얼로그 / 실행 로그

**다이얼로그**
- [ ] 백드롭 딤 + 모달 `width:480px`, `--surface`, `--r-xl`, `--sh-3`.
- [ ] 헤더(brand-weak 아이콘 타일 + 제목 16/700 + 닫기 ✕) · 모드 세그먼트(`폼 모드`/`JSON 직접 편집`).
- [ ] 인증 세그먼트(`Bearer Token`/`API Key`, 선택=brand-weak) + 토큰 input(mono, masked).
- [ ] 파라미터: 노드별 그룹 [배지+노드명] + 행(`라벨(필수 *) + input`). 자동매핑 값은 점선박스 + "이전 노드에서 자동 매핑" + 매핑 칩.
- [ ] 푸터: `취소`(ghost) / `실행하기`(primary+▶).

**실행 로그**
- [ ] 실행 헤더: `실행 #N` 드롭다운 + 타임스탬프 + 전체 상태 칩.
- [ ] 노드 카드(좌측 3px 상태 스트라이프): 상태 원형(✓/!/–) + 배지 + 노드명 + 상태코드 + 소요시간 + 펼치기(▾/▴).
- [ ] 펼침: input/output 토글 + JSON 코드블록. 실패=에러 메시지(danger). 스킵=점선+opacity .7.

---

## 4. 합격 기준 — 노드 카드 (가장 중요, 버그 발생 지점)

`drawflow_node_styles.css` + 아래 마크업을 그대로 사용.

**api_call 노드 정확한 DOM:**
```html
<div class="wf-node" data-status="">   <!-- "" | running | success | error | skipped -->
  <div class="wf-node__stripe"></div>
  <div class="wf-node__body">
    <div class="wf-node__head">
      <span class="wf-badge wf-badge--get">GET</span>      <!-- 메서드별 클래스 -->
      <span class="wf-path">/impo/detail</span>             <!-- 경로(mono, ellipsis) -->
      <!-- 실행 후에만 표식: -->
      <!-- <span class="wf-node__status wf-node__status--success">✓ 200</span> -->
    </div>
    <div class="wf-node__title">단지 부과 상세 정보 조회</div>  <!-- 요약! 경로 반복 금지 -->
  </div>
</div>
```

**상태별 시각 (단언):**
- [ ] **기본**: 흰 카드(`--surface`), 1px `--border`, 스트라이프 `--border`(중립 회색). 빨강 아님.
- [ ] **선택**: `.drawflow-node.selected .wf-node` → 1.5px `--brand` 테두리 + `0 0 0 3px var(--focus)` 링 + 스트라이프 brand. (Drawflow 기본 파란 박스는 제거)
- [ ] **실행중**: 스트라이프 파란 그라데이션 + 우측 스피너.
- [ ] **성공**: 스트라이프 `--success` + 연한초록 테두리 + `✓ 200`(success).
- [ ] **실패**: 스트라이프 `--danger` + 연한빨강 테두리 + `! 401`(danger). ← **빨강은 여기서만.**
- [ ] **스킵**: 점선 테두리 + opacity .75 + "스킵".
- [ ] **start/end**: `.wf-node--terminal`, 아이콘 타일(start=brand ▶ / end=`--text-2` ■) + 라벨(13/700).

**제어 흐름 노드(IF/Switch/Loop/Batch/Merge/Filter):** 메서드 배지 대신 **색 아이콘 타일 + 타입 칩**. 다중 출력 포트 + 라벨(참/거짓, case, 루프/완료 등). 색: 분기=`--logic-branch`, 반복=`--logic-loop`, 병합=`--logic-merge`.

---

## 5. 합격 기준 — 컴포넌트 상태

- [ ] **Primary 버튼**: 채움 `#0A7D5A`(AA 통과), 흰 글씨 13/600, `--r-md`, `9px 16px`. hover=`--brand-hover`, active=`translateY(1px)`, disabled=`#A9D9C8`. (`--brand` 원색은 테두리/아이콘/큰 텍스트에만)
- [ ] **Input**: focus=1.5px `--brand`+`0 0 0 3px var(--focus)` 링. error=1.5px `--danger`+하단 메시지. disabled=`--canvas`+`not-allowed`.
- [ ] **Toggle**: 40×23, 노브 19px. ON=`--brand`.
- [ ] **메서드 배지**: mono 11/600, 색=`--m-*`, 배경=`--m-*-bg`.
- [ ] **엣지**: 기본 2px `--border-strong`; 활성/성공 2.5px `--success`/그라데이션; 스킵 점선(`6 4`); 매핑 라벨 mono 9.5 칩.
- [ ] **Toast**: surface+좌3px 상태보더, 상태 원형 아이콘 + 메시지(12.5/500).

---

## 6. 합격 기준 — 정렬 도구

- [ ] 캔버스 상단 중앙 **플로팅 바**: `자동 정렬`(brand-weak 라벨버튼) | 맞춤 6종(위/아래/좌/우/가로중앙/세로중앙) | 균등분배 2종.
- [ ] 아이콘 = 기준선(`--brand`) + 박스(`--text-3`). 흐리게 두지 말 것.
- [ ] 아이콘 버튼 상태: default(surface) / hover(surface-3) / active(brand-weak) / disabled(opacity .4).
- [ ] 2개 미만 선택 시 맞춤/분배 비활성. 선택 컨텍스트 바(다크 알약 "노드 N개 선택됨").
- [ ] 구현: 맞춤/분배 = `pos_x/pos_y` 재계산. 자동정렬 = `dagre`/`elkjs` → 적용 + `updateConnectionNodes()`. 위치변경 200ms 트랜지션.

---

## 7. 접근성 (반드시 통과)
- [ ] Primary 버튼 흰 글씨 대비 ≥ 4.5:1 → 채움 `#0A7D5A` 사용(`#0E9E74`는 3.0이라 미달).
- [ ] 상태를 색만으로 구분하지 않음(아이콘 ✓/!/– + 코드 200/401/스킵 병행).
- [ ] 모든 input/button/노드에 포커스 링(`var(--focus)` 3px).
- [ ] 선택 = 테두리+링(명도차)로도 인지 가능.
- [ ] 주요 버튼 타깃 ≥ 32px(보조 액션만 28px).

---

## 8. 최종 자가 점검 (제출 전)
1. 노드 카드 중 **배경 전체가 빨강/초록인 것이 하나도 없다**. (상태는 스트라이프+테두리만)
2. 노드 제목과 경로가 **서로 다르다**. (제목=요약, 배지옆=경로)
3. 라이트/다크 토글이 `<html data-theme>` 전환 + localStorage 영속으로 동작한다.
4. 모든 색이 `var(--*)`로 나오고, 콘솔에 깨진 `var()` 폴백이 없다.
5. `디자인 시스템 (standalone).html`을 옆에 띄우고 같은 화면을 1:1로 비교했을 때 색·간격·상태가 일치한다.
