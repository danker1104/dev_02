# 배포 대상 정리

이 저장소는 백엔드 FastAPI와 프론트엔드 Next.js가 분리된 구조입니다. 배포할 때는 두 앱을 따로 보거나, 한 플랫폼에서 함께 묶어서 보시면 됩니다.

## 1) 실제로 배포해야 하는 파일

### 백엔드
- `app/main.py`
- `app/models.py`
- `app/repository.py`
- `app/schemas.py`
- `app/services.py`
- `app/__init__.py`
- `pyproject.toml`
- `.env.example`
- `README.md`

### 프론트엔드
- `web/app/layout.js`
- `web/app/page.js`
- `web/app/register/page.js`
- `web/app/inventory/page.js`
- `web/app/globals.css`
- `web/app/sw-register.js`
- `web/lib/api.js`
- `web/public/manifest.webmanifest`
- `web/public/sw.js`
- `web/package.json`
- `web/package-lock.json`
- `web/next.config.mjs`
- `web/jsconfig.json`

## 2) 배포 전에 빼야 하는 파일

- `tests/`
- `web/.next/`
- `web/node_modules/`
- `app/__pycache__/`
- `tests/__pycache__/`
- `fridge_alert_mvp.egg-info/`
- `web/.env.local`
- `tmp-ocr-sample.png`
- `test ex.png`

## 3) 현재 구조에서 중요한 배포 포인트

- 백엔드는 `app.main:app` 이 진입점입니다.
- 프론트엔드는 `web` 폴더의 Next.js 앱입니다.
- 프론트는 `NEXT_PUBLIC_API_BASE` 로 백엔드 주소를 받아야 합니다.
- 백엔드는 기본 저장소가 Azure Table Storage 이므로 `AZURE_TABLES_CONNECTION_STRING` 가 필요합니다.
- 테스트 환경에서는 `REPOSITORY_KIND=inmemory` 를 사용하고, 실제 배포에서는 `REPOSITORY_KIND=azure` 쪽이 기본입니다.

## 4) 추천 배포 방식

1. 백엔드: FastAPI 컨테이너 또는 App Service 계열로 배포
2. 프론트엔드: Next.js 빌드 후 정적/Node 배포
3. 환경변수 분리: 백엔드용, 프론트엔드용으로 나눠 관리

## 5) 지금 바로 필요한 최소 체크

- 백엔드 실행 확인: `python -m uvicorn app.main:app`
- 프론트 빌드 확인: `cd web && npm run build`
- 테스트 확인: `python -m pytest -q`

원하면 다음 단계에서 배포용 파일만 남기는 구조로 더 정리해드릴 수 있습니다. 예를 들면 Dockerfile 추가, `.env.example` 정리, 또는 Azure 배포용 설정 파일까지 붙일 수 있습니다.