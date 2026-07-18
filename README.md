# 냉장고 알리미 MVP (TDD)

이 저장소는 [PRD.md](PRD.md)를 기준으로 구현한 TDD 기반 MVP 백엔드 앱입니다.

## 구현 범위
- 비로그인 단일 기기 흐름 (device_id 기반 격리)
- 식재료 등록/조회/검색
- 동일성 규칙에 따른 수량 병합
- 수량 차감, 전량 소진/폐기 처리
- D-3 알림 대상 계산 및 중복 발송 방지 로그
- DeviceTable 기반 푸시 권한 상태 관리
- 권한 거부/미결정 시 대시보드 대체 안내 정책
- KPI 이벤트 저장/조회
- APScheduler 일 1회 D-3 배치 실행
- OCR은 Vision API 미연동 상태로 수동입력 fallback만 제공

## 기술 스택
- FastAPI
- Python 3.11+
- Pytest
- Azure Table Storage (실제 DB)
- Next.js (App Router) PWA

## 저장소 설정
- 기본값: `REPOSITORY_KIND=azure`
- `AZURE_TABLES_CONNECTION_STRING`가 반드시 필요
- 테스트/로컬 임시 검증만 `REPOSITORY_KIND=inmemory` 사용

### OCR 설정 (배포 권장)
- OCR 연동을 사용하려면 아래 환경변수를 설정해야 합니다.

```powershell
$env:OCR_API_KEY="K86524379288957"
$env:OCR_API_URL="https://ocr.space"
$env:OCR_ENGINE="3"
$env:OCR_LANGUAGE="kor"
```

- 배포 시에는 `.env.example`를 복사해 실제 환경 변수 값으로 주입해 주세요.

### Web Push 설정
- 실제 Web Push 발송을 위해 아래 환경변수가 필요합니다.

```powershell
$env:WEB_PUSH_VAPID_PRIVATE_KEY="<your-private-key>"
$env:WEB_PUSH_VAPID_SUBJECT="mailto:you@example.com"
```

- 푸시 권한이 granted 이고 구독 정보가 저장된 경우에만 push 채널로 발송됩니다.
- 그렇지 않으면 PRD 정책대로 앱 내 안내(in_app fallback)로 처리됩니다.

예시 (PowerShell):

```powershell
$env:REPOSITORY_KIND="azure"
$env:AZURE_TABLES_CONNECTION_STRING="DefaultEndpointsProtocol=..."
$env:AZURE_TABLES_PREFIX="Fridge"
```

## 로컬 실행
1. 의존성 설치

```bash
python -m pip install -e .[dev]
```

2. 테스트 실행

```bash
python -m pytest -q
```

3. API 실행

```bash
python -m uvicorn app.main:app --reload
```

4. 웹 프론트엔드 실행

```bash
cd web
npm install
npm run dev
```

5. 접속

- 프론트엔드: http://localhost:3000
- 백엔드 API: http://localhost:8000

## 주요 엔드포인트
- GET /health
- POST /ocr/mock
- POST /device/register
- PUT /device/{device_id}/push-permission
- PUT /device/{device_id}/push-subscription
- GET /device/{device_id}/push-subscription
- DELETE /device/{device_id}/push-subscription
- GET /dashboard/{device_id}/alerts
- POST /inventory
- GET /inventory/{device_id}/{item_id}
- POST /inventory/{item_id}/reduce
- POST /inventory/{item_id}/discard
- GET /search/{device_id}?q=...
- POST /notifications/d3/run
- GET /kpi/{device_id}
- GET /kpi/{device_id}/summary?days=30

## 프론트엔드 화면
- / : 대시보드(상태 요약, 전체 재고, D-3 배치 실행)
- /register : OCR mock + 수동입력 등록
- /inventory : 검색, 수량 차감, 전량 폐기

## 비고
- 현재 버전은 배포 구성을 포함하지 않습니다.
- Vision API는 연동하지 않았으며, OCR은 수동입력 전환을 위한 mock 결과만 반환합니다.
