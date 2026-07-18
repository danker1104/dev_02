from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional
from urllib.request import Request, urlopen

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware

from app.repository import create_repository
from app.schemas import (
    AdjustQuantityRequest,
    DashboardAlertView,
    DeviceRegisterRequest,
    DeviceView,
    InventoryBatchView,
    InventoryItemView,
    KPIEventView,
    KPISummaryView,
    OCRResult,
    PushSubscriptionUpsertRequest,
    PushSubscriptionView,
    PushPermissionUpdateRequest,
    RegisterRequest,
)
from app.services import (
    DeviceService,
    InventoryService,
    KPIService,
    NotificationService,
    detect_canonical_ingredient_in_text,
    normalize_ingredient_name,
)

repo = create_repository()
device_service = DeviceService(repo)
kpi_service = KPIService(repo)
inventory_service = InventoryService(repo, kpi=kpi_service)
notification_service = NotificationService(repo, device_service=device_service, kpi=kpi_service)
scheduler = BackgroundScheduler(timezone="UTC")


def _run_daily_d3_job() -> None:
    notification_service.dispatch_d3(today=date.today())


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not scheduler.running:
        scheduler.add_job(_run_daily_d3_job, CronTrigger(hour=0, minute=0), id="daily-d3", replace_existing=True)
        scheduler.start()
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title="냉장고 알리미 MVP API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _ocr_fallback(reason: str) -> OCRResult:
    return OCRResult(
        name=None,
        expiry_date=None,
        expiry_source=None,
        confidence=0.0,
        fallback_to_manual=True,
        fail_reason=reason,
    )


