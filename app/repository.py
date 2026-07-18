from __future__ import annotations

import os
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Dict, Iterable, Optional, Protocol

from app.models import (
    BatchStatus,
    DeviceProfile,
    InventoryBatch,
    InventoryItem,
    KPIEvent,
    NotificationLog,
    PushSubscription,
    PushPermissionState,
    StorageType,
)


class Repository(Protocol):
    def save_device(self, device: DeviceProfile) -> None: ...

    def get_device(self, device_id: str) -> Optional[DeviceProfile]: ...

    def save_item(self, item: InventoryItem) -> None: ...

    def get_item(self, item_id: str) -> Optional[InventoryItem]: ...

    def list_items_by_device(self, device_id: str) -> list[InventoryItem]: ...

    def list_all_items(self) -> list[InventoryItem]: ...

    def save_batch(self, batch: InventoryBatch) -> None: ...

    def get_batch(self, batch_id: str) -> Optional[InventoryBatch]: ...

    def list_batches_by_item(self, item_id: str) -> list[InventoryBatch]: ...

    def list_batches_by_device(self, device_id: str) -> list[InventoryBatch]: ...

    def save_notification_log(self, log: NotificationLog) -> None: ...

    def has_notification_log(self, device_id: str, batch_id: str, notify_type: str) -> bool: ...

    def now(self) -> datetime: ...

    def save_kpi_event(self, event: KPIEvent) -> None: ...

    def list_kpi_events(self, device_id: str) -> list[KPIEvent]: ...

    def save_push_subscription(self, subscription: PushSubscription) -> None: ...

    def get_push_subscription(self, device_id: str) -> Optional[PushSubscription]: ...

    def delete_push_subscription(self, device_id: str) -> None: ...

    def clear_all(self) -> None: ...


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self.devices: Dict[str, DeviceProfile] = {}
        self.items: Dict[str, InventoryItem] = {}
        self.batches: Dict[str, InventoryBatch] = {}
        self.item_batches: dict[str, set[str]] = defaultdict(set)
        self.notification_logs: dict[tuple[str, str, str], NotificationLog] = {}
        self.kpi_events: dict[str, KPIEvent] = {}
        self.push_subscriptions: Dict[str, PushSubscription] = {}

    def save_device(self, device: DeviceProfile) -> None:
        self.devices[device.device_id] = device

    def get_device(self, device_id: str) -> Optional[DeviceProfile]:
        return self.devices.get(device_id)

    def save_item(self, item: InventoryItem) -> None:
        self.items[item.item_id] = item

    def get_item(self, item_id: str) -> Optional[InventoryItem]:
        return self.items.get(item_id)

    def list_items_by_device(self, device_id: str) -> list[InventoryItem]:
        return [i for i in self.items.values() if i.device_id == device_id]

    def list_all_items(self) -> list[InventoryItem]:
        return list(self.items.values())

    def save_batch(self, batch: InventoryBatch) -> None:
        self.batches[batch.batch_id] = batch
        self.item_batches[batch.item_id].add(batch.batch_id)

    def get_batch(self, batch_id: str) -> Optional[InventoryBatch]:
        return self.batches.get(batch_id)

    def list_batches_by_item(self, item_id: str) -> list[InventoryBatch]:
        ids = self.item_batches.get(item_id, set())
        return [self.batches[i] for i in ids]

    def list_batches_by_device(self, device_id: str) -> list[InventoryBatch]:
        return [b for b in self.batches.values() if b.device_id == device_id]

    def save_notification_log(self, log: NotificationLog) -> None:
        key = (log.device_id, log.batch_id, log.notify_type)
        self.notification_logs[key] = log

    def has_notification_log(self, device_id: str, batch_id: str, notify_type: str) -> bool:
        return (device_id, batch_id, notify_type) in self.notification_logs

    def now(self) -> datetime:
        return datetime.now(UTC)

    def save_kpi_event(self, event: KPIEvent) -> None:
        self.kpi_events[event.event_id] = event

    def list_kpi_events(self, device_id: str) -> list[KPIEvent]:
        return [e for e in self.kpi_events.values() if e.device_id == device_id]

    def save_push_subscription(self, subscription: PushSubscription) -> None:
        self.push_subscriptions[subscription.device_id] = subscription

    def get_push_subscription(self, device_id: str) -> Optional[PushSubscription]:
        return self.push_subscriptions.get(device_id)

    def delete_push_subscription(self, device_id: str) -> None:
        self.push_subscriptions.pop(device_id, None)

    def clear_all(self) -> None:
        self.devices.clear()
        self.items.clear()
        self.batches.clear()
        self.item_batches.clear()
        self.notification_logs.clear()
        self.kpi_events.clear()
        self.push_subscriptions.clear()


