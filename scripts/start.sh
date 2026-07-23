#!/bin/bash
set -euo pipefail

# CodeDeploy ApplicationStart — venv 파이썬 프로세스를 백그라운드로 기동.
# systemd 미사용. setsid 로 CodeDeploy agent 프로세스 그룹에서 분리해 훅 종료 후에도 유지.

DEPLOY_DIR="/data/web-mcp-provider"
APP_DIR="$DEPLOY_DIR/app"
VENV="$DEPLOY_DIR/venv"
LOG_DIR="$DEPLOY_DIR/logs"
PID_DIR="$DEPLOY_DIR/run"
DATA_DIR="$DEPLOY_DIR/data"

mkdir -p "$LOG_DIR" "$PID_DIR" "$DATA_DIR"
cd "$APP_DIR"

# .env 로드 — MCP 서버는 dotenv 미사용이라 셸에서 환경변수를 주입한다.
set -a
# shellcheck disable=SC1091
[ -f "$APP_DIR/.env" ] && . "$APP_DIR/.env"
set +a

# 기본값(미설정 시)
export MCP_DB_PATH="${MCP_DB_PATH:-$DATA_DIR/mcp_provider.db}"
export MCP_HTTP_HOST="${MCP_HTTP_HOST:-0.0.0.0}"
export MCP_HTTP_PORT="${MCP_HTTP_PORT:-9900}"
export MCP_HTTP_PATH="${MCP_HTTP_PATH:-/mcp}"
UI_PORT="${UI_PORT:-9090}"

start_svc() {
    local name="$1"; shift
    local pidfile="$PID_DIR/$name.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile" 2>/dev/null)" 2>/dev/null; then
        echo "$name 이미 실행 중 (PID $(cat "$pidfile"))"
        return
    fi
    setsid "$@" >"$LOG_DIR/$name.log" 2>&1 < /dev/null &
    echo $! > "$pidfile"
    echo "$name 시작 (PID $!) → $LOG_DIR/$name.log"
}

start_svc mcp "$VENV/bin/python" -m backend.mcp_http_server
start_svc ui  "$VENV/bin/uvicorn" backend.app:app --host 0.0.0.0 --port "$UI_PORT" --proxy-headers --forwarded-allow-ips=*

# 헬스체크 — 실패 시 배포 실패 처리
sleep 4
rc=0
curl -sf "http://localhost:${UI_PORT}/healthz"       >/dev/null && echo "UI(${UI_PORT}) OK"       || { echo "UI 기동 실패";  tail -n 30 "$LOG_DIR/ui.log";  rc=1; }
curl -sf "http://localhost:${MCP_HTTP_PORT}/healthz" >/dev/null && echo "MCP(${MCP_HTTP_PORT}) OK" || { echo "MCP 기동 실패"; tail -n 30 "$LOG_DIR/mcp.log"; rc=1; }

echo "ApplicationStart 완료 (rc=$rc)"
exit $rc
