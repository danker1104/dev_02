from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import AliasChoices, BaseModel, Field

from app.models import BatchStatus, PushPermissionState, StorageType


class RegisterRequest(BaseModel):
    device_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    # Treat '유통기한' and '소비기한' as the same semantic field.
    expiry_date: date = Field(
        validation_alias=AliasChoices("expiry_date", "consume_by_date", "best_before_date", "유통기한", "소비기한")
    )
    storage_type: StorageType = StorageType.FRIDGE
    qty: int = Field(ge=1)


class AdjustQuantityRequest(BaseModel):
    device_id: str = Field(min_length=1)
    amount: int = Field(ge=1)


class SearchResult(BaseModel):
    item_id: str
    name: str
    status: BatchStatus
    has_stock: bool
    total_qty: int
    has_imminent_or_risk: bool


class InventoryBatchView(BaseModel):
    batch_id: str
    expiry_date: date
    qty: int
    status: BatchStatus


class InventoryItemView(BaseModel):
    item_id: str
    name: str
    storage_type: StorageType
    total_qty: int
    status: BatchStatus
    batches: list[InventoryBatchView]


class NotificationCandidate(BaseModel):
    device_id: str
    batch_id: str
    item_id: str
    name: str
    expiry_date: date
    days_left: int


class OCRResult(BaseModel):
    name: Optional[str] = None
    expiry_date: Optional[date] = None
    expiry_source: Optional[str] = None
    confidence: float = 0.0
    fallback_to_manual: bool = True
    fail_reason: Optional[str] = None


class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(min_length=1)


class PushPermissionUpdateRequest(BaseModel):
    state: PushPermissionState


class DeviceView(BaseModel):
    device_id: str
    push_permission_state: PushPermissionState
    created_at: str
    last_active_at: str


class PriorityItem(BaseModel):
    item_id: str
    name: str
    status: BatchStatus
    total_qty: int


class DashboardAlertView(BaseModel):
    push_permission_denied: bool
    show_permission_modal: bool
    persistent_warning_banner: bool
    priority_items: list[PriorityItem]


class KPIEventView(BaseModel):
    event_id: str
    event_name: str
    occurred_at: str
    properties: dict[str, str]


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)


class PushSubscriptionUpsertRequest(BaseModel):
    endpoint: str = Field(min_length=1)
    keys: PushSubscriptionKeys


class PushSubscriptionView(BaseModel):
    device_id: str
    endpoint: str
    created_at: str
    updated_at: str


class KPISummaryView(BaseModel):
    window_days: int
    registration_attempts: int
    registration_successes: int
    registration_success_rate: float
    avg_registration_completion_seconds: float
    search_usage_count: int
    search_usage_rate: float
    consume_conversion_rate: float
    discard_rate: float
    notification_revisit_24h_rate: float