def _device_to_entity(device: DeviceProfile) -> dict:
    return {
        "PartitionKey": device.device_id,
        "RowKey": "profile",
        "push_permission_state": device.push_permission_state.value,
        "created_at": device.created_at.isoformat(),
        "last_active_at": device.last_active_at.isoformat(),
    }


def _entity_to_device(entity: dict) -> DeviceProfile:
    return DeviceProfile(
        device_id=entity["PartitionKey"],
        push_permission_state=PushPermissionState(entity.get("push_permission_state", PushPermissionState.DEFAULT.value)),
        created_at=datetime.fromisoformat(entity["created_at"]),
        last_active_at=datetime.fromisoformat(entity["last_active_at"]),
    )


def _quote(value: str) -> str:
    return value.replace("'", "''")


def _item_to_entity(item: InventoryItem) -> dict:
    return {
        "PartitionKey": item.device_id,
        "RowKey": item.item_id,
        "name": item.name,
        "storage_type": item.storage_type.value,
        "total_qty": item.total_qty,
        "status": item.status.value,
        "updated_at": item.updated_at.isoformat(),
    }


def _entity_to_item(entity: dict) -> InventoryItem:
    return InventoryItem(
        device_id=entity["PartitionKey"],
        item_id=entity["RowKey"],
        name=entity["name"],
        storage_type=StorageType(entity["storage_type"]),
        total_qty=int(entity.get("total_qty", 0)),
        status=BatchStatus(entity["status"]),
        updated_at=datetime.fromisoformat(entity["updated_at"]),
    )


def _batch_to_entity(batch: InventoryBatch) -> dict:
    return {
        "PartitionKey": batch.item_id,
        "RowKey": batch.batch_id,
        "device_id": batch.device_id,
        "expiry_date": batch.expiry_date.isoformat(),
        "qty": batch.qty,
        "status": batch.status.value,
    }


def _entity_to_batch(entity: dict) -> InventoryBatch:
    return InventoryBatch(
        device_id=entity["device_id"],
        item_id=entity["PartitionKey"],
        batch_id=entity["RowKey"],
        expiry_date=date.fromisoformat(entity["expiry_date"]),
        qty=int(entity.get("qty", 0)),
        status=BatchStatus(entity["status"]),
    )


def _log_to_entity(log: NotificationLog) -> dict:
    return {
        "PartitionKey": log.device_id,
        "RowKey": f"{log.batch_id}_{log.notify_type}",
        "batch_id": log.batch_id,
        "notify_type": log.notify_type,
        "channel": log.channel,
        "delivery_status": log.delivery_status,
        "sent_at": log.sent_at.isoformat(),
    }


def _kpi_to_entity(event: KPIEvent) -> dict:
    entity: dict[str, object] = {
        "PartitionKey": event.device_id,
        "RowKey": event.event_id,
        "event_name": event.event_name,
        "occurred_at": event.occurred_at.isoformat(),
    }
    for key, value in event.properties.items():
        entity[f"prop_{key}"] = value
    return entity


