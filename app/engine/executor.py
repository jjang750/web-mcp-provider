"""그래프 검증 / 토폴로지 정렬 / 순차 실행 / 노드별 로그 (사양서 §4).

- 그래프 검증: 사이클 거부.
- 노드 실패 시 raise 안 함 → 해당 노드 failed, 이후(하류) 노드 skipped.
- start 출력 = initial_input ($). 엣지 data_mapping($.x → params.path.x)로 상류 출력 주입.
- base_url 우선순위: node.base_url → operation.base_url → DEFAULT_BASE_URL.
- JSONPath 부분집합: $, 점 접근($.a.b), 인덱스($.a[0].b).
- condition 노드(IF): 조건 평가 → true/false 분기, 미선택 분기의 배타적 하류 스킵.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from engine import http_client

OperationResolver = Callable[[int], Optional[dict]]
NodeEventCb = Callable[[dict], None]

_TOKEN_RE = re.compile(r"([A-Za-z_][\w-]*)|\[(\d+)\]")

# 부작용 없는(조회) HTTP 메서드
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_read_only(node: dict, op: Optional[dict]) -> bool:
    """노드가 부작용 없는(조회) 노드인지 판정.

    - 노드에 read_only 가 명시되면 그 값을 우선.
    - 미지정이면 HTTP 메서드로 추론: GET/HEAD/OPTIONS = 조회(True), 그 외 = 변경(False).
    - api_call 이 아닌 제어흐름/변환 노드는 부작용이 없으므로 True.
    """
    explicit = node.get("read_only")
    if explicit is not None:
        return bool(explicit)
    if node.get("type", "api_call") != "api_call":
        return True
    method = (op.get("method") if op else "") or ""
    return method.upper() in SAFE_METHODS


# ---------- JSONPath 부분집합 ----------
def get_by_path(data: Any, path: str) -> Any:
    """'$', '$.a.b', '$.a[0].b' 지원. 미존재 시 None."""
    if path in ("$", "", None):
        return data
    p = path[2:] if path.startswith("$.") else (path[1:] if path.startswith("$") else path)
    cur = data
    for name, idx in _TOKEN_RE.findall(p):
        if name:
            if isinstance(cur, dict) and name in cur:
                cur = cur[name]
            else:
                return None
        elif idx != "":
            i = int(idx)
            if isinstance(cur, list) and 0 <= i < len(cur):
                cur = cur[i]
            else:
                return None
    return cur


def set_by_path(params: dict, dest: str, value: Any) -> None:
    """'params.path.x' / 'path.x' / 'query.y' / 'body.z' 형태에 값 주입."""
    dest = dest.strip()
    if dest.startswith("$."):
        dest = dest[2:]
    parts = [seg for seg in dest.split(".") if seg]
    if parts and parts[0] == "params":
        parts = parts[1:]
    if not parts:
        return
    cur = params
    for seg in parts[:-1]:
        nxt = cur.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[seg] = nxt
        cur = nxt
    cur[parts[-1]] = value


# ---------- 그래프 헬퍼 ----------
def _node_map(graph: dict) -> dict[str, dict]:
    return {n["id"]: n for n in graph.get("nodes", [])}


def _adjacency(graph: dict) -> tuple[dict[str, list[str]], dict[str, int]]:
    adj: dict[str, list[str]] = {n["id"]: [] for n in graph.get("nodes", [])}
    indeg: dict[str, int] = {n["id"]: 0 for n in graph.get("nodes", [])}
    for e in graph.get("edges", []):
        s, t = e["source"], e["target"]
        if s in adj and t in indeg:
            adj[s].append(t)
            indeg[t] += 1
    return adj, indeg


def topological_order(graph: dict) -> list[str]:
    """Kahn 알고리즘. 사이클이면 ValueError."""
    adj, indeg = _adjacency(graph)
    queue = [n for n, d in indeg.items() if d == 0]
    order: list[str] = []
    indeg = dict(indeg)
    while queue:
        queue.sort()  # 결정적 순서
        n = queue.pop(0)
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if len(order) != len(indeg):
        raise ValueError("워크플로우 그래프에 사이클이 있어 실행할 수 없습니다.")
    return order


def validate_graph(graph: dict) -> None:
    nodes = _node_map(graph)
    for e in graph.get("edges", []):
        if e["source"] not in nodes:
            raise ValueError(f"엣지 source 노드를 찾을 수 없습니다: {e['source']}")
        if e["target"] not in nodes:
            raise ValueError(f"엣지 target 노드를 찾을 수 없습니다: {e['target']}")
    topological_order(graph)  # 사이클 검증


def _deep_find(obj: Any, key: str):
    """obj(dict/list) 에서 key 에 해당하는 스칼라 값을 찾음(상위 우선, 그다음 중첩). (값, 찾음여부)."""
    if isinstance(obj, dict):
        if key in obj and not isinstance(obj[key], (dict, list)):
            return obj[key], True
        for v in obj.values():
            r, ok = _deep_find(v, key)
            if ok:
                return r, True
    elif isinstance(obj, list):
        for v in obj:
            r, ok = _deep_find(v, key)
            if ok:
                return r, True
    return None, False


def _incoming_edges(graph: dict, node_id: str) -> list[dict]:
    return [e for e in graph.get("edges", []) if e["target"] == node_id]


def _outgoing_edges(graph: dict, node_id: str) -> list[dict]:
    return [e for e in graph.get("edges", []) if e["source"] == node_id]


def _descendants(graph: dict, start: str) -> set[str]:
    adj, _ = _adjacency(graph)
    seen: set[str] = set()
    stack = list(adj.get(start, []))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adj.get(n, []))
    return seen


def _descendants_incl(graph: dict, start: str) -> set[str]:
    """start 자신 포함 하류 노드 집합."""
    return {start} | _descendants(graph, start)


# ---------- 조건 평가 ----------
def _as_bool(v: Any):
    """bool 또는 'true'/'false'/'1'/'0'/'yes'/'no' → bool, 아니면 None."""
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def _coerce_eq(lhs: Any, rhs: Any) -> bool:
    if lhs == rhs:
        return True
    # bool ↔ "true"/"false" 문자열 비교 관용 (예: JSON true == 우변 "true")
    if isinstance(lhs, bool) or isinstance(rhs, bool):
        bl, br = _as_bool(lhs), _as_bool(rhs)
        if bl is not None and br is not None:
            return bl == br
    # 숫자/문자 혼합 비교 관용: 문자열 표현으로 한 번 더 비교
    try:
        return str(lhs) == str(rhs)
    except Exception:
        return False


def _typed_eq(lhs: Any, rhs_raw: Any, rtype: str) -> bool:
    """우변 타입(rtype)에 맞춰 == 비교. auto 는 기존 관용 비교(_coerce_eq)."""
    if rtype == "string":
        return str(lhs) == ("" if rhs_raw is None else str(rhs_raw))
    if rtype == "number":
        try:
            return float(lhs) == float(rhs_raw)
        except (TypeError, ValueError):
            return False
    if rtype == "boolean":
        bl, br = _as_bool(lhs), _as_bool(rhs_raw)
        return bl is not None and br is not None and bl == br
    if rtype == "null":
        return lhs is None
    return _coerce_eq(lhs, rhs_raw)


def _cond_expr(cond: dict) -> str:
    """조건을 사람이 읽는 식 문자열로."""
    op = (cond.get("op") or "truthy").strip()
    left = cond.get("left", "$")
    if op in ("truthy", "falsy", "exists"):
        return f"{left} ({op})"
    rtype = cond.get("rtype") or "auto"
    suffix = "" if rtype == "auto" else f" :{rtype}"
    return f"{left} {op} {cond.get('right')}{suffix}"


def eval_condition(subject: Any, cond: dict) -> bool:
    """cond = {left, op, right}. left 는 subject 기준 JSONPath($..). 미지정 op 는 truthy."""
    op = (cond.get("op") or "truthy").strip()
    left = cond.get("left", "$")
    lhs = get_by_path(subject, left) if isinstance(left, str) and left.startswith("$") else left
    if op == "exists":
        return lhs is not None
    if op == "truthy":
        return bool(lhs)
    if op == "falsy":
        return not bool(lhs)
    rhs = cond.get("right")
    rtype = cond.get("rtype") or "auto"
    if op in ("==", "eq"):
        return _typed_eq(lhs, rhs, rtype)
    if op in ("!=", "ne"):
        return not _typed_eq(lhs, rhs, rtype)
    if op in (">", "<", ">=", "<="):
        if rtype == "string":
            l, r = str(lhs), ("" if rhs is None else str(rhs))
        else:
            try:
                l, r = float(lhs), float(rhs)
            except (TypeError, ValueError):
                return False
        return {">": l > r, "<": l < r, ">=": l >= r, "<=": l <= r}[op]
    if op == "contains":
        try:
            return rhs in lhs
        except TypeError:
            return False
    raise ValueError(f"지원하지 않는 조건 연산자: {op}")


# ---------- 실행 ----------
def run_workflow(
    graph: dict,
    initial_input: Any = None,
    auth: Optional[dict] = None,
    on_node_event: Optional[NodeEventCb] = None,
    *,
    operation_resolver: OperationResolver,
    timeout: float = 30.0,
    default_base_url: str = http_client.DEFAULT_BASE_URL,
    dry_run: bool = False,
) -> dict:
    """그래프를 검증·토폴로지 정렬 후 순차 실행. ExecutionResult(dict) 반환.

    dry_run=True 이면 조회(read-only) 노드는 실제 호출해 미리보기 데이터를 만들고,
    변경성(write) api_call 노드는 실제 호출하지 않고 '실행 예정(planned)' 계획만 기록한다.
    planned_actions 에 실행될 변경 호출 목록을 모아 사용자 확인용으로 반환한다.
    """
    validate_graph(graph)
    order = topological_order(graph)
    nodes = _node_map(graph)

    outputs: dict[str, Any] = {}
    logs: list[dict] = []
    planned_actions: list[dict] = []
    skipped: set[str] = set()
    overall_failed = False
    started_at = _now()

    def emit(payload: dict) -> None:
        if on_node_event:
            try:
                on_node_event(payload)
            except Exception:
                pass

    for seq, node_id in enumerate(order):
        node = nodes[node_id]
        ntype = node.get("type", "api_call")

        if node_id in skipped:
            log = {"node_key": node_id, "seq": seq, "status": "skipped",
                   "input": None, "output": None, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        # 상류 출력으로 입력 구성
        node_input: Any = None
        if ntype == "start":
            node_input = initial_input
            outputs[node_id] = initial_input
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": initial_input, "output": initial_input, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        if ntype == "condition":
            incoming = _incoming_edges(graph, node_id)
            subject = outputs.get(incoming[0]["source"]) if incoming else initial_input
            cond = (node.get("params") or {}).get("condition") or {}
            try:
                branch_bool = eval_condition(subject, cond)
            except Exception as exc:
                overall_failed = True
                log = {"node_key": node_id, "seq": seq, "status": "failed",
                       "input": subject, "output": None,
                       "error": f"조건 평가 실패: {exc}", "timestamp": _now()}
                logs.append(log)
                emit(log)
                skipped |= _descendants(graph, node_id)
                continue
            branch_label = "true" if branch_bool else "false"
            _left = cond.get("left", "$")
            _lhs = get_by_path(subject, _left) if isinstance(_left, str) and _left.startswith("$") else _left
            outputs[node_id] = subject  # 통과(pass-through): 하류 매핑 유지

            # 미선택 분기의 '배타적' 하류만 스킵(선택 분기에서도 도달 가능하면 살림 → Merge 재합류)
            taken_set: set[str] = set()
            nottaken_targets: list[str] = []
            for e in _outgoing_edges(graph, node_id):
                lbl = (e.get("label") or "").strip().lower()
                if lbl in ("true", "false") and lbl != branch_label:
                    nottaken_targets.append(e["target"])
                else:  # 라벨 없음 또는 선택 분기 → 통과
                    taken_set |= _descendants_incl(graph, e["target"])
            for t in nottaken_targets:
                skipped |= (_descendants_incl(graph, t) - taken_set)

            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": subject,
                   "output": {"branch": branch_label, "expr": _cond_expr(cond), "value": _lhs, "result": branch_bool},
                   "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        if ntype == "switch":
            incoming = _incoming_edges(graph, node_id)
            subject = outputs.get(incoming[0]["source"]) if incoming else initial_input
            sw = (node.get("params") or {}).get("switch") or {}
            left = sw.get("left", "$")
            value = get_by_path(subject, left) if isinstance(left, str) and left.startswith("$") else left
            cases = [str(x) for x in (sw.get("cases") or [])]
            value_str = "" if value is None else str(value)
            taken_labels = {value_str} if value_str in cases else {"__default__"}
            outputs[node_id] = subject  # 통과
            taken_set: set[str] = set()
            nottaken_targets: list[str] = []
            for e in _outgoing_edges(graph, node_id):
                lbl = e.get("label")
                if not lbl or lbl in taken_labels:  # 라벨 없음 또는 채택 케이스 → 통과
                    taken_set |= _descendants_incl(graph, e["target"])
                else:
                    nottaken_targets.append(e["target"])
            for t in nottaken_targets:
                skipped |= (_descendants_incl(graph, t) - taken_set)
            matched = value_str if value_str in cases else "__default__"
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": subject,
                   "output": {"switch": value_str, "matched": matched, "expr": str(left)},
                   "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        if ntype == "filter":
            incoming = _incoming_edges(graph, node_id)
            subject = outputs.get(incoming[0]["source"]) if incoming else initial_input
            cond = (node.get("params") or {}).get("condition") or {}
            _fleft = cond.get("left", "$")
            _flhs = get_by_path(subject, _fleft) if isinstance(_fleft, str) and _fleft.startswith("$") else _fleft
            try:
                passed = eval_condition(subject, cond)
            except Exception as exc:
                overall_failed = True
                log = {"node_key": node_id, "seq": seq, "status": "failed",
                       "input": subject, "output": None,
                       "error": f"필터 조건 평가 실패: {exc}", "timestamp": _now()}
                logs.append(log)
                emit(log)
                skipped |= _descendants(graph, node_id)
                continue
            _fdetail = {"passed": passed, "filtered": not passed, "expr": _cond_expr(cond), "value": _flhs}
            if passed:
                outputs[node_id] = subject  # 통과
                log = {"node_key": node_id, "seq": seq, "status": "success",
                       "input": subject, "output": _fdetail, "error": None, "timestamp": _now()}
            else:
                outputs[node_id] = None
                skipped |= _descendants(graph, node_id)  # 걸러짐 → 하류 스킵
                log = {"node_key": node_id, "seq": seq, "status": "success",
                       "input": subject, "output": _fdetail, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        if ntype == "merge":
            incoming = _incoming_edges(graph, node_id)
            merged = {}
            for e in incoming:
                src = e["source"]
                if src in outputs:
                    merged[src] = outputs[src]
            outputs[node_id] = merged
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": {"sources": [e["source"] for e in incoming]},
                   "output": merged, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        # api_call / transform / end: 정적 params + 엣지 매핑 주입
        params = copy.deepcopy(node.get("params") or {})
        for ed in _incoming_edges(graph, node_id):
            src_out = outputs.get(ed["source"])
            for m in ed.get("data_mapping", []) or []:
                frm = m.get("from") or m.get("from_")
                to = m.get("to")
                if frm and to:
                    set_by_path(params, to, get_by_path(src_out, frm))
        node_input = params

        if ntype == "end":
            # 같은 상류 노드는 한 번만 수집(예: IF true/false 포트를 둘 다 종료에 연결한 경우 중복 방지)
            srcs, seen = [], set()
            for e in _incoming_edges(graph, node_id):
                s = e["source"]
                if s in outputs and s not in seen:
                    seen.add(s)
                    srcs.append(outputs[s])
            if len(srcs) == 1:
                outputs[node_id] = srcs[0]          # 단일 상류 → 그대로 통과(노드ID 래핑 없음)
            elif len(srcs) > 1:
                outputs[node_id] = srcs             # 서로 다른 다중 상류 → 리스트
            else:
                outputs[node_id] = initial_input
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": node_input, "output": outputs[node_id], "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        if ntype == "transform":
            setmap = (node.get("params") or {}).get("setmap")
            if setmap:
                # 상류 응답(subject)에서 필드를 골라 출력 객체 구성
                incoming = _incoming_edges(graph, node_id)
                subject = outputs.get(incoming[0]["source"]) if incoming else initial_input
                built: dict = {}
                for f in setmap:
                    key = f.get("key")
                    if not key:
                        continue
                    if f.get("mode") == "literal":
                        built[key] = f.get("value")
                    else:  # path
                        src = f.get("src", "$")
                        built[key] = get_by_path(subject, src) if (isinstance(src, str) and src.startswith("$")) else src
                outputs[node_id] = built
                log = {"node_key": node_id, "seq": seq, "status": "success",
                       "input": subject, "output": built, "error": None, "timestamp": _now()}
            else:
                outputs[node_id] = params
                log = {"node_key": node_id, "seq": seq, "status": "success",
                       "input": node_input, "output": params, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        # api_call
        op = None
        op_id = node.get("operation_id")
        if op_id is not None:
            op = operation_resolver(op_id)
        if not op:
            overall_failed = True
            err = f"오퍼레이션을 찾을 수 없습니다 (operation_id={op_id})."
            log = {"node_key": node_id, "seq": seq, "status": "failed",
                   "input": node_input, "output": None, "error": err, "timestamp": _now()}
            logs.append(log)
            emit(log)
            skipped |= _descendants(graph, node_id)
            continue

        # 미입력 파라미터는 상류 노드 출력에서 같은 이름으로 자동 주입(명시 매핑/정적값이 우선)
        _inc = _incoming_edges(graph, node_id)
        _up = outputs.get(_inc[0]["source"]) if _inc else None
        if _up is not None:
            for _sec in ("path", "query", "header"):
                _secobj = params.get(_sec)
                if isinstance(_secobj, dict):
                    for _k in list(_secobj.keys()):
                        if _secobj[_k] in (None, ""):
                            _v, _ok = _deep_find(_up, _k)
                            if _ok:
                                _secobj[_k] = _v

        # base_url 우선순위: node → connection(API) → operation → DEFAULT
        base_url = (
            node.get("base_url")
            or op.get("conn_base_url")
            or op.get("base_url")
            or default_base_url
        )
        # 인증 우선순위: 연결(API)에 설정된 인증 → 실행 시 입력 인증(폴백)
        node_auth = op.get("auth") or auth

        # dry-run: 변경성(write) 노드는 실제 호출하지 않고 실행 계획만 기록
        if dry_run and not is_read_only(node, op):
            plan = http_client.preview(
                op["method"], base_url, op["path"],
                path_params=params.get("path"),
                query=params.get("query"),
                header=params.get("header"),
                body=params.get("body"),
                auth=node_auth,
            )
            outputs[node_id] = None  # 미실행 → 하류는 미리보기 한정
            planned_actions.append({"node_key": node_id, **plan})
            log = {"node_key": node_id, "seq": seq, "status": "planned",
                   "input": node_input, "output": plan, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        try:
            result = http_client.call(
                op["method"],
                base_url,
                op["path"],
                path_params=params.get("path"),
                query=params.get("query"),
                header=params.get("header"),
                body=params.get("body"),
                auth=node_auth,
                timeout=timeout,
            )
            status_code = result.get("status_code", 0)
            if status_code >= 400:
                overall_failed = True
                err = f"HTTP {status_code}"
                log = {"node_key": node_id, "seq": seq, "status": "failed",
                       "input": node_input, "output": result, "error": err, "timestamp": _now()}
                logs.append(log)
                emit(log)
                skipped |= _descendants(graph, node_id)
                continue
            outputs[node_id] = result.get("body")
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": node_input, "output": result.get("body"),
                   "error": None, "timestamp": _now(), "status_code": status_code}
            logs.append(log)
            emit(log)
        except Exception as exc:  # 네트워크/프로토콜 오류 등 — raise 하지 않음
            overall_failed = True
            log = {"node_key": node_id, "seq": seq, "status": "failed",
                   "input": node_input, "output": None, "error": str(exc), "timestamp": _now()}
            logs.append(log)
            emit(log)
            skipped |= _descendants(graph, node_id)

    # 최종 결과(final): end 노드 출력 우선, 없으면 마지막 성공 노드 출력(노드ID 래핑 없는 깔끔한 값)
    final = None
    end_ids = [nid for nid in order if nodes[nid].get("type") == "end" and nid in outputs]
    if end_ids:
        final = outputs[end_ids[-1]]
    else:
        for lg in reversed(logs):
            if lg["status"] == "success" and lg["node_key"] in outputs:
                final = outputs[lg["node_key"]]
                break

    return {
        "execution_id": None,
        "workflow_id": graph.get("workflow_id"),
        "status": "failed" if overall_failed else "success",
        "dry_run": dry_run,
        "started_at": started_at,
        "finished_at": _now(),
        "result": outputs,
        "final": final,
        "planned_actions": planned_actions,
        "logs": logs,
    }
