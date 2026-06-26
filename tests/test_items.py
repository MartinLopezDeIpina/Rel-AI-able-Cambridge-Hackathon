from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_and_get_item() -> None:
    resp = client.post("/api/items", json={"name": "widget"})
    assert resp.status_code == 201
    item = resp.json()
    assert item["name"] == "widget"
    assert "id" in item

    resp = client.get(f"/api/items/{item['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "widget"


def test_get_missing_item() -> None:
    resp = client.get("/api/items/999999")
    assert resp.status_code == 404