def _entity_to_kpi(entity: dict) -> KPIEvent:
    props = {
        str(k)[5:]: str(v)
        for k, v in entity.items()
        if isinstance(k, str) and k.startswith("prop_")
    }
    return KPIEvent(
        device_id=entity["PartitionKey"],
        event_id=entity["RowKey"],
        event_name=entity["event_name"],
        occurred_at=datetime.fromisoformat(entity["occurred_at"]),
        properties=props,
    )


def _subscription_to_entity(subscription: PushSubscription) -> dict:
    return {
        "PartitionKey": subscription.device_id,
        "RowKey": "subscription",
        "endpoint": subscription.endpoint,
        "p256dh": subscription.p256dh,
        "auth": subscription.auth,
        "created_at": subscription.created_at.isoformat(),
        "updated_at": subscription.updated_at.isoformat(),
    }


def _entity_to_subscription(entity: dict) -> PushSubscription:
    return PushSubscription(
        device_id=entity["PartitionKey"],
        endpoint=entity["endpoint"],
        p256dh=entity["p256dh"],
        auth=entity["auth"],
        created_at=datetime.fromisoformat(entity["created_at"]),
        updated_at=datetime.fromisoformat(entity["updated_at"]),
    )


class AzureTableRepository(Repository):
    def __init__(self, *, connection_string: str, table_prefix: str = "Fridge") -> None:
        from azure.core.exceptions import ResourceNotFoundError
        from azure.data.tables import TableServiceClient
        from azure.data.tables import UpdateMode

        self.service = TableServiceClient.from_connection_string(connection_string)
        self._resource_not_found_error = ResourceNotFoundError
        self._update_mode = UpdateMode
        self.item_table_name = f"{table_prefix}InventoryItem"
        self.batch_table_name = f"{table_prefix}InventoryBatch"
        self.log_table_name = f"{table_prefix}NotificationLog"
        self.device_table_name = f"{table_prefix}Device"
        self.kpi_table_name = f"{table_prefix}KPIEvent"
        self.subscription_table_name = f"{table_prefix}PushSubscription"

        self.service.create_table_if_not_exists(self.device_table_name)
        self.service.create_table_if_not_exists(self.item_table_name)
        self.service.create_table_if_not_exists(self.batch_table_name)
        self.service.create_table_if_not_exists(self.log_table_name)
        self.service.create_table_if_not_exists(self.kpi_table_name)
        self.service.create_table_if_not_exists(self.subscription_table_name)

        self.device_table = self.service.get_table_client(self.device_table_name)
        self.item_table = self.service.get_table_client(self.item_table_name)
        self.batch_table = self.service.get_table_client(self.batch_table_name)
        self.log_table = self.service.get_table_client(self.log_table_name)
        self.kpi_table = self.service.get_table_client(self.kpi_table_name)
        self.subscription_table = self.service.get_table_client(self.subscription_table_name)

    def save_device(self, device: DeviceProfile) -> None:
        self.device_table.upsert_entity(_device_to_entity(device), mode=self._update_mode.REPLACE)

    def get_device(self, device_id: str) -> Optional[DeviceProfile]:
        try:
            entity = self.device_table.get_entity(partition_key=device_id, row_key="profile")
            return _entity_to_device(entity)
        except self._resource_not_found_error:
            return None

    def save_item(self, item: InventoryItem) -> None:
        self.item_table.upsert_entity(_item_to_entity(item), mode=self._update_mode.REPLACE)

    def get_item(self, item_id: str) -> Optional[InventoryItem]:
        query = f"RowKey eq '{_quote(item_id)}'"
        entities = list(self.item_table.query_entities(query_filter=query, results_per_page=1))
        if not entities:
            return None
        return _entity_to_item(entities[0])

    def list_items_by_device(self, device_id: str) -> list[InventoryItem]:
        query = f"PartitionKey eq '{_quote(device_id)}'"
        return [_entity_to_item(e) for e in self.item_table.query_entities(query_filter=query)]

    def list_all_items(self) -> list[InventoryItem]:
        return [_entity_to_item(e) for e in self.item_table.list_entities()]

    def save_batch(self, batch: InventoryBatch) -> None:
        self.batch_table.upsert_entity(_batch_to_entity(batch), mode=self._update_mode.REPLACE)

    def get_batch(self, batch_id: str) -> Optional[InventoryBatch]:
        query = f"RowKey eq '{_quote(batch_id)}'"
        entities = list(self.batch_table.query_entities(query_filter=query, results_per_page=1))
        if not entities:
            return None
        return _entity_to_batch(entities[0])

    def list_batches_by_item(self, item_id: str) -> list[InventoryBatch]:
        query = f"PartitionKey eq '{_quote(item_id)}'"
        return [_entity_to_batch(e) for e in self.batch_table.query_entities(query_filter=query)]

    def list_batches_by_device(self, device_id: str) -> list[InventoryBatch]:
        query = f"device_id eq '{_quote(device_id)}'"
        return [_entity_to_batch(e) for e in self.batch_table.query_entities(query_filter=query)]

    def save_notification_log(self, log: NotificationLog) -> None:
        self.log_table.upsert_entity(_log_to_entity(log), mode=self._update_mode.REPLACE)

    def has_notification_log(self, device_id: str, batch_id: str, notify_type: str) -> bool:
        row_key = f"{batch_id}_{notify_type}"
        try:
            self.log_table.get_entity(partition_key=device_id, row_key=row_key)
            return True
        except self._resource_not_found_error:
            return False

    def now(self) -> datetime:
        return datetime.now(UTC)

    def save_kpi_event(self, event: KPIEvent) -> None:
        self.kpi_table.upsert_entity(_kpi_to_entity(event), mode=self._update_mode.REPLACE)

    def list_kpi_events(self, device_id: str) -> list[KPIEvent]:
        query = f"PartitionKey eq '{_quote(device_id)}'"
        return [_entity_to_kpi(e) for e in self.kpi_table.query_entities(query_filter=query)]

    def save_push_subscription(self, subscription: PushSubscription) -> None:
        self.subscription_table.upsert_entity(_subscription_to_entity(subscription), mode=self._update_mode.REPLACE)

    def get_push_subscription(self, device_id: str) -> Optional[PushSubscription]:
        try:
            entity = self.subscription_table.get_entity(partition_key=device_id, row_key="subscription")
            return _entity_to_subscription(entity)
        except self._resource_not_found_error:
            return None

    def delete_push_subscription(self, device_id: str) -> None:
        try:
            self.subscription_table.delete_entity(partition_key=device_id, row_key="subscription")
        except self._resource_not_found_error:
            pass

    def clear_all(self) -> None:
        for table in (
            self.device_table,
            self.item_table,
            self.batch_table,
            self.log_table,
            self.kpi_table,
            self.subscription_table,
        ):
            entities = list(table.list_entities())
            for entity in entities:
                table.delete_entity(partition_key=entity["PartitionKey"], row_key=entity["RowKey"])


def create_repository() -> Repository:
    kind = os.getenv("REPOSITORY_KIND", "azure").lower()
    if kind == "inmemory":
        return InMemoryRepository()

    connection_string = os.getenv("AZURE_TABLES_CONNECTION_STRING", "").strip()
    if not connection_string:
        raise RuntimeError(
            "AZURE_TABLES_CONNECTION_STRING is required when REPOSITORY_KIND is 'azure'. "
            "Set REPOSITORY_KIND=inmemory only for local tests."
        )

    table_prefix = os.getenv("AZURE_TABLES_PREFIX", "Fridge")
    return AzureTableRepository(connection_string=connection_string, table_prefix=table_prefix)


def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def canonical_item_key(name: str, storage_type: str) -> str:
    return "|".join([normalize_text(name), storage_type])


def find_same_item(
    items: Iterable[InventoryItem],
    name: str,
    storage_type: str,
) -> Optional[InventoryItem]:
    target = canonical_item_key(name, storage_type)

    for item in items:
        current = canonical_item_key(item.name, item.storage_type.value)
        if current == target:
            return item
    return None