def _build_multipart_form_data(fields: dict[str, str], file_field_name: str, file_name: str, file_bytes: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = f"----OCRBoundary{uuid.uuid4().hex}"
    body_parts: list[bytes] = []
    for key, value in fields.items():
        body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
        body_parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body_parts.append(f"{value}\r\n".encode("utf-8"))

    body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
    body_parts.append(
        f'Content-Disposition: form-data; name="{file_field_name}"; filename="{file_name}"\r\n'.encode("utf-8")
    )
    body_parts.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body_parts.append(file_bytes)
    body_parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(body_parts), f"multipart/form-data; boundary={boundary}"


def _extract_expiry_date(text: str) -> tuple[Optional[date], Optional[str]]:
    compact_year_pattern = r"(?<!\d)(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})(?!\d)"
    patterns_with_year = [
        r"(?P<y>\d{4})\s*[-./]\s*(?P<m>\d{1,2})\s*[-./]\s*(?P<d>\d{1,2})",
        r"(?P<y>\d{4})\s*년\s*(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일?",
        r"(?P<y>\d{4})\s+(?P<m>\d{1,2})\s+(?P<d>\d{1,2})",
        r"(?P<y>\d{2})\s*[-./]\s*(?P<m>\d{1,2})\s*[-./]\s*(?P<d>\d{1,2})",
        r"(?P<y>\d{2})\s+(?P<m>\d{1,2})\s+(?P<d>\d{1,2})",
    ]
    patterns_without_year = [
        r"(?P<m>\d{1,2})\s*[-./]\s*(?P<d>\d{1,2})",
        r"(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일?",
    ]
    expiry_keywords = re.compile(r"(유통기한|소비기한|까지|best\s*before|expiry|exp\.?)", re.IGNORECASE)
    manufacturing_keywords = re.compile(r"(제조일|제조일자|제조년월일|manufact|mfg)", re.IGNORECASE)
    line_label_pattern = re.compile(
        r"(?P<expiry>유통기한|소비기한|까지|best\s*before|expiry|exp\.?)|(?P<mfg>제조일|제조일자|제조년월일|manufact|mfg)",
        re.IGNORECASE,
    )

    today = date.today()

    def _overlaps_existing(spans: list[tuple[int, int]], start: int, end: int) -> bool:
        for s, e in spans:
            if start < e and s < end:
                return True
        return False

    def _coerce_yearless(month: int, day: int) -> date:
        # Do not auto-promote to next year. Keep current year to avoid surprising shifts.
        return date(today.year, month, day)

    def _line_for_span(source: str, start: int, end: int) -> str:
        line_start = source.rfind("\n", 0, start)
        line_end = source.find("\n", end)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1
        if line_end == -1:
            line_end = len(source)
        return source[line_start:line_end]

    def _parse_date_match(match: re.Match[str], *, has_year: bool) -> date:
        month = int(match.group("m"))
        day = int(match.group("d"))
        if has_year:
            year = int(match.group("y"))
            if year < 100:
                year += 2000
            return date(year, month, day)
        return _coerce_yearless(month, day)

    def _collect_label_linked_candidates() -> set[date]:
        linked: set[date] = set()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            labels = [
                (m.start(), "expiry" if m.group("expiry") else "mfg")
                for m in line_label_pattern.finditer(line)
            ]
            if not labels:
                continue

            date_matches: list[tuple[int, date]] = []
            for pattern in patterns_with_year:
                for match in re.finditer(pattern, line):
                    try:
                        date_matches.append((match.start(), _parse_date_match(match, has_year=True)))
                    except ValueError:
                        continue
            for match in re.finditer(compact_year_pattern, line):
                try:
                    date_matches.append((match.start(), _parse_date_match(match, has_year=True)))
                except ValueError:
                    continue
            for pattern in patterns_without_year:
                for match in re.finditer(pattern, line):
                    try:
                        date_matches.append((match.start(), _parse_date_match(match, has_year=False)))
                    except ValueError:
                        continue

            for pos, parsed in date_matches:
                prev_labels = [item for item in labels if item[0] <= pos]
                if not prev_labels:
                    continue
                nearest = max(prev_labels, key=lambda item: item[0])
                if nearest[1] == "expiry":
                    linked.add(parsed)
        return linked

    candidates: set[date] = set()
    keyword_candidates: set[date] = set()
    label_linked_candidates = _collect_label_linked_candidates()
    year_spans: list[tuple[int, int]] = []

    for pattern in patterns_with_year:
        for match in re.finditer(pattern, text):
            try:
                year = int(match.group("y"))
                month = int(match.group("m"))
                day = int(match.group("d"))
                if year < 100:
                    year += 2000
                parsed = date(year, month, day)
                candidates.add(parsed)
                line = _line_for_span(text, match.start(), match.end())
                if expiry_keywords.search(line) and not manufacturing_keywords.search(line):
                    keyword_candidates.add(parsed)
                year_spans.append((match.start(), match.end()))
            except ValueError:
                continue

    for pattern in patterns_without_year:
        for match in re.finditer(pattern, text):
            if _overlaps_existing(year_spans, match.start(), match.end()):
                continue
            try:
                month = int(match.group("m"))
                day = int(match.group("d"))
                parsed = _coerce_yearless(month, day)
                candidates.add(parsed)
                line = _line_for_span(text, match.start(), match.end())
                if expiry_keywords.search(line) and not manufacturing_keywords.search(line):
                    keyword_candidates.add(parsed)
            except ValueError:
                continue

    if not candidates and not label_linked_candidates and not keyword_candidates:
        return None, None

    current_year = today.year
    min_year = current_year - 1
    max_year = current_year + 5

    linked_plausible = {d for d in label_linked_candidates if min_year <= d.year <= max_year}
    if linked_plausible:
        return max(linked_plausible), "label_linked"

    keyword_plausible = {d for d in keyword_candidates if min_year <= d.year <= max_year}
    if keyword_plausible:
        return max(keyword_plausible), "keyword_line"

    plausible = {d for d in candidates if min_year <= d.year <= max_year}
    if plausible:
        return max(plausible), "heuristic"

    # If all OCR years are implausible (for example 2080), fall back to current year.
    normalized_to_current_year: set[date] = set()
    for candidate in candidates:
        try:
            normalized_to_current_year.add(date(current_year, candidate.month, candidate.day))
        except ValueError:
            continue

    if normalized_to_current_year:
        return max(normalized_to_current_year), "normalized_year"
    return max(candidates), "fallback_max"


def _sanitize_name_candidate(line: str) -> str:
    value = line.strip()
    value = re.sub(r"[•·]", " ", value)
    value = re.sub(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}", " ", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\s?(?:kg|g|mg|ml|l|개|입|봉|팩)\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" -_:;,./•·")
    return value.strip()

def _extract_product_name_field(line: str) -> Optional[str]:
    if "제품명" not in line:
        return None

    tail = line.split("제품명", 1)[1]
    tail = re.sub(r"^[\s:\-]+", "", tail)
    tail = re.split(r"(식품유형|제조원|유통기한|소비기한|원재료|보관방법|고객)", tail)[0]
    name = _sanitize_name_candidate(tail)
    return name or None


def _expand_candidate_fragments(line: str) -> list[str]:
    fragments = re.split(r"[•·|]", line)
    if len(fragments) == 1:
        return [line]
    return [frag.strip() for frag in fragments if frag.strip()]


def _contains_date_keyword(line: str) -> bool:
    if re.search(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}", line):
        return True
    return bool(re.search(r"(유통기한|소비기한|제조일|까지|년|월|일)", line))


def _pick_name_from_ocr_text(parsed_text: str) -> Optional[str]:
    lines = [line.strip() for line in parsed_text.splitlines() if line.strip()]
    if not lines:
        return None

    best_name: Optional[str] = None
    best_score = -10**9

    for line in lines:
        explicit_name = _extract_product_name_field(line)
        if explicit_name:
            return explicit_name

        for fragment in _expand_candidate_fragments(line):
            if _contains_date_keyword(fragment):
                continue

            candidate = _sanitize_name_candidate(fragment)
            if len(candidate) < 2:
                continue
            if len(candidate) > 30:
                continue
            if re.search(r"(제조원|식품유형|고객|센터|의견|원재료|보관)", candidate):
                continue

            korean_count = len(re.findall(r"[가-힣]", candidate))
            alpha_count = len(re.findall(r"[A-Za-z]", candidate))
            digit_count = len(re.findall(r"\d", candidate))
            score = (korean_count * 3) + alpha_count - (digit_count * 2)

            if score > best_score:
                best_score = score
                best_name = candidate

    if best_name:
        return best_name

    # Fallback: normalize the first OCR line when no strong candidate exists.
    fallback = _sanitize_name_candidate(lines[0])
    return fallback or None


def _extract_file_from_multipart(body: bytes, content_type: str) -> tuple[bytes, str, str] | None:
    if "multipart/form-data" not in content_type:
        return None

    boundary_match = re.search(r"boundary=([^;]+)", content_type)
    if not boundary_match:
        return None

    boundary = boundary_match.group(1).strip().strip('"').encode("utf-8")
    marker = b"--" + boundary
    for raw_part in body.split(marker):
        part = raw_part.strip()
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue

        header_blob, data_blob = part.split(b"\r\n\r\n", 1)
        headers_text = header_blob.decode("utf-8", errors="ignore")
        if "name=\"file\"" not in headers_text:
            continue

        filename_match = re.search(r'filename="([^"]*)"', headers_text)
        file_name = filename_match.group(1) if filename_match else "upload.png"

        type_match = re.search(r"Content-Type:\s*([^\r\n]+)", headers_text, flags=re.IGNORECASE)
        mime_type = type_match.group(1).strip() if type_match else "image/png"

        file_bytes = data_blob
        if file_bytes.endswith(b"\r\n"):
            file_bytes = file_bytes[:-2]
        if file_bytes.endswith(b"--"):
            file_bytes = file_bytes[:-2]

        return file_bytes, file_name, mime_type

    return None


@app.post("/ocr/mock", response_model=OCRResult)
async def ocr_mock(request: FastAPIRequest) -> OCRResult:
    body = await request.body()
    parsed_file = _extract_file_from_multipart(body=body, content_type=request.headers.get("content-type", ""))
    if parsed_file is None:
        return _ocr_fallback("missing_file")

    file_bytes, file_name, mime_type = parsed_file

    try:
        if not file_bytes:
            return _ocr_fallback("empty_file")

        api_key = os.getenv("OCR_API_KEY")
        if not api_key:
            return _ocr_fallback("missing_api_key")

        api_url = os.getenv("OCR_API_URL", "https://ocr.space")
        if api_url.rstrip("/") == "https://ocr.space":
            api_url = "https://api.ocr.space/parse/image"
        payload = {
            "apikey": api_key,
            "language": os.getenv("OCR_LANGUAGE", "kor"),
            "isOverlayRequired": "false",
            "OCREngine": os.getenv("OCR_ENGINE", "3"),
        }
        body, content_type = _build_multipart_form_data(
            fields=payload,
            file_field_name="file",
            file_name=file_name,
            file_bytes=file_bytes,
            content_type=mime_type,
        )
        request = Request(api_url, data=body, headers={"Content-Type": content_type}, method="POST")
        with urlopen(request, timeout=15) as response:
            payload_response = json.loads(response.read().decode("utf-8"))
    except Exception:
        return _ocr_fallback("request_failed")

    parsed_results = payload_response.get("ParsedResults") or []
    if not parsed_results:
        return _ocr_fallback("empty_parsed_results")

    parsed_text = parsed_results[0].get("ParsedText", "")
    name = detect_canonical_ingredient_in_text(parsed_text)
    if not name:
        name = _pick_name_from_ocr_text(parsed_text)
    if not name:
        return _ocr_fallback("name_not_found")
    name = normalize_ingredient_name(name)

    expiry_date, expiry_source = _extract_expiry_date(parsed_text)
    if expiry_source in {"label_linked", "keyword_line"}:
        confidence = 0.9
    elif expiry_source is not None:
        confidence = 0.65
    else:
        confidence = 0.6

    return OCRResult(
        name=name,
        expiry_date=expiry_date,
        expiry_source=expiry_source,
        confidence=confidence,
        fallback_to_manual=False,
        fail_reason=None,
    )


@app.post("/device/register", response_model=DeviceView)
def register_device(payload: DeviceRegisterRequest) -> DeviceView:
    profile = device_service.register_or_get(device_id=payload.device_id)
    return DeviceView(
        device_id=profile.device_id,
        push_permission_state=profile.push_permission_state,
        created_at=profile.created_at.isoformat(),
        last_active_at=profile.last_active_at.isoformat(),
    )


@app.put("/device/{device_id}/push-permission", response_model=DeviceView)
def update_push_permission(device_id: str, payload: PushPermissionUpdateRequest) -> DeviceView:
    profile = device_service.update_push_permission(device_id=device_id, state=payload.state)
    return DeviceView(
        device_id=profile.device_id,
        push_permission_state=profile.push_permission_state,
        created_at=profile.created_at.isoformat(),
        last_active_at=profile.last_active_at.isoformat(),
    )


@app.put("/device/{device_id}/push-subscription", response_model=PushSubscriptionView)
def upsert_push_subscription(device_id: str, payload: PushSubscriptionUpsertRequest) -> PushSubscriptionView:
    sub = device_service.upsert_push_subscription(
        device_id=device_id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    return PushSubscriptionView(
        device_id=sub.device_id,
        endpoint=sub.endpoint,
        created_at=sub.created_at.isoformat(),
        updated_at=sub.updated_at.isoformat(),
    )


@app.get("/device/{device_id}/push-subscription", response_model=PushSubscriptionView)
def get_push_subscription(device_id: str) -> PushSubscriptionView:
    sub = device_service.get_push_subscription(device_id=device_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="push subscription not found")
    return PushSubscriptionView(
        device_id=sub.device_id,
        endpoint=sub.endpoint,
        created_at=sub.created_at.isoformat(),
        updated_at=sub.updated_at.isoformat(),
    )


@app.delete("/device/{device_id}/push-subscription")
def delete_push_subscription(device_id: str) -> dict[str, str]:
    device_service.delete_push_subscription(device_id=device_id)
    return {"status": "deleted"}


@app.get("/dashboard/{device_id}/alerts", response_model=DashboardAlertView)
def dashboard_alerts(device_id: str, today: Optional[date] = None) -> DashboardAlertView:
    profile = device_service.get(device_id=device_id)
    items = inventory_service.list_priority_items(device_id=device_id, today=today or date.today())
    denied = profile.push_permission_state.value == "denied"
    undecided = profile.push_permission_state.value == "default"
    return DashboardAlertView(
        push_permission_denied=denied,
        show_permission_modal=(denied or undecided) and len(items) > 0,
        persistent_warning_banner=denied,
        priority_items=items,
    )


@app.get("/kpi/{device_id}", response_model=list[KPIEventView])
def list_kpi(device_id: str) -> list[KPIEventView]:
    events = kpi_service.list_events(device_id=device_id)
    return [
        KPIEventView(
            event_id=e.event_id,
            event_name=e.event_name,
            occurred_at=e.occurred_at.isoformat(),
            properties=e.properties,
        )
        for e in events
    ]


@app.get("/kpi/{device_id}/summary", response_model=KPISummaryView)
def summarize_kpi(device_id: str, days: int = 30) -> KPISummaryView:
    if days <= 0:
        raise HTTPException(status_code=400, detail="days must be positive")
    summary = kpi_service.summarize(device_id=device_id, days=days)
    return KPISummaryView(**summary)


@app.post("/inventory", response_model=InventoryItemView)
def register_inventory(payload: RegisterRequest, today: Optional[date] = None) -> InventoryItemView:
    base_day = today or date.today()
    kpi_service.track(device_id=payload.device_id, event_name="inventory_register_attempted")
    device_service.register_or_get(device_id=payload.device_id)
    item = inventory_service.register_item(
        device_id=payload.device_id,
        name=payload.name,
        expiry_date=payload.expiry_date,
        storage_type=payload.storage_type,
        qty=payload.qty,
        today=base_day,
    )
    _, batches = inventory_service.get_item_view(device_id=payload.device_id, item_id=item.item_id, today=base_day)
    return InventoryItemView(
        item_id=item.item_id,
        name=item.name,
        storage_type=item.storage_type,
        total_qty=item.total_qty,
        status=item.status,
        batches=[
            InventoryBatchView(batch_id=b.batch_id, expiry_date=b.expiry_date, qty=b.qty, status=b.status)
            for b in batches
        ],
    )


@app.get("/inventory/{device_id}/{item_id}", response_model=InventoryItemView)
def get_inventory_item(device_id: str, item_id: str, today: Optional[date] = None) -> InventoryItemView:
    view = inventory_service.get_item_view(device_id=device_id, item_id=item_id, today=today or date.today())
    if view is None:
        raise HTTPException(status_code=404, detail="item not found")
    item, batches = view
    return InventoryItemView(
        item_id=item.item_id,
        name=item.name,
        storage_type=item.storage_type,
        total_qty=item.total_qty,
        status=item.status,
        batches=[
            InventoryBatchView(batch_id=b.batch_id, expiry_date=b.expiry_date, qty=b.qty, status=b.status)
            for b in batches
        ],
    )


@app.post("/inventory/{item_id}/reduce", response_model=InventoryItemView)
def reduce_inventory(item_id: str, payload: AdjustQuantityRequest, today: Optional[date] = None) -> InventoryItemView:
    item = inventory_service.reduce_quantity(
        device_id=payload.device_id,
        item_id=item_id,
        amount=payload.amount,
        today=today or date.today(),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")

    _, batches = inventory_service.get_item_view(device_id=payload.device_id, item_id=item.item_id, today=today or date.today())
    return InventoryItemView(
        item_id=item.item_id,
        name=item.name,
        storage_type=item.storage_type,
        total_qty=item.total_qty,
        status=item.status,
        batches=[
            InventoryBatchView(batch_id=b.batch_id, expiry_date=b.expiry_date, qty=b.qty, status=b.status)
            for b in batches
        ],
    )


@app.post("/inventory/{item_id}/discard", response_model=InventoryItemView)
def discard_inventory(item_id: str, payload: AdjustQuantityRequest, today: Optional[date] = None) -> InventoryItemView:
    item = inventory_service.discard_item(device_id=payload.device_id, item_id=item_id, today=today or date.today())
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")

    _, batches = inventory_service.get_item_view(device_id=payload.device_id, item_id=item.item_id, today=today or date.today())
    return InventoryItemView(
        item_id=item.item_id,
        name=item.name,
        storage_type=item.storage_type,
        total_qty=item.total_qty,
        status=item.status,
        batches=[
            InventoryBatchView(batch_id=b.batch_id, expiry_date=b.expiry_date, qty=b.qty, status=b.status)
            for b in batches
        ],
    )


@app.get("/search/{device_id}")
def search_inventory(device_id: str, q: str, today: Optional[date] = None):
    device_service.register_or_get(device_id=device_id)
    return inventory_service.search(device_id=device_id, query=q, today=today or date.today())


@app.post("/notifications/d3/run")
def run_d3_notification(today: Optional[date] = None):
    candidates = notification_service.dispatch_d3(today=today or date.today())
    return {"count": len(candidates), "items": candidates}
