"""Telegram-бот: вход в Mini App, список ближайших списаний, управление доступом."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    User,
    WebAppInfo,
)

from .auth import is_allowed
from .config import Config
from .db import Database
from .service import enrich, fmt_money, local_now, monthly_summary, when_text


def full_name(u: User) -> str:
    return " ".join(filter(None, [u.first_name, u.last_name])) or (u.username or "")


def app_keyboard(cfg: Config) -> InlineKeyboardMarkup | None:
    if not cfg.webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📱 Открыть подписки", web_app=WebAppInfo(url=cfg.webapp_url))]]
    )


async def setup_bot(bot: Bot, cfg: Config) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть приложение"),
            BotCommand(command="next", description="Ближайшие списания"),
            BotCommand(command="id", description="Мой Telegram ID"),
        ]
    )
    if cfg.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Подписки", web_app=WebAppInfo(url=cfg.webapp_url)))


def create_router(db: Database, cfg: Config) -> Router:
    router = Router()

    async def allowed(message: Message) -> dict | None:
        user = await db.touch_user(message.from_user.id, full_name(message.from_user))
        if is_allowed(user, user["id"], cfg.admin_id):
            return user
        await message.answer(
            f"Это приватный бот. Доступ выдаёт владелец.\nТвой ID: <code>{user['id']}</code>\n"
            "Запрос на доступ уже отправлен."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Разрешить", callback_data=f"allow:{user['id']}"),
                InlineKeyboardButton(text="🚫 Отклонить", callback_data=f"deny:{user['id']}"),
            ]]
        )
        username = f" @{message.from_user.username}" if message.from_user.username else ""
        await message.bot.send_message(
            cfg.admin_id,
            f"Запрос доступа: {escape(user['name'])}{escape(username)} (<code>{user['id']}</code>)",
            reply_markup=kb,
        )
        return None

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if not await allowed(message):
            return
        text = (
            "Привет! Я напомню о списаниях по подпискам заранее.\n\n"
            "Карты, подписки и время напоминаний настраиваются в приложении. "
            "/next — ближайшие списания."
        )
        if not cfg.webapp_url:
            text += "\n\n⚠️ WEBAPP_URL не задан — Mini App недоступен."
        await message.answer(text, reply_markup=app_keyboard(cfg))

    @router.message(Command("id"))
    async def my_id(message: Message) -> None:
        await message.answer(f"Твой ID: <code>{message.from_user.id}</code>")

    @router.message(Command("next"))
    async def upcoming(message: Message) -> None:
        user = await allowed(message)
        if not user:
            return
        today = local_now(user).date()
        cards = {c["id"]: c for c in await db.list_cards(user["id"])}
        subs = [enrich(s, user, today) for s in await db.list_subs(user["id"]) if s["active"]]
        if not subs:
            await message.answer("Подписок пока нет. Добавь их в приложении.", reply_markup=app_keyboard(cfg))
            return
        subs.sort(key=lambda s: s["next_charge"])
        lines = ["<b>Ближайшие списания</b>"]
        for s in subs[:15]:
            card = cards.get(s["card_id"])
            card_txt = f" · {escape(card['name'])}{' •' + card['last4'] if card and card['last4'] else ''}" if card else ""
            lines.append(
                f"• {s['next_charge'][8:10]}.{s['next_charge'][5:7]} ({when_text(s['days_left'])}) — "
                f"<b>{escape(s['name'])}</b> {fmt_money(s['amount'], s['currency'])}{card_txt}"
            )
        total = monthly_summary(subs)
        lines.append("\nВ месяц ≈ " + " + ".join(fmt_money(v, k) for k, v in total.items()))
        await message.answer("\n".join(lines), reply_markup=app_keyboard(cfg))

    # --- админка ---

    is_admin = F.from_user.id == cfg.admin_id

    @router.message(Command("users"), is_admin)
    async def users(message: Message) -> None:
        rows = await db.list_users()
        lines = ["<b>Пользователи</b>"]
        for u in rows:
            mark = "👑" if u["id"] == cfg.admin_id else ("✅" if u["allowed"] else "⛔")
            lines.append(f"{mark} {escape(u['name']) or '—'} <code>{u['id']}</code>")
        lines.append("\n/allow &lt;id&gt; — выдать доступ, /deny &lt;id&gt; — забрать")
        await message.answer("\n".join(lines))

    async def change_access(bot: Bot, user_id: int, allow: bool) -> str:
        if user_id == cfg.admin_id:
            return "Админ всегда имеет доступ."
        await db.set_allowed(user_id, allow)
        try:
            if allow:
                await bot.send_message(user_id, "Доступ открыт! Жми /start.")
        except Exception:
            pass  # пользователь мог ещё не писать боту
        return f"{'Доступ выдан' if allow else 'Доступ закрыт'}: <code>{user_id}</code>"

    @router.message(Command("allow", "deny"), is_admin)
    async def allow_cmd(message: Message, command: CommandObject) -> None:
        if not command.args or not command.args.strip().lstrip("-").isdigit():
            await message.answer(f"Формат: /{command.command} &lt;user_id&gt;")
            return
        await message.answer(await change_access(message.bot, int(command.args), command.command == "allow"))

    @router.callback_query(F.data.regexp(r"^(allow|deny):-?\d+$"), is_admin)
    async def allow_cb(call: CallbackQuery) -> None:
        action, uid = call.data.split(":")
        text = await change_access(call.bot, int(uid), action == "allow")
        await call.message.edit_text(f"{call.message.html_text}\n\n{text}")
        await call.answer()

    return router
