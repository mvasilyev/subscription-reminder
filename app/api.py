"""HTTP API для Mini App + раздача статики."""
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .auth import is_allowed, validate_init_data
from .billing import format_reminders
from .config import Config
from .db import Database
from .service import enrich, local_now, monthly_summary

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"

Reminders = Annotated[list[Annotated[int, Field(ge=0, le=90)]], Field(max_length=6)]


class CardIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    last4: str = Field(default="", pattern=r"^\d{0,4}$")
    color: str = Field(default="#3b82f6", pattern=r"^#[0-9a-fA-F]{6}$")


class SubIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    amount: float = Field(gt=0, lt=1e9)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    card_id: int | None = None
    anchor: date
    unit: Literal["day", "week", "month", "year"]
    every: int = Field(default=1, ge=1, le=365)
    reminders: Reminders | None = None
    note: str = Field(default="", max_length=200)
    active: bool = True


class SettingsIn(BaseModel):
    tz: str
    notify_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    default_reminders: Reminders

    @field_validator("tz")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("неизвестный часовой пояс")
        return v


def create_api(db: Database, cfg: Config) -> FastAPI:
    app = FastAPI(title="subscription-reminder", docs_url=None, redoc_url=None, openapi_url=None)

    async def current_user(authorization: str = Header(default="")) -> dict:
        init_data = authorization.removeprefix("tma ").strip()
        tg_user = validate_init_data(init_data, cfg.bot_token) if init_data else None
        if not tg_user:
            raise HTTPException(401, "invalid initData")
        name = " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])) or tg_user.get("username", "")
        user = await db.touch_user(int(tg_user["id"]), name)
        if not is_allowed(user, user["id"], cfg.admin_id):
            raise HTTPException(403, "access denied")
        return user

    User = Annotated[dict, Depends(current_user)]

    async def sub_payload(user: dict, body: SubIn) -> dict:
        if body.card_id is not None and not await db.get_card(user["id"], body.card_id):
            raise HTTPException(400, "card not found")
        data = body.model_dump()
        data["anchor"] = body.anchor.isoformat()
        data["reminders"] = format_reminders(body.reminders)
        data["currency"] = body.currency.upper()
        data["active"] = int(body.active)
        return data

    @app.get("/api/state")
    async def state(user: User) -> dict:
        today = local_now(user).date()
        subs = [enrich(s, user, today) for s in await db.list_subs(user["id"])]
        subs.sort(key=lambda s: (not s["active"], s["next_charge"]))
        return {
            "me": {
                "id": user["id"],
                "name": user["name"],
                "is_admin": user["id"] == cfg.admin_id,
                "tz": user["tz"],
                "notify_time": user["notify_time"],
                "default_reminders": [int(x) for x in user["default_reminders"].split(",") if x],
            },
            "today": today.isoformat(),
            "cards": await db.list_cards(user["id"]),
            "subs": subs,
            "monthly": monthly_summary(subs),
        }

    @app.put("/api/settings")
    async def put_settings(user: User, body: SettingsIn) -> dict:
        await db.update_settings(
            user["id"],
            {"tz": body.tz, "notify_time": body.notify_time, "default_reminders": format_reminders(body.default_reminders) or ""},
        )
        return {"ok": True}

    @app.post("/api/cards")
    async def create_card(user: User, body: CardIn) -> dict:
        return await db.create_card(user["id"], body.model_dump())

    @app.put("/api/cards/{card_id}")
    async def update_card(user: User, card_id: int, body: CardIn) -> dict:
        card = await db.update_card(user["id"], card_id, body.model_dump())
        if not card:
            raise HTTPException(404)
        return card

    @app.delete("/api/cards/{card_id}")
    async def delete_card(user: User, card_id: int) -> dict:
        if not await db.delete_card(user["id"], card_id):
            raise HTTPException(404)
        return {"ok": True}

    @app.post("/api/subs")
    async def create_sub(user: User, body: SubIn) -> dict:
        return await db.create_sub(user["id"], await sub_payload(user, body))

    @app.put("/api/subs/{sub_id}")
    async def update_sub(user: User, sub_id: int, body: SubIn) -> dict:
        sub = await db.update_sub(user["id"], sub_id, await sub_payload(user, body))
        if not sub:
            raise HTTPException(404)
        return sub

    @app.delete("/api/subs/{sub_id}")
    async def delete_sub(user: User, sub_id: int) -> dict:
        if not await db.delete_sub(user["id"], sub_id):
            raise HTTPException(404)
        return {"ok": True}

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    if WEBAPP_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
    return app
