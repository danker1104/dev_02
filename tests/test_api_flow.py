import json
import os
from datetime import date

from fastapi.testclient import TestClient

os.environ["REPOSITORY_KIND"] = "inmemory"
os.environ["OCR_API_KEY"] = "test-key"
os.environ["OCR_API_URL"] = "https://ocr.space"
os.environ["OCR_ENGINE"] = "3"
os.environ["OCR_LANGUAGE"] = "kor"

from app.main import app, repo


client = TestClient(app)


def setup_function() -> None:
    repo.clear_all()


def test_ocr_endpoint_parses_uploaded_image(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "양파\n2026-07-14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "양파"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_name_extraction_skips_noise_line(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "행사상품\n무농약 양파\n2026-07-14\n1kg"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "양파"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_name_extraction_prefers_product_name_field(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "•제품명 : 제주두부 •식품유형 : 두부\n2026-07-14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "두부"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_name_extraction_normalizes_jejubu_to_dubu(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 제주부\n2026-07-14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "두부"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_extracts_expiry_date_from_korean_format(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 찌개두부\n소비기한 2026년 7월 14일"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "두부"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_extracts_expiry_date_from_spaced_dot_format(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "두부\n유통기한 2026. 07. 14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "두부"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_picks_canonical_ingredient_if_keyword_exists_in_text(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "브랜드 행사상품\n유기농 당근 500g\n소비기한 2026 07 14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "당근"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_prefers_later_date_when_multiple_dates_exist(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 두부\n제조일자 2026-07-01\n유통기한 2026-07-14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "두부"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_uses_current_year_when_year_is_missing(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 당근\n유통기한 7월 14일"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "당근"
    expected = f"{date.today().year}-07-14"
    assert result.json()["expiry_date"] == expected
    assert result.json()["fallback_to_manual"] is False


def test_ocr_prefers_later_date_with_mfg_yearless_and_expiry_yearless(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 두부\n제조일자 7/1\n유통기한 7/14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "두부"
    expected = f"{date.today().year}-07-14"
    assert result.json()["expiry_date"] == expected
    assert result.json()["fallback_to_manual"] is False


def test_ocr_ignores_implausible_far_future_year(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 두부\n유통기한 2080-07-14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "두부"
    expected = f"{date.today().year}-07-14"
    assert result.json()["expiry_date"] == expected
    assert result.json()["fallback_to_manual"] is False


def test_ocr_prefers_expiry_keyword_date_over_unrelated_later_date(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 당근\n유통기한 2026-07-14\n고객센터 2026-12-31"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "당근"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_prefers_expiry_date_when_mfg_and_expiry_share_same_line(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 두부\n제조일자 2026-07-01 소비기한 2026-07-14"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["name"] == "두부"
    assert result.json()["expiry_date"] == "2026-07-14"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_yearless_date_does_not_promote_to_next_year(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 당근\n유통기한 3/20"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    expected = f"{date.today().year}-03-20"
    assert result.json()["expiry_date"] == expected
    assert result.json()["fallback_to_manual"] is False


def test_ocr_compact_yyyymmdd_is_used_when_linked_to_expiry_keyword(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 당근\n유통기한20260320"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["expiry_date"] == "2026-03-20"
    assert result.json()["fallback_to_manual"] is False


def test_ocr_compact_yyyymmdd_is_ignored_without_expiry_keyword(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 당근\n고객센터 20260320"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["expiry_date"] is None
    assert result.json()["fallback_to_manual"] is False


def test_ocr_compact_yyyymmdd_does_not_partial_match_long_digits(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ParsedResults": [
                        {"ParsedText": "제품명: 당근\n유통기한 2026630320"}
                    ],
                    "OCRExitCode": 1,
                    "IsErroredOnProcessing": False,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=10) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.main.urlopen", fake_urlopen)

    result = client.post(
        "/ocr/mock",
        files={"file": ("image.png", b"fake-image", "image/png")},
    )

    assert result.status_code == 200
    assert result.json()["expiry_date"] is None
    assert result.json()["fallback_to_manual"] is False


def test_end_to_end_flow_without_vision_api() -> None:
    dev = client.post("/device/register", json={"device_id": "device-a"})
    assert dev.status_code == 200

    update_push = client.put("/device/device-a/push-permission", json={"state": "denied"})
    assert update_push.status_code == 200
    assert update_push.json()["push_permission_state"] == "denied"

    sub = client.put(
        "/device/device-a/push-subscription",
        json={
            "endpoint": "https://push.example/sub-a",
            "keys": {"p256dh": "key-p256", "auth": "key-auth"},
        },
    )
    assert sub.status_code == 200

    sub_get = client.get("/device/device-a/push-subscription")
    assert sub_get.status_code == 200
    assert sub_get.json()["endpoint"] == "https://push.example/sub-a"

    ocr = client.post("/ocr/mock")
    assert ocr.status_code == 200
    assert ocr.json()["fallback_to_manual"] is True

    created = client.post(
        "/inventory?today=2026-07-11",
        json={
            "device_id": "device-a",
            "name": "양파",
            "expiry_date": "2026-07-14",
            "storage_type": "실온",
            "qty": 2,
        },
    )
    assert created.status_code == 200
    item_id = created.json()["item_id"]

    searched = client.get("/search/device-a?q=양파&today=2026-07-11")
    assert searched.status_code == 200
    assert searched.json()[0]["has_stock"] is True
    assert searched.json()[0]["total_qty"] == 2

    reduced = client.post(
        f"/inventory/{item_id}/reduce?today=2026-07-11",
        json={"device_id": "device-a", "amount": 1},
    )
    assert reduced.status_code == 200
    assert reduced.json()["total_qty"] == 1

    d3 = client.post("/notifications/d3/run?today=2026-07-11")
    assert d3.status_code == 200
    assert d3.json()["count"] == 1

    alert = client.get("/dashboard/device-a/alerts?today=2026-07-11")
    assert alert.status_code == 200
    assert alert.json()["push_permission_denied"] is True
    assert alert.json()["persistent_warning_banner"] is True

    d3_again = client.post("/notifications/d3/run?today=2026-07-11")
    assert d3_again.status_code == 200
    assert d3_again.json()["count"] == 0

    discarded = client.post(
        f"/inventory/{item_id}/discard?today=2026-07-11",
        json={"device_id": "device-a", "amount": 1},
    )
    assert discarded.status_code == 200
    assert discarded.json()["total_qty"] == 0

    kpi = client.get("/kpi/device-a")
    assert kpi.status_code == 200
    names = [e["event_name"] for e in kpi.json()]
    assert "inventory_registered" in names
    assert "search_used" in names
    assert "notification_sent" in names

    summary = client.get("/kpi/device-a/summary?days=30")
    assert summary.status_code == 200
    assert summary.json()["registration_attempts"] >= 1
    assert summary.json()["registration_successes"] >= 1

    deleted = client.delete("/device/device-a/push-subscription")
    assert deleted.status_code == 200


def test_inventory_register_accepts_consumption_date_alias() -> None:
    dev = client.post("/device/register", json={"device_id": "device-b"})
    assert dev.status_code == 200

    created = client.post(
        "/inventory?today=2026-07-11",
        json={
            "device_id": "device-b",
            "name": "두부",
            "소비기한": "2026-07-14",
            "storage_type": "냉장",
            "qty": 1,
        },
    )

    assert created.status_code == 200
    assert created.json()["name"] == "두부"
    assert created.json()["total_qty"] == 1
