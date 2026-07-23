#!/bin/bash
# CodeDeploy ApplicationStop — PID 파일 기반 종료(이전 리비전 기준 실행, 최초 배포 시 skip).
# 실행 중이 아니어도 실패하지 않도록 방어적으로 처리.
set +e

DEPLOY_DIR="/data/web-mcp-provider"
PID_DIR="$DEPLOY_DIR/run"

for name in ui mcp; do
    pidfile="$PID_DIR/$name.pid"
    [ -f "$pidfile" ] || continue
    pid="$(cat "$pidfile" 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "중지: $name (PID $pid)"
        kill "$pid" 2>/dev/null
        for _ in $(seq 1 5); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
        kill -9 "$pid" 2>/dev/null
    fi
    rm -f "$pidfile"
done

# 안전망 — PID 파일이 유실된 경우 패턴으로 정리
pkill -f "backend.mcp_http_server" 2>/dev/null
pkill -f "uvicorn backend.app:app" 2>/dev/null

echo "ApplicationStop 완료"
exit 0
