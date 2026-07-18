from datetime import date

from app.models import BatchStatus, StorageType
from app.repository import InMemoryRepository
from app.services import InventoryService


def test_register_merges_when_identity_matches() -> None:
    repo = InMemoryRepository()
    svc = InventoryService(repo)

    first = svc.register_item(
        device_id="device-a",
        name="우유",
        expiry_date=date(2026, 7, 20),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )
    second = svc.register_item(
        device_id="device-a",
        name="우유",
        expiry_date=date(2026, 7, 18),
        storage_type=StorageType.FRIDGE,
        qty=2,
        today=date(2026, 7, 11),
    )

    assert first.item_id == second.item_id
    assert second.total_qty == 3


def test_register_separates_when_storage_type_differs() -> None:
    repo = InMemoryRepository()
    svc = InventoryService(repo)

    first = svc.register_item(
        device_id="device-a",
        name="계란",
        expiry_date=date(2026, 7, 20),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )
    second = svc.register_item(
        device_id="device-a",
        name="계란",
        expiry_date=date(2026, 7, 21),
        storage_type=StorageType.ROOM,
        qty=1,
        today=date(2026, 7, 11),
    )

    assert first.item_id != second.item_id


def test_status_moves_to_imminent_and_risk() -> None:
    repo = InMemoryRepository()
    svc = InventoryService(repo)

    item = svc.register_item(
        device_id="device-a",
        name="두부",
        expiry_date=date(2026, 7, 14),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )
    assert item.status == BatchStatus.IMMINENT

    view = svc.get_item_view(device_id="device-a", item_id=item.item_id, today=date(2026, 7, 15))
    assert view is not None
    item_after, _ = view
    assert item_after.status == BatchStatus.RISK


def test_reduce_and_discard() -> None:
    repo = InMemoryRepository()
    svc = InventoryService(repo)

    item = svc.register_item(
        device_id="device-a",
        name="요거트",
        expiry_date=date(2026, 7, 18),
        storage_type=StorageType.FRIDGE,
        qty=3,
        today=date(2026, 7, 11),
    )

    reduced = svc.reduce_quantity(device_id="device-a", item_id=item.item_id, amount=1, today=date(2026, 7, 11))
    assert reduced is not None
    assert reduced.total_qty == 2

    discarded = svc.discard_item(device_id="device-a", item_id=item.item_id, today=date(2026, 7, 11))
    assert discarded is not None
    assert discarded.total_qty == 0
    assert discarded.status == BatchStatus.DISCARDED


def test_register_normalizes_ingredient_name_for_merge() -> None:
    repo = InMemoryRepository()
    svc = InventoryService(repo)

    first = svc.register_item(
        device_id="device-a",
        name="제주두부",
        expiry_date=date(2026, 7, 20),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )
    second = svc.register_item(
        device_id="device-a",
        name="국산 두부",
        expiry_date=date(2026, 7, 21),
        storage_type=StorageType.FRIDGE,
        qty=2,
        today=date(2026, 7, 11),
    )

    assert first.item_id == second.item_id
    assert second.name == "두부"
    assert second.total_qty == 3


def test_search_matches_variant_query_after_normalization() -> None:
    repo = InMemoryRepository()
    svc = InventoryService(repo)

    svc.register_item(
        device_id="device-a",
        name="제주두부",
        expiry_date=date(2026, 7, 20),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )

    result = svc.search(device_id="device-a", query="국산 제주두부", today=date(2026, 7, 11))
    assert len(result) == 1
    assert result[0].name == "두부"


def test_register_maps_jjigae_tofu_to_canonical_tofu() -> None:
    repo = InMemoryRepository()
    svc = InventoryService(repo)

    item = svc.register_item(
        device_id="device-a",
        name="찌개두부",
        expiry_date=date(2026, 7, 20),
        storage_type=StorageType.FRIDGE,
        qty=1,
        today=date(2026, 7, 11),
    )

    assert item.name == "두부"
