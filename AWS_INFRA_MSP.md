# AWS 인프라 요청서 (MSP 전달용) — web-mcp-provider

> 목적: CodePipeline/CodeDeploy 기반 배포를 위해 MSP 측에서 구성해야 할 AWS 리소스(ALB·보안그룹·EC2·IAM·DNS 등)를 정리한 문서입니다.
> 리전: **ap-northeast-2 (서울)** / 애플리케이션: MCP Provider (관리 UI + MCP HTTP 서버)

---

## 1. 아키텍처 개요

```
                 (HTTPS 443)
 인터넷 / 사내망 ──────────────▶  ALB  ──(HTTP)──▶  EC2 (Amazon Linux 2023)
                                  │                 ├─ MCP HTTP 서버 : 9900  (/mcp, /healthz)
                                  │                 └─ 관리 UI(FastAPI): 9090 (/, /login, /healthz)
                                  │
        ┌──── 호스트 기반 라우팅 ────┐
        │ mcp.aegisep.com      → 9900 (MCP, 기계 클라이언트용, Bearer 토큰)
        │ mcp-admin.aegisep.com → 9090 (관리 UI, 사람용, 로그인)   ← 접근 제한 권장
        └──────────────────────────┘
```

- **TLS 종단은 ALB**(ACM 인증서). EC2 컨테이너/프로세스는 HTTP 로만 수신.
- ALB 는 `Host` 헤더와 `X-Forwarded-*` 를 보존해 전달해야 함(앱의 DNS rebinding 방어·프록시 헤더 처리에 필요). ALB 기본 동작으로 충족되나 확인 요망.
- 관리 UI(9090)는 민감(워크플로우·API 설정 편집)하므로 **인터넷 비공개 또는 사내망/IP 허용목록**을 권장.

---

## 2. 필요 리소스 요약

| 구분 | 리소스 | 비고 |
|---|---|---|
| 컴퓨팅 | EC2 1대 (t3.small 이상 권장) | Amazon Linux 2023, CodeDeploy agent |
| 로드밸런서 | ALB 1대 | HTTPS 리스너, 타깃그룹 2개(9090/9900) |
| 인증서 | ACM 인증서 | `*.aegisep.com` 또는 대상 호스트별 |
| DNS | Route53 A(Alias) 레코드 | ALB 로 연결 |
| 배포 | CodePipeline + CodeDeploy | 소스: CodeCommit `web-mcp-provider` |
| 스토리지 | S3 (파이프라인 아티팩트) | 파이프라인 생성 시 자동/지정 |
| 보안 | 보안그룹 2개 | alb-sg, ec2-sg |
| 권한 | IAM 역할 3종 | 인스턴스 프로파일, CodeDeploy, CodePipeline |

---

## 3. 네트워크 / 포트

| 방향 | 포트 | 프로토콜 | 용도 |
|---|---|---|---|
| 인터넷→ALB | 443 | HTTPS | 서비스 진입(권장) |
| 인터넷→ALB | 80 | HTTP | 443 리다이렉트 |
| ALB→EC2 | 9900 | HTTP | MCP HTTP 서버 |
| ALB→EC2 | 9090 | HTTP | 관리 UI |
| 관리자→EC2 | 22 | SSH | 운영/디버깅(허용 IP 한정) |
| EC2→인터넷 | 443 | HTTPS | dnf/pip, AWS API(아웃바운드) |

헬스체크 경로(양 서비스 공통): **`GET /healthz`** (200 응답).

---

## 4. ALB 구성

**리스너**
- `HTTP:80` → `HTTPS:443` 리다이렉트(301).
- `HTTPS:443` (ACM 인증서 연결) → 호스트 기반 규칙:
  - `Host = mcp.aegisep.com` → **TG-mcp** (EC2:9900)
  - `Host = mcp-admin.aegisep.com` → **TG-ui** (EC2:9090)
  - (선택) UI 규칙에 **Source IP 조건**을 추가해 사내/관리 IP만 허용.

**타깃 그룹**

| 이름 | 대상 포트 | 프로토콜 | 헬스체크 | 정상 임계 |
|---|---|---|---|---|
| TG-mcp | 9900 | HTTP | `/healthz` | 2/5, 30s |
| TG-ui  | 9090 | HTTP | `/healthz` | 2/5, 30s |

- 스티키니스: 불필요(무상태). MCP 스트리밍(SSE) 특성상 **idle timeout 120s 이상** 권장.
- ALB 속성: `Host` 헤더 보존(기본), `X-Forwarded-For/Proto` 전달(기본).

---

## 5. 보안 그룹

**alb-sg (ALB에 부착)**

| 방향 | 포트 | 소스/대상 | 비고 |
|---|---|---|---|
| Inbound | 443 | 0.0.0.0/0 | MCP 공개(필요 시 제한) |
| Inbound | 80 | 0.0.0.0/0 | 443 리다이렉트 |
| Outbound | 9090, 9900 | ec2-sg | EC2 로 전달 |

**ec2-sg (EC2에 부착)**

| 방향 | 포트 | 소스/대상 | 비고 |
|---|---|---|---|
| Inbound | 9900 | alb-sg | ALB 경유만 허용 |
| Inbound | 9090 | alb-sg | ALB 경유만 허용 |
| Inbound | 22 | 관리자 IP/CIDR 또는 Bastion SG | SSH |
| Outbound | 443 | 0.0.0.0/0 | 패키지/AWS API |

> 핵심: EC2 의 9090/9900 은 **ALB(alb-sg)에서 오는 트래픽만** 허용하고 인터넷에 직접 노출하지 않습니다.

---

## 6. EC2 요구사항

