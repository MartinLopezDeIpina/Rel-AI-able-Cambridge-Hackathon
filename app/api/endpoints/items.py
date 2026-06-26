from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.item import ItemCreate, ItemRead
from app.services.item_service import ItemService, get_item_service

router = APIRouter()


@router.get("", response_model=list[ItemRead])
async def list_items(service: ItemService = Depends(get_item_service)) -> list[ItemRead]:
    return service.list_items()


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: ItemCreate, service: ItemService = Depends(get_item_service)
) -> ItemRead:
    return service.create_item(payload)


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(
    item_id: int, service: ItemService = Depends(get_item_service)
) -> ItemRead:
    item = service.get_item(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )
    return item
