from datetime import date

from app.models import PushPermissionState, StorageType
from app.repository import InMemoryRepository
from app.services import DeviceService, InventoryService, KPIService, NotificationService, PushSender


class FakePushSender(PushSender):
    def __init__(self, should_succeed: bool = True) -> None:
        self.should_succeed = should_succeed

    def send(self, subscription, payload):
        return self.should_succeed


def test_d3_notification_uses_earliest_batch_and_dedupes() -> None:
    repo = InMemoryRepository()
    kpi = KPIService(repo)
    device = DeviceService(repo)
    inv = InventoryService(repo, kpi=kpi)
    noti = NotificationService(repo, device_service=device, kpi=kpi)

    item = inv.register_item(
        device_id="device-a",
        name="토마토",
        expiry_date=date(2026, 7, 14),
        storage_type=StorageType.ROOM,
        qty=1,
        today=date(2026, 7, 11),
    )
    inv.register_item(
        device_id="device-a",
        name="토마토",
        expiry_date=date(2026, 7, 20),
        storage_type=StorageType.ROOM,
        qty=1,
        today=date(2026, 7, 11),
    )

    cands = noti.find_d3_candidates(today=date(2026, 7, 11))
    assert len(cands) == 1
    assert cands[0].item_id == item.item_id

    noti.mark_sent(device_id=cands[0].device_id, batch_id=cands[0].batch_id)
    cands_after = noti.find_d3_candidates(today=date(2026, 7, 11))
    assert len(cands_after) == 0


def test_notification_falls_back_to_in_app_when_push_not_granted() -> None:
    repo = InMemoryRepository()
    kpi = KPIService(repo)
    device = DeviceService(repo)
    inv = InventoryService(repo, kpi=kpi)
    noti = NotificationService(repo, device_service=device, kpi=kpi)

    inv.register_item(
        device_id="device-b",
        name="상추",
        expiry_date=date(2026, 7, 14),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )

    out = noti.dispatch_d3(today=date(2026, 7, 11))
    assert len(out) == 1

    log = repo.notification_logs[("device-b", out[0].batch_id, "D-3")]
    assert log.channel == "in_app"
    assert log.delivery_status == "fallback_in_app"


def test_notification_uses_push_when_permission_granted_and_subscription_exists() -> None:
    repo = InMemoryRepository()
    kpi = KPIService(repo)
    device = DeviceService(repo)
    inv = InventoryService(repo, kpi=kpi)
    noti = NotificationService(repo, device_service=device, kpi=kpi, push_sender=FakePushSender())

    device.update_push_permission(device_id="device-c", state=PushPermissionState.GRANTED)
    device.upsert_push_subscription(
        device_id="device-c",
        endpoint="https://push.example/sub-c",
        p256dh="p256dh",
        auth="auth",
    )
    inv.register_item(
        device_id="device-c",
        name="우엉",
        expiry_date=date(2026, 7, 14),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )

    out = noti.dispatch_d3(today=date(2026, 7, 11))
    assert len(out) == 1

    log = repo.notification_logs[("device-c", out[0].batch_id, "D-3")]
    assert log.channel == "push"
    assert log.delivery_status == "sent"


def test_d3_notification_skips_expired_batches() -> None:
    repo = InMemoryRepository()
    kpi = KPIService(repo)
    device = DeviceService(repo)
    inv = InventoryService(repo, kpi=kpi)
    noti = NotificationService(repo, device_service=device, kpi=kpi, push_sender=FakePushSender())

    device.update_push_permission(device_id="device-d", state=PushPermissionState.GRANTED)
    device.upsert_push_subscription(
        device_id="device-d",
        endpoint="https://push.example/sub-d",
        p256dh="p256dh",
        auth="auth",
    )
    inv.register_item(
        device_id="device-d",
        name="양배추",
        expiry_date=date(2026, 7, 10),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )

    out = noti.dispatch_d3(today=date(2026, 7, 11))
    assert out == []


def test_notification_sends_on_d2_d1_and_dday() -> None:
    repo = InMemoryRepository()
    kpi = KPIService(repo)
    device = DeviceService(repo)
    inv = InventoryService(repo, kpi=kpi)
    noti = NotificationService(repo, device_service=device, kpi=kpi, push_sender=FakePushSender())

    device.update_push_permission(device_id="device-e", state=PushPermissionState.GRANTED)
    device.upsert_push_subscription(
        device_id="device-e",
        endpoint="https://push.example/sub-e",
        p256dh="p256dh",
        auth="auth",
    )
    inv.register_item(
        device_id="device-e",
        name="시금치",
        expiry_date=date(2026, 7, 14),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )

    out_d2 = noti.dispatch_d3(today=date(2026, 7, 12))
    assert len(out_d2) == 1
    assert repo.notification_logs[("device-e", out_d2[0].batch_id, "D-2")].delivery_status == "sent"

    out_d1 = noti.dispatch_d3(today=date(2026, 7, 13))
    assert len(out_d1) == 1
    assert repo.notification_logs[("device-e", out_d1[0].batch_id, "D-1")].delivery_status == "sent"

    out_dday = noti.dispatch_d3(today=date(2026, 7, 14))
    assert len(out_dday) == 1
    assert repo.notification_logs[("device-e", out_dday[0].batch_id, "D-day")].delivery_status == "sent"

    out_dday_again = noti.dispatch_d3(today=date(2026, 7, 14))
    assert out_dday_again == []
