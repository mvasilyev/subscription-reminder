import pytest
from fastapi.testclient import TestClient

from app.api import create_api
from app.config import Config
from app.db import Database
from tests.test_auth import TOKEN, make

ADMIN, FRIEND, STRANGER = 1, 2, 3


@pytest.fixture
async def client():
    cfg = Config(TOKEN, ADMIN, "", ":memory:", "Europe/Moscow", "127.0.0.1", 0)
    db = Database(":memory:", cfg.default_tz)
    await db.connect()
    await db.set_allowed(FRIEND, True)
    yield TestClient(create_api(db, cfg)), db
    await db.close()


def h(uid):
    return {"Authorization": "tma " + make(uid)}


SUB = {"name": "Netflix", "amount": 9.99, "currency": "USD", "anchor": "2026-10-20", "unit": "month"}


async def test_access(client):
    c, _ = client
    assert c.get("/api/state").status_code == 401
    assert c.get("/api/state", headers=h(STRANGER)).status_code == 403
    assert c.get("/api/state", headers=h(ADMIN)).json()["me"]["is_admin"] is True
    assert c.get("/api/state", headers=h(FRIEND)).json()["me"]["is_admin"] is False


async def test_isolation(client):
    c, _ = client
    card = c.post("/api/cards", headers=h(ADMIN), json={"name": "Tinkoff", "last4": "1234"}).json()
    sub = c.post("/api/subs", headers=h(ADMIN), json={**SUB, "card_id": card["id"]}).json()
    assert c.get("/api/state", headers=h(FRIEND)).json()["subs"] == []
    # чужую карту не привязать, чужое не изменить и не удалить
    assert c.post("/api/subs", headers=h(FRIEND), json={**SUB, "card_id": card["id"]}).status_code == 400
    assert c.put(f"/api/subs/{sub['id']}", headers=h(FRIEND), json=SUB).status_code == 404
    assert c.delete(f"/api/cards/{card['id']}", headers=h(FRIEND)).status_code == 404
    assert len(c.get("/api/state", headers=h(ADMIN)).json()["subs"]) == 1


async def test_crud_and_summary(client):
    c, _ = client
    c.post("/api/subs", headers=h(ADMIN), json=SUB)
    c.post("/api/subs", headers=h(ADMIN), json={**SUB, "name": "Yandex", "amount": 2400, "currency": "RUB", "unit": "year", "reminders": [7, 1]})
    st = c.get("/api/state", headers=h(ADMIN)).json()
    assert st["monthly"] == {"RUB": 200.0, "USD": 9.99}
    yandex = next(s for s in st["subs"] if s["name"] == "Yandex")
    assert yandex["reminders"] == [7, 1]
    assert c.put("/api/settings", headers=h(ADMIN), json={"tz": "Asia/Almaty", "notify_time": "09:30", "default_reminders": [2]}).status_code == 200
    assert c.put("/api/settings", headers=h(ADMIN), json={"tz": "Mars/Base", "notify_time": "09:30", "default_reminders": []}).status_code == 422
    me = c.get("/api/state", headers=h(ADMIN)).json()["me"]
    assert (me["tz"], me["notify_time"], me["default_reminders"]) == ("Asia/Almaty", "09:30", [2])


async def test_delete_card_keeps_sub(client):
    c, _ = client
    card = c.post("/api/cards", headers=h(ADMIN), json={"name": "Alfa"}).json()
    c.post("/api/subs", headers=h(ADMIN), json={**SUB, "card_id": card["id"]})
    c.delete(f"/api/cards/{card['id']}", headers=h(ADMIN))
    assert c.get("/api/state", headers=h(ADMIN)).json()["subs"][0]["card_id"] is None
