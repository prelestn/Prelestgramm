"""
Telegram-бот администратора Prelestgram на aiogram 3.
Запускается в режиме long polling на Railway.
"""
import asyncio
import random
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import aioredis
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import AsyncSessionLocal, init_db
from backend.models import Gift, Invite, NFT, PhoneNumber, User

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


# --- Пулы форматов телефонных номеров ---

PHONE_POOLS = [
    # Россия мобильные
    lambda: f"+7 999 {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}",
    lambda: f"+7 495 {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}",
    # США
    lambda: f"+1 {random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}",
    # Великобритания
    lambda: f"+44 7{random.randint(100, 999)} {random.randint(100000, 999999)}",
    # Германия
    lambda: f"+49 15{random.randint(1, 9)} {random.randint(1000000, 9999999)}",
    # Украина
    lambda: f"+380 {random.randint(50, 99)} {random.randint(100, 999)} {random.randint(10, 99)} {random.randint(10, 99)}",
    # Беларусь
    lambda: f"+375 {random.randint(25, 44)} {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}",
]


def _generate_collectible_number() -> tuple[str, bool]:
    """
    Сгенерировать коллекционный номер (+888).
    Возвращает (номер, is_collectible=True).
    """
    variants = [
        f"+888 {d}{d}{d}-{d}{d}-{d}{d}"
        for d in range(1, 10)
    ] + [
        f"+888 123-45-67",
        f"+888 777-77-77",
        f"+888 888-88-88",
        f"+888 999-99-99",
        f"+888 {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}",
    ]
    return random.choice(variants), True


async def _issue_unique_number(db: AsyncSession, collectible: bool = False) -> str:
    """Сгенерировать уникальный номер и сохранить в БД."""
    for _ in range(100):  # максимум 100 попыток
        if collectible:
            number, is_col = _generate_collectible_number()
        else:
            number = random.choice(PHONE_POOLS)()
            is_col = False

        # Проверить уникальность
        result = await db.execute(select(PhoneNumber).where(PhoneNumber.number == number))
        if result.scalar_one_or_none() is None:
            phone_obj = PhoneNumber(number=number, is_collectible=is_col)
            db.add(phone_obj)
            await db.commit()
            return number

    raise RuntimeError("Не удалось сгенерировать уникальный номер за 100 попыток")


# --- Клавиатура панели администратора ---

def _admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Инвайт", callback_data="admin:invite"),
         InlineKeyboardButton(text="📱 Номер", callback_data="admin:number")],
        [InlineKeyboardButton(text="⭐ Коллекционный номер", callback_data="admin:collectible")],
    ])


# --- Хендлеры ---

@dp.message(Command("start"))
async def cmd_start(msg: Message) -> None:
    """Панель администратора."""
    await msg.answer(
        "👑 <b>Панель администратора Prelestgram</b>\n\n"
        "Выберите действие или используйте команды:\n"
        "/invite — создать инвайт\n"
        "/issue_number — выдать номер\n"
        "/code &lt;номер&gt; — выдать код авторизации\n"
        "/balance &lt;user_id&gt; — баланс пользователя\n"
        "/give_stars &lt;user_id&gt; &lt;amount&gt; — начислить звёзды\n"
        "/give_gift &lt;user_id&gt; &lt;type&gt; — выдать подарок\n"
        "/give_nft &lt;user_id&gt; &lt;token_id&gt; — выдать NFT\n"
        "/ban &lt;user_id&gt; — заблокировать",
        parse_mode="HTML",
        reply_markup=_admin_keyboard(),
    )


@dp.callback_query(F.data == "admin:invite")
async def cb_invite(cb: CallbackQuery) -> None:
    async with AsyncSessionLocal() as db:
        code = secrets.token_urlsafe(16)
        invite = Invite(code=code)
        db.add(invite)
        await db.commit()
    await cb.message.answer(f"✅ Инвайт создан:\n<code>{code}</code>", parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "admin:number")
async def cb_number(cb: CallbackQuery) -> None:
    async with AsyncSessionLocal() as db:
        number = await _issue_unique_number(db, collectible=False)
    await cb.message.answer(f"📱 Номер выдан:\n<code>{number}</code>", parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "admin:collectible")
async def cb_collectible(cb: CallbackQuery) -> None:
    async with AsyncSessionLocal() as db:
        number = await _issue_unique_number(db, collectible=True)
    await cb.message.answer(
        f"⭐ Коллекционный номер выдан:\n<code>{number}</code>",
        parse_mode="HTML",
    )
    await cb.answer()


@dp.message(Command("invite"))
async def cmd_invite(msg: Message) -> None:
    """Создать инвайт-код."""
    async with AsyncSessionLocal() as db:
        code = secrets.token_urlsafe(16)
        invite = Invite(code=code)
        db.add(invite)
        await db.commit()
    await msg.answer(f"✅ Инвайт создан:\n<code>{code}</code>", parse_mode="HTML")


