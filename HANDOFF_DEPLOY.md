# HANDOFF — AWS CodePipeline/CodeDeploy 배포

## 요약
CodeDeploy(EC2, Amazon Linux 2023)로 이 저장소를 `/data/web-mcp-provider` 에 배포하고,
UI(uvicorn, 9090)와 MCP HTTP(9900)를 **venv 파이썬 프로세스**로 백그라운드 기동한다(systemd 미사용).
프로세스는 `setsid` 로 CodeDeploy agent 프로세스 그룹에서 분리하고 PID 파일로 관리한다.

## 추가/변경 파일
- `appspec.yml` — 배포 대상 `/data/web-mcp-provider`, 훅 4단계, 권한(ec2-user, 755).
- `scripts/before_install.sh` — python3.11 설치, 배포 디렉터리 준비(root).
- `scripts/after_install.sh` — venv 생성 + `app/requirements.txt` 설치 + `.env` 적용 + 런타임 디렉터리(root).
- `scripts/start.sh` — venv 프로세스 백그라운드 기동(nohup/setsid) + PID 기록 + 헬스체크(ec2-user).
- `scripts/stop.sh` — PID 기반 종료 + 패턴 정리(ec2-user).
- `.gitignore` — `.env.dev/.env.prod/.env.bak` 추가(비밀 유출 방지).

## 배포 폴더 구조 (EC2)
```
/data/web-mcp-provider/          ← 저장소 전체(appspec destination)
├── app/                         ← 앱 코드(backend/, requirements.txt, .env)
├── scripts/                     ← 배포 훅
├── venv/                        ← after_install 이 생성(배포 간 유지)
├── data/mcp_provider.db         ← SQLite(배포 간 유지)
├── logs/{ui,mcp}.log            ← 프로세스 로그
└── run/{ui,mcp}.pid             ← PID 파일
```
`app/`, `data/`, `venv/`, `logs/`, `run/` 는 리비전에 포함되지 않으므로 재배포해도 DB/가상환경/로그는 보존된다.

## 훅 실행 순서
1. **BeforeInstall** `before_install.sh` (root) — python3.11, 디렉터리.
2. (파일 복사)
3. **AfterInstall** `after_install.sh` (root) — venv·의존성·.env·런타임 디렉터리.
4. **ApplicationStop** `stop.sh` (ec2-user) — 이전 리비전 기준 실행 → 최초 배포 시 자동 skip.
5. **ApplicationStart** `start.sh` (ec2-user) — MCP→UI 백그라운드 기동 + healthz 확인.

## 프로세스 운영 (EC2 콘솔)
```
# 상태/로그
cat /data/web-mcp-provider/run/ui.pid /data/web-mcp-provider/run/mcp.pid
tail -f /data/web-mcp-provider/logs/ui.log
tail -f /data/web-mcp-provider/logs/mcp.log
# 수동 재기동/중지
/data/web-mcp-provider/scripts/stop.sh
/data/web-mcp-provider/scripts/start.sh
```

## 사전 조건 (배포 전 필수)
- EC2: Amazon Linux 2023, **CodeDeploy agent** 설치·실행, 인스턴스 프로파일에 아티팩트 S3 읽기 권한.
- 배포 그룹명에 `dev` 또는 `prod` 포함 시 해당 `.env` 자동 선택.
- **비밀(.env) 배치** — 두 방법 중 하나:
  - (권장) 서버에 `/data/web-mcp-provider/app/.env` 를 미리 배치 → 재배포해도 보존, 저장소엔 없음.
  - 또는 `/data/web-mcp-provider/.env.dev` / `.env.prod` 를 서버에 배치 → after_install 이 `app/.env` 로 복사.
  - `.env*` 는 gitignore 대상이므로 저장소에 커밋되지 않는다(반드시 서버/SSM로 관리).
- 보안 그룹/리버스 프록시: UI 9090, MCP 9900 개방 또는 프록시 연결.
- `.env` 에 인증 필수값: `APP_AUTH_USER/APP_AUTH_PASSWORD/APP_JWT_SECRET`, MCP `MCP_AUTH_TOKEN/MCP_ALLOWED_HOSTS` 등.

## 테스트 (배포 후, 콘솔/URL)
```
# EC2 콘솔
sudo systemctl status web-mcp-ui web-mcp-mcp
sudo journalctl -u web-mcp-ui -n 50 --no-pager
curl -s http://localhost:9090/healthz
curl -s http://localhost:9900/healthz
```
- UI: `http://<host>:9090/` → 로그인 페이지 리다이렉트 확인.
- MCP: `http://<host>:9900/mcp` (Bearer 토큰 필요).

## 이슈/리스크
- **부팅 시 자동 시작 없음** — systemd 미사용이므로 EC2 재부팅 후 프로세스가 자동 기동되지 않는다. 재부팅 후에는 재배포하거나 `start.sh` 를 수동 실행(또는 cron `@reboot`) 필요.
- `setsid` 로 agent 프로세스 그룹에서 분리해 훅 종료 후에도 유지되도록 처리했다. (CodeDeploy 는 훅 종료 시 자식 프로세스를 정리할 수 있어 필수)
- `.env` 미배치 시 인증/DB 설정 누락 → after_install 이 경고만 하고 진행. 배포 전 반드시 배치.
- MCP 서버는 dotenv 미사용이라 `start.sh` 가 `.env` 를 셸에 로드해 주입한다(`MCP_AUTH_TOKEN`, `MCP_ALLOWED_HOSTS` 등 포함되어야 함).
- 포트 9090/9900 을 ec2-user 로 바인딩(1024 이상이라 문제없음).
- ApplicationStop 은 첫 배포에서 skip → 정상.
