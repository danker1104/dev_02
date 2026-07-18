from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional


class StorageType(str, Enum):
    FRIDGE = "냉장"
    FREEZER = "냉동"
    ROOM = "실온"


class BatchStatus(str, Enum):
    OWNED = "보유"
    IMMINENT = "임박"
    RISK = "기한 지남"
    CONSUMED = "소진"
    DISCARDED = "폐기"


class PushPermissionState(str, Enum):
    DEFAULT = "default"
    GRANTED = "granted"
    DENIED = "denied"


@dataclass
class InventoryItem:
    device_id: str
    item_id: str
    name: str
    storage_type: StorageType
    total_qty: int
    status: BatchStatus
    updated_at: datetime


@dataclass
class InventoryBatch:
    device_id: str
    item_id: str
    batch_id: str
    expiry_date: date
    qty: int
    status: BatchStatus


@dataclass
class NotificationLog:
    device_id: str
    batch_id: str
    notify_type: str
    channel: str
    delivery_status: str
    sent_at: datetime


@dataclass
class DeviceProfile:
    device_id: str
    push_permission_state: PushPermissionState
    created_at: datetime
    last_active_at: datetime


@dataclass
class KPIEvent:
    device_id: str
    event_id: str
    event_name: str
    occurred_at: datetime
    properties: dict[str, str]


@dataclass
class PushSubscription:
    device_id: str
    endpoint: str
    p256dh: str
    auth: str
    created_at: datetime
    updated_at: datetime
