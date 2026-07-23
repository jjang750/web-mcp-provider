#!/bin/bash
set -euo pipefail

# CodeDeploy AfterInstall — venv 구성 + 의존성 설치 + .env 적용 + 런타임 디렉터리 준비.

echo "=== CodeDeploy Info ==="
echo "App: ${APPLICATION_NAME:-} / Group: ${DEPLOYMENT_GROUP_NAME:-} / ID: ${DEPLOYMENT_ID:-} / Lifecycle: ${LIFECYCLE_EVENT:-}"

DEPLOY_DIR="/data/web-mcp-provider"
APP_DIR="$DEPLOY_DIR/app"          # 실제 앱 코드(backend/, requirements.txt)
VENV_DIR="$DEPLOY_DIR/venv"        # 배포 간 유지(리비전에 포함되지 않음)
DATA_DIR="$DEPLOY_DIR/data"        # SQLite 등 런타임 산출물(배포 간 유지)

# 1) 배포 그룹별 .env 적용
#    - <deploy_dir>/.env.dev|.env.prod 가 있으면 app/.env 로 복사.
#    - 없으면 기존 app/.env 유지(서버에 사전 배치한 비밀은 보존).
echo "=== .env 적용 ($DEPLOYMENT_GROUP_NAME) ==="
if [[ "${DEPLOYMENT_GROUP_NAME:-}" == *dev* ]] && [ -f "$DEPLOY_DIR/.env.dev" ]; then
    cp "$DEPLOY_DIR/.env.dev" "$APP_DIR/.env"
    echo "dev .env 적용"
elif [[ "${DEPLOYMENT_GROUP_NAME:-}" == *prod* ]] && [ -f "$DEPLOY_DIR/.env.prod" ]; then
    cp "$DEPLOY_DIR/.env.prod" "$APP_DIR/.env"
    echo "prod .env 적용"
elif [ -f "$APP_DIR/.env" ]; then
    echo "환경별 파일 없음 → 기존 app/.env 유지"
else
    echo "경고: app/.env 가 없습니다. 서버에 .env 를 배치해야 인증/DB 설정이 적용됩니다."
fi

# 2) 런타임 디렉터리(배포 간 유지)
mkdir -p "$DATA_DIR" "$DEPLOY_DIR/logs" "$DEPLOY_DIR/run"
export TMPDIR="$DEPLOY_DIR/tmp"
mkdir -p "$TMPDIR"

# 3) 가상환경 + 의존성
if [ ! -d "$VENV_DIR" ]; then
    echo "venv 생성(python3.11)"
    python3.11 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"
python -m pip show uvicorn >/dev/null 2>&1 || python -m pip install "uvicorn[standard]"
deactivate

# 4) 정리 및 소유권 — 실제 기동은 ApplicationStart(start.sh)가 담당
rm -rf "$TMPDIR"
chown -R ec2-user:ec2-user "$DEPLOY_DIR"

echo "=== AfterInstall 완료 (whoami=$(whoami)) ==="
