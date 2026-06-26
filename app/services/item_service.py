from itertools import count

from app.schemas.item import ItemCreate, ItemRead


class ItemService:
    """In-memory item store. Swap for a real repository/DB layer later."""

    def __init__(self) -> None:
        self._items: dict[int, ItemRead] = {}
        self._ids = count(1)

    def list_items(self) -> list[ItemRead]:
        return list(self._items.values())

    def get_item(self, item_id: int) -> ItemRead | None:
        return self._items.get(item_id)

    def create_item(self, payload: ItemCreate) -> ItemRead:
        item = ItemRead(id=next(self._ids), **payload.model_dump())
        self._items[item.id] = item
        return item


_service = ItemService()


def get_item_service() -> ItemService:
    return _service
