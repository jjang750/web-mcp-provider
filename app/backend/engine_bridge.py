"""engine 패키지 호출 래퍼 (지연 import).

backend 레이어가 engine 의 순수 함수를 호출할 때의 단일 진입점.
operation_resolver 는 operations 리포지토리를 주입한다(3단계에서 연결).
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def parse_openapi(raw: str, source_hint: Optional[str] = None):
    from engine.parser import parse_openapi as _parse
    return _parse(raw, source_hint)


def run_workflow(
    graph: dict,
    initial_input: Any = None,
    auth: Optional[dict] = None,
    on_node_event=None,
    *,
    operation_resolver: Callable[[int], Optional[dict]],
    timeout: float = 30.0,
    dry_run: bool = False,
):
    from engine.executor import run_workflow as _run
    return _run(
        graph,
        initial_input=initial_input,
        auth=auth,
        on_node_event=on_node_event,
        operation_resolver=operation_resolver,
        timeout=timeout,
        dry_run=dry_run,
    )
