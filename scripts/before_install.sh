#!/bin/bash
set -euo pipefail

# CodeDeploy BeforeInstall — 런타임 준비.
# 우선순위: 정확성 → 재현성 → 보안 → 운영 안정성.

DEPLOY_DIR="/data/web-mcp-provider"

echo "=== BeforeInstall 시작 ==="

# 1) Python 3.11 설치(Amazon Linux 2023 / dnf 기준)
echo "Python 3.11 확인..."
if ! command -v python3.11 &> /dev/null; then
    echo "Python 3.11 미존재 → dnf 설치"
    sudo dnf install -y python3.11 python3.11-pip
    echo "Python 3.11 설치 완료"
else
    echo "Python 3.11 이미 설치됨"
fi

# 2) 배포 디렉터리 준비
mkdir -p "$DEPLOY_DIR"
chown -R ec2-user:ec2-user "$DEPLOY_DIR"

echo "=== BeforeInstall 완료 ==="
