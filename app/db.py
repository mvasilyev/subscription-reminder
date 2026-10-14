"""SQLite-хранилище. Все запросы к картам и подпискам фильтруются по user_id —
данные одного пользователя другому недоступны."""
import os
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL DEFAULT '',
    allowed           INTEGER NOT NULL DEFAULT 0,
    tz                TEXT NOT NULL,
    notify_time       TEXT NOT NULL DEFAULT '10:00',
    default_reminders TEXT NOT NULL DEFAULT '3,1',
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cards (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name    TEXT NOT NULL,
    last4   TEXT NOT NULL DEFAULT '',
    color   TEXT NOT NULL DEFAULT '#3b82f6'
);
CREATE TABLE IF NOT EXISTS subs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    amount    REAL NOT NULL,
    currency  TEXT NOT NULL,
    card_id   INTEGER REFERENCES cards(id) ON DELETE SET NULL,
    anchor    TEXT NOT NULL,
    unit      TEXT NOT NULL,
    every     INTEGER NOT NULL DEFAULT 1,
    reminders TEXT,
    note      TEXT NOT NULL DEFAULT '',
    active    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS subs_user ON subs(user_id);
CREATE INDEX IF NOT EXISTS cards_user ON cards(user_id);
CREATE TABLE IF NOT EXISTS sent (
    sub_id      INTEGER NOT NULL REFERENCES subs(id) ON DELETE CASCADE,
    charge_date TEXT NOT NULL,
    days_before INTEGER NOT NULL,
    PRIMARY KEY (sub_id, charge_date, days_before)
);
"""

CARD_FIELDS = ("name", "last4", "color")
SUB_FIELDS = ("name", "amount", "currency", "card_id", "anchor", "unit", "every", "reminders", "note", "active")
SETTINGS_FIELDS = ("tz", "notify_time", "default_reminders")


class Database:
    def __init__(self, path: str, default_tz: str):
        self.path = path
        self.default_tz = default_tz
        self.conn: aiosqlite.Connection = None  # type: ignore[assignment]  # задаётся в connect()

    async def connect(self) -> None:
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.execute("PRAGMA journal_mode = WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def _one(self, sql: str, *args: Any) -> dict | None:
        async with self.conn.execute(sql, args) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def _all(self, sql: str, *args: Any) -> list[dict]:
        async with self.conn.execute(sql, args) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def _exec(self, sql: str, *args: Any) -> int:
        cur = await self.conn.execute(sql, args)
        await self.conn.commit()
        return cur.rowcount

    async def _insert(self, sql: str, *args: Any) -> int:
        cur = await self.conn.execute(sql, args)
        await self.conn.commit()
        return cur.lastrowid

    # --- users / доступ ---

    async def get_user(self, user_id: int) -> dict | None:
        return await self._one("SELECT * FROM users WHERE id = ?", user_id)

    async def touch_user(self, user_id: int, name: str) -> dict:
        await self.conn.execute(
            "INSERT INTO users (id, name, tz) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
            (user_id, name, self.default_tz),
        )
        await self.conn.commit()
        return await self.get_user(user_id)

    async def set_allowed(self, user_id: int, allowed: bool) -> None:
        await self.conn.execute(
            "INSERT INTO users (id, tz, allowed) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET allowed = excluded.allowed",
            (user_id, self.default_tz, int(allowed)),
        )
        await self.conn.commit()

    async def list_users(self) -> list[dict]:
        return await self._all("SELECT * FROM users ORDER BY allowed DESC, id")

    async def allowed_users(self, admin_id: int) -> list[dict]:
        return await self._all("SELECT * FROM users WHERE allowed = 1 OR id = ?", admin_id)

    async def update_settings(self, user_id: int, data: dict) -> dict:
        fields = {k: v for k, v in data.items() if k in SETTINGS_FIELDS}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            await self._exec(f"UPDATE users SET {sets} WHERE id = ?", *fields.values(), user_id)
        return await self.get_user(user_id)

    # --- cards ---

    async def list_cards(self, user_id: int) -> list[dict]:
        return await self._all("SELECT * FROM cards WHERE user_id = ? ORDER BY name", user_id)

    async def get_card(self, user_id: int, card_id: int) -> dict | None:
        return await self._one("SELECT * FROM cards WHERE id = ? AND user_id = ?", card_id, user_id)

    async def create_card(self, user_id: int, data: dict) -> dict:
        vals = [data[k] for k in CARD_FIELDS]
        card_id = await self._insert(
            f"INSERT INTO cards (user_id, {', '.join(CARD_FIELDS)}) VALUES (?, ?, ?, ?)", user_id, *vals
        )
        return await self.get_card(user_id, card_id)

    async def update_card(self, user_id: int, card_id: int, data: dict) -> dict | None:
        sets = ", ".join(f"{k} = ?" for k in CARD_FIELDS)
        await self._exec(
            f"UPDATE cards SET {sets} WHERE id = ? AND user_id = ?", *[data[k] for k in CARD_FIELDS], card_id, user_id
        )
        return await self.get_card(user_id, card_id)

    async def delete_card(self, user_id: int, card_id: int) -> bool:
        return await self._exec("DELETE FROM cards WHERE id = ? AND user_id = ?", card_id, user_id) > 0

    # --- subs ---

    async def list_subs(self, user_id: int) -> list[dict]:
        return await self._all("SELECT * FROM subs WHERE user_id = ? ORDER BY name", user_id)

    async def get_sub(self, user_id: int, sub_id: int) -> dict | None:
        return await self._one("SELECT * FROM subs WHERE id = ? AND user_id = ?", sub_id, user_id)

    async def create_sub(self, user_id: int, data: dict) -> dict:
        placeholders = ", ".join("?" for _ in SUB_FIELDS)
        sub_id = await self._insert(
            f"INSERT INTO subs (user_id, {', '.join(SUB_FIELDS)}) VALUES (?, {placeholders})",
            user_id,
            *[data[k] for k in SUB_FIELDS],
        )
        return await self.get_sub(user_id, sub_id)

    async def update_sub(self, user_id: int, sub_id: int, data: dict) -> dict | None:
        sets = ", ".join(f"{k} = ?" for k in SUB_FIELDS)
        await self._exec(
            f"UPDATE subs SET {sets} WHERE id = ? AND user_id = ?", *[data[k] for k in SUB_FIELDS], sub_id, user_id
        )
        return await self.get_sub(user_id, sub_id)

    async def delete_sub(self, user_id: int, sub_id: int) -> bool:
        return await self._exec("DELETE FROM subs WHERE id = ? AND user_id = ?", sub_id, user_id) > 0

    # --- журнал отправленных напоминаний ---

    async def mark_sent(self, sub_id: int, charge_date: str, days_before: int) -> bool:
        """True, если напоминание ещё не отправлялось (и теперь помечено)."""
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO sent (sub_id, charge_date, days_before) VALUES (?, ?, ?)",
            (sub_id, charge_date, days_before),
        )
        await self.conn.commit()
        return cur.rowcount == 1

    async def unmark_sent(self, sub_id: int, charge_date: str, days_before: int) -> None:
        await self._exec(
            "DELETE FROM sent WHERE sub_id = ? AND charge_date = ? AND days_before = ?", sub_id, charge_date, days_before
        )

    async def prune_sent(self, before: str) -> None:
        await self._exec("DELETE FROM sent WHERE charge_date < ?", before)