@dp.message(Command("issue_number"))
async def cmd_issue_number(msg: Message) -> None:
    """Выдать уникальный телефонный номер из пула."""
    # Если после команды есть слово "collectible" — выдаём коллекционный
    text = msg.text or ""
    collectible = "collectible" in text.lower()
    async with AsyncSessionLocal() as db:
        number = await _issue_unique_number(db, collectible=collectible)
    label = "⭐ Коллекционный номер" if collectible else "📱 Номер"
    await msg.answer(f"{label} выдан:\n<code>{number}</code>", parse_mode="HTML")


@dp.message(Command("code"))
async def cmd_code(msg: Message) -> None:
    """
    Сгенерировать 6-значный код для номера.
    Использование: /code +7 999 123-45-67
    """
    text = msg.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("❌ Укажите номер: /code +7 999 123-45-67")
        return

    phone = parts[1].strip()
    code = "".join(random.choices(string.digits, k=6))

    # Сохранить в Redis с TTL 5 минут
    redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis.setex(f"auth_code:{phone}", settings.AUTH_CODE_TTL, code)
    await redis.aclose()

    await msg.answer(
        f"🔐 Код для <code>{phone}</code>:\n<b>{code}</b>\nИстекает через 5 минут.",
        parse_mode="HTML",
    )


@dp.message(Command("balance"))
async def cmd_balance(msg: Message) -> None:
    """Показать баланс пользователя. /balance <user_id>"""
    parts = (msg.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await msg.answer("❌ Использование: /balance <user_id>")
        return

    user_id = int(parts[1])
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user is None:
        await msg.answer(f"❌ Пользователь {user_id} не найден")
        return

    await msg.answer(
        f"👤 <b>Пользователь {user_id}</b>\n"
        f"📱 Телефон: <code>{user.phone}</code>\n"
        f"⭐ Звёзды: {user.stars_balance}\n"
        f"💎 Премиум: {'да' if user.is_premium else 'нет'}\n"
        f"🚫 Бан: {'да' if user.is_banned else 'нет'}",
        parse_mode="HTML",
    )


@dp.message(Command("give_stars"))
async def cmd_give_stars(msg: Message) -> None:
    """Начислить звёзды пользователю. /give_stars <user_id> <amount>"""
    parts = (msg.text or "").split()
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await msg.answer("❌ Использование: /give_stars <user_id> <amount>")
        return

    user_id = int(parts[1])
    amount = int(parts[2])

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            await msg.answer(f"❌ Пользователь {user_id} не найден")
            return
        user.stars_balance += amount
        await db.commit()

    await msg.answer(f"✅ Начислено {amount} звёзд пользователю {user_id}. Баланс: {user.stars_balance}")


@dp.message(Command("give_gift"))
async def cmd_give_gift(msg: Message) -> None:
    """Выдать подарок пользователю. /give_gift <user_id> <gift_type>"""
    parts = (msg.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await msg.answer("❌ Использование: /give_gift <user_id> <gift_type>")
        return

    user_id = int(parts[1])
    gift_type = parts[2].strip()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            await msg.answer(f"❌ Пользователь {user_id} не найден")
            return
        gift = Gift(user_id=user_id, gift_type=gift_type)
        db.add(gift)
        await db.commit()

    await msg.answer(f"🎁 Подарок «{gift_type}» выдан пользователю {user_id}")


@dp.message(Command("give_nft"))
async def cmd_give_nft(msg: Message) -> None:
    """Выдать NFT пользователю. /give_nft <user_id> <token_id>"""
    parts = (msg.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await msg.answer("❌ Использование: /give_nft <user_id> <token_id>")
        return

    user_id = int(parts[1])
    token_id = parts[2].strip()

    async with AsyncSessionLocal() as db:
        # Проверить уникальность token_id
        existing = await db.execute(select(NFT).where(NFT.token_id == token_id))
        if existing.scalar_one_or_none() is not None:
            await msg.answer(f"❌ NFT с token_id «{token_id}» уже существует")
            return

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            await msg.answer(f"❌ Пользователь {user_id} не найден")
            return

        nft = NFT(user_id=user_id, token_id=token_id)
        db.add(nft)
        await db.commit()

    await msg.answer(f"🖼 NFT «{token_id}» выдан пользователю {user_id}")


@dp.message(Command("ban"))
async def cmd_ban(msg: Message) -> None:
    """Заблокировать пользователя. /ban <user_id>"""
    parts = (msg.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await msg.answer("❌ Использование: /ban <user_id>")
        return

    user_id = int(parts[1])

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            await msg.answer(f"❌ Пользователь {user_id} не найден")
            return
        user.is_banned = True
        await db.commit()

    await msg.answer(f"🚫 Пользователь {user_id} заблокирован")


async def main() -> None:
    """Запустить бота в режиме long polling."""
    await init_db()
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
