from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from uuid import uuid4

from app.models import (
    BatchStatus,
    DeviceProfile,
    InventoryBatch,
    InventoryItem,
    KPIEvent,
    NotificationLog,
    PushSubscription,
    PushPermissionState,
)
from app.repository import Repository, find_same_item
from app.schemas import NotificationCandidate, PriorityItem, SearchResult


CANONICAL_INGREDIENTS = [
    "두부",
    "당근",
    "가지",
    "양파",
    "대파",
    "감자",
    "고구마",
    "오이",
    "토마토",
    "호박",
    "브로콜리",
    "시금치",
    "상추",
    "애호박",
    "버섯",
    "우유",
    "계란",
    "요거트",
    "치즈",
    "사과",
    "바나나",
]

INGREDIENT_ALIAS_MAP = {
    "제주부": "두부",
    "찌개두부": "두부",
    "부침두부": "두부",
    "연두부": "두부",
    "순두부": "두부",
}


def detect_canonical_ingredient_in_text(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return None

    for alias, canonical in sorted(INGREDIENT_ALIAS_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in compact:
            return canonical

    for keyword in sorted(CANONICAL_INGREDIENTS, key=len, reverse=True):
        if keyword in compact:
            return keyword

    return None


def normalize_ingredient_name(name: str) -> str:
    value = name.strip()
    if not value:
        return value

    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[•·|:/,_-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    detected = detect_canonical_ingredient_in_text(value)
    if detected:
        return detected

    return value


class PushSender:
    def send(self, subscription: PushSubscription, payload: dict[str, str]) -> bool:
        raise NotImplementedError()


class WebPushSender(PushSender):
    def __init__(self, vapid_private_key: str, vapid_subject: str) -> None:
        self.vapid_private_key = vapid_private_key
        self.vapid_subject = vapid_subject

    @classmethod
    def from_env(cls) -> "WebPushSender | None":
        private_key = os.getenv("WEB_PUSH_VAPID_PRIVATE_KEY", "").strip()
        subject = os.getenv("WEB_PUSH_VAPID_SUBJECT", "").strip()
        if not private_key or not subject:
            return None
        return cls(vapid_private_key=private_key, vapid_subject=subject)

    def send(self, subscription: PushSubscription, payload: dict[str, str]) -> bool:
        try:
            from pywebpush import webpush
        except Exception:
            return False

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=self.vapid_private_key,
                vapid_claims={"sub": self.vapid_subject},
            )
            return True
        except Exception:
            return False


class DeviceService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def register_or_get(self, *, device_id: str) -> DeviceProfile:
        now = self.repo.now()
        current = self.repo.get_device(device_id)
        if current is not None:
            current.last_active_at = now
            self.repo.save_device(current)
            return current

        created = DeviceProfile(
            device_id=device_id,
            push_permission_state=PushPermissionState.DEFAULT,
            created_at=now,
            last_active_at=now,
        )
        self.repo.save_device(created)
        return created

    def update_push_permission(self, *, device_id: str, state: PushPermissionState) -> DeviceProfile:
        profile = self.register_or_get(device_id=device_id)
        profile.push_permission_state = state
        profile.last_active_at = self.repo.now()
        self.repo.save_device(profile)
        return profile

    def get(self, *, device_id: str) -> DeviceProfile:
        return self.register_or_get(device_id=device_id)

    def upsert_push_subscription(self, *, device_id: str, endpoint: str, p256dh: str, auth: str) -> PushSubscription:
        now = self.repo.now()
        current = self.repo.get_push_subscription(device_id)
        created_at = current.created_at if current is not None else now
        subscription = PushSubscription(
            device_id=device_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            created_at=created_at,
            updated_at=now,
        )
        self.repo.save_push_subscription(subscription)
        return subscription

    def get_push_subscription(self, *, device_id: str) -> PushSubscription | None:
        return self.repo.get_push_subscription(device_id)

    def delete_push_subscription(self, *, device_id: str) -> None:
        self.repo.delete_push_subscription(device_id)


class KPIService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def track(self, *, device_id: str, event_name: str, properties: dict[str, str] | None = None) -> None:
        event = KPIEvent(
            device_id=device_id,
            event_id=str(uuid4()),
            event_name=event_name,
            occurred_at=self.repo.now(),
            properties=properties or {},
        )
        self.repo.save_kpi_event(event)

    def list_events(self, *, device_id: str) -> list[KPIEvent]:
        return sorted(self.repo.list_kpi_events(device_id), key=lambda x: x.occurred_at, reverse=True)

    def summarize(self, *, device_id: str, days: int) -> dict[str, float | int]:
        now = self.repo.now()
        window_start = now - timedelta(days=days)
        events = [e for e in self.repo.list_kpi_events(device_id) if e.occurred_at >= window_start]
        events_sorted = sorted(events, key=lambda x: x.occurred_at)

        attempts = [e for e in events_sorted if e.event_name == "inventory_register_attempted"]
        successes = [e for e in events_sorted if e.event_name == "inventory_registered"]
        searches = [e for e in events_sorted if e.event_name == "search_used"]
        reduced = [e for e in events_sorted if e.event_name == "inventory_reduced"]
        discarded = [e for e in events_sorted if e.event_name == "inventory_discarded"]
        notifications = [e for e in events_sorted if e.event_name == "notification_sent"]

        completion_durations: list[float] = []
        attempt_idx = 0
        for success in successes:
            while attempt_idx < len(attempts) and attempts[attempt_idx].occurred_at <= success.occurred_at:
                attempt_idx += 1
            if attempt_idx == 0:
                continue
            prior = attempts[attempt_idx - 1]
            delta = (success.occurred_at - prior.occurred_at).total_seconds()
            if 0 <= delta <= 600:
                completion_durations.append(delta)

        revisit_events = {
            "search_used",
            "inventory_registered",
            "inventory_reduced",
            "inventory_discarded",
        }
        revisit_count = 0
        for sent in notifications:
            deadline = sent.occurred_at + timedelta(hours=24)
            revisited = any(
                e.event_name in revisit_events and sent.occurred_at < e.occurred_at <= deadline
                for e in events_sorted
            )
            if revisited:
                revisit_count += 1

        attempts_count = len(attempts)
        success_count = len(successes)
        search_count = len(searches)
        reduced_count = len(reduced)
        discarded_count = len(discarded)
        notification_count = len(notifications)

        return {
            "window_days": days,
            "registration_attempts": attempts_count,
            "registration_successes": success_count,
            "registration_success_rate": (success_count / attempts_count) if attempts_count else 0.0,
            "avg_registration_completion_seconds": (
                sum(completion_durations) / len(completion_durations) if completion_durations else 0.0
            ),
            "search_usage_count": search_count,
            "search_usage_rate": 1.0 if search_count > 0 else 0.0,
            "consume_conversion_rate": (reduced_count / success_count) if success_count else 0.0,
            "discard_rate": (discarded_count / success_count) if success_count else 0.0,
            "notification_revisit_24h_rate": (
                revisit_count / notification_count if notification_count else 0.0
            ),
        }


class InventoryService:
    def __init__(self, repo: Repository, kpi: KPIService | None = None) -> None:
        self.repo = repo
        self.kpi = kpi

    def _resolve_batch_status(self, expiry_date: date, today: date) -> BatchStatus:
        days_left = (expiry_date - today).days
        if days_left < 0:
            return BatchStatus.RISK
        if days_left <= 3:
            return BatchStatus.IMMINENT
        return BatchStatus.OWNED

    def _resolve_item_status(self, item_id: str, today: date) -> BatchStatus:
        batches = [b for b in self.repo.list_batches_by_item(item_id) if b.status == BatchStatus.OWNED or b.status == BatchStatus.IMMINENT or b.status == BatchStatus.RISK]
        if not batches:
            return BatchStatus.CONSUMED

        statuses = [self._resolve_batch_status(b.expiry_date, today) for b in batches if b.qty > 0]
        if not statuses:
            return BatchStatus.CONSUMED
        if BatchStatus.RISK in statuses:
            return BatchStatus.RISK
        if BatchStatus.IMMINENT in statuses:
            return BatchStatus.IMMINENT
        return BatchStatus.OWNED

    def register_item(
        self,
        *,
        device_id: str,
        name: str,
        expiry_date: date,
        storage_type,
        qty: int,
        today: date,
    ) -> InventoryItem:
        canonical_name = normalize_ingredient_name(name)
        items = self.repo.list_items_by_device(device_id)
        matched = find_same_item(items, canonical_name, storage_type.value)

        if matched is None:
            item = InventoryItem(
                device_id=device_id,
                item_id=str(uuid4()),
                name=canonical_name,
                storage_type=storage_type,
                total_qty=0,
                status=BatchStatus.OWNED,
                updated_at=self.repo.now(),
            )
            self.repo.save_item(item)
        else:
            item = matched

        batch = InventoryBatch(
            device_id=device_id,
            item_id=item.item_id,
            batch_id=str(uuid4()),
            expiry_date=expiry_date,
            qty=qty,
            status=self._resolve_batch_status(expiry_date, today),
        )
        self.repo.save_batch(batch)

        item.total_qty += qty
        item.status = self._resolve_item_status(item.item_id, today)
        item.updated_at = self.repo.now()
        self.repo.save_item(item)
        if self.kpi is not None:
            self.kpi.track(
                device_id=device_id,
                event_name="inventory_registered",
                properties={"item_id": item.item_id, "status": item.status.value},
            )
        return item

    def get_item_view(self, *, device_id: str, item_id: str, today: date):
        item = self.repo.get_item(item_id)
        if item is None or item.device_id != device_id:
            return None

        batches = []
        for b in self.repo.list_batches_by_item(item_id):
            if b.device_id != device_id:
                continue
            if b.status in (BatchStatus.CONSUMED, BatchStatus.DISCARDED):
                pass
            else:
                b.status = self._resolve_batch_status(b.expiry_date, today) if b.qty > 0 else BatchStatus.CONSUMED
            batches.append(b)

        item.status = self._resolve_item_status(item.item_id, today)
        self.repo.save_item(item)
        return item, sorted(batches, key=lambda x: x.expiry_date)

    def reduce_quantity(self, *, device_id: str, item_id: str, amount: int, today: date) -> InventoryItem | None:
        item = self.repo.get_item(item_id)
        if item is None or item.device_id != device_id:
            return None

        remaining = amount
        batches = sorted(self.repo.list_batches_by_item(item_id), key=lambda x: x.expiry_date)
        for b in batches:
            if remaining <= 0:
                break
            if b.qty <= 0 or b.status in (BatchStatus.CONSUMED, BatchStatus.DISCARDED):
                continue
            used = min(b.qty, remaining)
            b.qty -= used
            remaining -= used
            if b.qty == 0:
                b.status = BatchStatus.CONSUMED
            self.repo.save_batch(b)

        consumed = amount - remaining
        item.total_qty = max(0, item.total_qty - consumed)
        item.status = self._resolve_item_status(item_id, today)
        self.repo.save_item(item)
        if self.kpi is not None and consumed > 0:
            self.kpi.track(
                device_id=device_id,
                event_name="inventory_reduced",
                properties={"item_id": item.item_id, "consumed": str(consumed)},
            )
        return item

    def discard_item(self, *, device_id: str, item_id: str, today: date) -> InventoryItem | None:
        item = self.repo.get_item(item_id)
        if item is None or item.device_id != device_id:
            return None

        total = 0
        for b in self.repo.list_batches_by_item(item_id):
            if b.device_id != device_id:
                continue
            total += b.qty
            b.qty = 0
            b.status = BatchStatus.DISCARDED
            self.repo.save_batch(b)

        item.total_qty = max(0, item.total_qty - total)
        item.status = BatchStatus.DISCARDED if total > 0 else item.status
        self.repo.save_item(item)
        if self.kpi is not None and total > 0:
            self.kpi.track(
                device_id=device_id,
                event_name="inventory_discarded",
                properties={"item_id": item.item_id, "discarded_qty": str(total)},
            )
        return item

    def search(self, *, device_id: str, query: str, today: date) -> list[SearchResult]:
        q = query.strip().lower()
        q_normalized = normalize_ingredient_name(query).lower() if query.strip() else ""
        out: list[SearchResult] = []
        for item in self.repo.list_items_by_device(device_id):
            if q and q not in item.name.lower() and (q_normalized and q_normalized not in item.name.lower()):
                continue
            item.status = self._resolve_item_status(item.item_id, today)
            self.repo.save_item(item)
            has_alert = item.status in (BatchStatus.IMMINENT, BatchStatus.RISK)
            out.append(
                SearchResult(
                    item_id=item.item_id,
                    name=item.name,
                    status=item.status,
                    has_stock=item.total_qty > 0,
                    total_qty=item.total_qty,
                    has_imminent_or_risk=has_alert,
                )
            )
        if self.kpi is not None:
            self.kpi.track(
                device_id=device_id,
                event_name="search_used",
                properties={"query": query.strip()},
            )
        return out

    def list_priority_items(self, *, device_id: str, today: date) -> list[PriorityItem]:
        priority: list[PriorityItem] = []
        for item in self.repo.list_items_by_device(device_id):
            item.status = self._resolve_item_status(item.item_id, today)
            self.repo.save_item(item)
            if item.status not in (BatchStatus.IMMINENT, BatchStatus.RISK):
                continue
            if item.total_qty <= 0:
                continue
            priority.append(
                PriorityItem(
                    item_id=item.item_id,
                    name=item.name,
                    status=item.status,
                    total_qty=item.total_qty,
                )
            )
        return sorted(priority, key=lambda x: (0 if x.status == BatchStatus.RISK else 1, x.name))


class NotificationService:
    def __init__(
        self,
        repo: Repository,
        device_service: DeviceService,
        kpi: KPIService | None = None,
        push_sender: PushSender | None = None,
    ) -> None:
        self.repo = repo
        self.device_service = device_service
        self.kpi = kpi
        self.push_sender = push_sender or WebPushSender.from_env()

    def _notify_type_from_days_left(self, days_left: int) -> str:
        if days_left == 0:
            return "D-day"
        return f"D-{days_left}"

    def find_d3_candidates(self, *, today: date) -> list[NotificationCandidate]:
        candidates: list[NotificationCandidate] = []
        for item in self.repo.list_all_items():
            batches = [
                b
                for b in self.repo.list_batches_by_item(item.item_id)
                if b.qty > 0 and b.status not in (BatchStatus.CONSUMED, BatchStatus.DISCARDED)
            ]
            if not batches:
                continue

            earliest = min(batches, key=lambda x: x.expiry_date)
            days_left = (earliest.expiry_date - today).days
            current_status = (
                BatchStatus.RISK if days_left < 0 else BatchStatus.IMMINENT if days_left <= 3 else BatchStatus.OWNED
            )
            if earliest.status != current_status:
                earliest.status = current_status
                self.repo.save_batch(earliest)

            # 웹 푸시 대상은 "임박" 상태에 도달한 배치로 제한한다.
            if current_status != BatchStatus.IMMINENT:
                continue
            if days_left not in (3, 2, 1, 0):
                continue

            notify_type = self._notify_type_from_days_left(days_left)
            if self.repo.has_notification_log(item.device_id, earliest.batch_id, notify_type):
                continue

            candidates.append(
                NotificationCandidate(
                    device_id=item.device_id,
                    batch_id=earliest.batch_id,
                    item_id=item.item_id,
                    name=item.name,
                    expiry_date=earliest.expiry_date,
                    days_left=days_left,
                )
            )
        return candidates

    def mark_sent(self, *, device_id: str, batch_id: str, notify_type: str = "D-3") -> None:
        profile = self.device_service.get(device_id=device_id)
        channel = "in_app"
        delivery_status = "fallback_in_app"

        if profile.push_permission_state == PushPermissionState.GRANTED:
            subscription = self.device_service.get_push_subscription(device_id=device_id)
            if subscription is not None and self.push_sender is not None:
                pushed = self.push_sender.send(
                    subscription,
                    {
                        "title": f"유통기한 {notify_type} 알림",
                        "body": "유통기한 임박 식재료를 확인해 주세요.",
                        "notify_type": notify_type,
                        "batch_id": batch_id,
                    },
                )
                channel = "push"
                delivery_status = "sent" if pushed else "push_failed_fallback_in_app"
            else:
                channel = "in_app"
                delivery_status = "missing_subscription_fallback"

        self.repo.save_notification_log(
            NotificationLog(
                device_id=device_id,
                batch_id=batch_id,
                notify_type=notify_type,
                channel=channel,
                delivery_status=delivery_status,
                sent_at=self.repo.now(),
            )
        )
        if self.kpi is not None:
            self.kpi.track(
                device_id=device_id,
                event_name="notification_sent",
                properties={"notify_type": notify_type, "channel": channel},
            )

    def dispatch_d3(self, *, today: date) -> list[NotificationCandidate]:
        candidates = self.find_d3_candidates(today=today)
        for c in candidates:
            notify_type = self._notify_type_from_days_left(c.days_left)
            self.mark_sent(device_id=c.device_id, batch_id=c.batch_id, notify_type=notify_type)
        return candidates