| 항목 | 값/요구 |
|---|---|
| OS | Amazon Linux 2023 |
| 인스턴스 타입 | t3.small 이상(빌드 시 pip 설치 여유) |
| 디스크 | gp3 20GB 이상(`/data` 여유) |
| 필수 SW | CodeDeploy agent(실행 중), Python 3.11(스크립트가 자동 설치 시도) |
| IAM | 인스턴스 프로파일(아래 7절) |
| 사용자 | `ec2-user` 로 앱 프로세스 구동 |
| 데이터 경로 | `/data/web-mcp-provider` (배포 루트) |

배포 후 프로세스는 systemd 없이 `setsid` 백그라운드로 구동됩니다(로그 `/data/web-mcp-provider/logs/`, PID `/data/web-mcp-provider/run/`).
※ **재부팅 시 자동 시작이 없으므로**, 부팅 자동기동이 필요하면 MSP 측에서 cron `@reboot` 또는 systemd 등록을 요청드립니다(선택).

---

## 7. IAM 역할

**(a) EC2 인스턴스 프로파일**
- `AmazonSSMManagedInstanceCore` (선택, SSM 접속용)
- CodeDeploy 아티팩트 S3 버킷 읽기 권한(`s3:Get*`, `s3:List*` — 해당 버킷 한정)

**(b) CodeDeploy 서비스 역할**
- `AWSCodeDeployRole` (관리형)

**(c) CodePipeline 서비스 역할**
- 소스(CodeCommit) 읽기, 아티팩트 S3 읽기/쓰기, CodeDeploy 배포 트리거 권한

---

## 8. CodePipeline / CodeDeploy 구성

| 항목 | 값 |
|---|---|
| 소스 | CodeCommit 저장소 `web-mcp-provider`, 브랜치 `main` |
| 빌드 | 불필요(배포 시 EC2에서 venv/pip 처리) — CodeBuild 미사용 |
| 배포 | CodeDeploy (EC2/온프레미스), In-place |
| 애플리케이션 스펙 | 저장소 루트 `appspec.yml` |
| 배포 그룹명 규칙 | 이름에 `dev` 또는 `prod` 포함 시 해당 `.env` 자동 선택 |
| 배포 대상 | ec2-sg EC2(태그 기반 매칭 권장, 예: `Name=web-mcp-provider`) |

배포 훅(순서): BeforeInstall → (파일 복사) → AfterInstall → ApplicationStop → ApplicationStart. 상세는 `HANDOFF_DEPLOY.md` 참조.

---

## 9. DNS / 인증서

| 레코드 | 타입 | 대상 | 용도 |
|---|---|---|---|
| `mcp.aegisep.com` | A(Alias) | ALB | MCP 엔드포인트 |
| `mcp-admin.aegisep.com` | A(Alias) | ALB | 관리 UI(제한 권장) |

- ACM 인증서(ap-northeast-2)에 위 호스트 포함(또는 와일드카드 `*.aegisep.com`).
- 인증서 검증은 Route53 DNS 검증 권장.

---

## 10. 시크릿 / .env 프로비저닝 (중요)

앱 설정·비밀은 저장소에 포함되지 않습니다(`.gitignore`). MSP 측에서 서버에 안전하게 배치해야 합니다.

- 배치 경로: **`/data/web-mcp-provider/app/.env`** (재배포해도 보존됨)
  - 또는 배포그룹별 `/data/web-mcp-provider/.env.dev` / `.env.prod` 배치 → AfterInstall 이 `app/.env` 로 복사.
- 필수 키:

| 키 | 설명 |
|---|---|
| `MCP_AUTH_TOKEN` | MCP 엔드포인트 Bearer 토큰(긴 랜덤) |
| `MCP_ALLOWED_HOSTS` | 허용 Host(예: `mcp.aegisep.com,mcp-admin.aegisep.com`) |
| `MCP_DEFAULT_BASE_URL` | 대상 API 기본 base_url |
| `APP_AUTH_USER` / `APP_AUTH_PASSWORD` | 관리 UI 로그인 계정 |
| `APP_JWT_SECRET` | UI JWT 서명 시크릿(긴 랜덤, `openssl rand -hex 32`) |
| `APP_COOKIE_SECURE` | **`true`** (ALB HTTPS 종단 환경) |

> 권장: 비밀은 AWS SSM Parameter Store/Secrets Manager 로 관리하고, 배치 시 `.env` 로 렌더링. 권한은 최소화.

---

## 11. 배포 후 검증 체크리스트

- [ ] `sudo systemctl status codedeploy-agent` (agent 실행)
- [ ] EC2 내부: `curl -s http://localhost:9090/healthz`, `curl -s http://localhost:9900/healthz` → 200
- [ ] ALB 타깃그룹 TG-ui / TG-mcp **healthy**
- [ ] `https://mcp-admin.aegisep.com/` → 로그인 페이지 리다이렉트
- [ ] `https://mcp.aegisep.com/mcp` → Bearer 토큰으로 접근(무토큰 401)
- [ ] `APP_COOKIE_SECURE=true` 상태에서 로그인 쿠키 정상(HTTPS)

---

## 12. 역할 분담 요약

| 항목 | 우리(개발) | MSP |
|---|---|---|
| 애플리케이션 코드·appspec·배포 스크립트 | ● | |
| CodeCommit 저장소 | ● | |
| ALB·타깃그룹·리스너 | | ● |
| 보안그룹·EC2·IAM 역할 | | ● |
| ACM·Route53 | | ● |
| CodePipeline·CodeDeploy(앱/배포그룹) | 협의 | ● |
| `.env` 시크릿 배치(SSM 연동) | 값 제공 | 배치 |
