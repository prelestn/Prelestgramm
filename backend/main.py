"""
FastAPI-приложение Prelestgram.
Точка входа для Railway.
"""
import json
import random
import string
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aioredis
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import create_token, verify_token
from backend.config import settings
from backend.database import get_db, init_db
from backend.models import AuthCode, Chat, ChatMember, Message, User


# --- Менеджер WebSocket-подключений ---

class ConnectionManager:
    """Управляет активными WebSocket-соединениями пользователей."""

    def __init__(self) -> None:
        # user_id -> список активных соединений
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        conns = self._connections.get(user_id, [])
        if ws in conns:
            conns.remove(ws)

    async def send_to_user(self, user_id: int, data: dict) -> None:
        """Отправить JSON-сообщение всем сессиям пользователя."""
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                pass


manager = ConnectionManager()


# --- Lifecycle ---

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Инициализация при старте, очистка при остановке."""
    await init_db()
    yield


app = FastAPI(
    title="Prelestgram API",
    version="1.0.0",
    lifespan=lifespan,
)

security = HTTPBearer()


# --- Вспомогательные функции ---

def _generate_code() -> str:
    """Сгенерировать 6-значный числовой код."""
    return "".join(random.choices(string.digits, k=6))


async def _get_redis() -> aioredis.Redis:
    """Создать подключение к Redis."""
    return await aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Зависимость: получить текущего пользователя по Bearer-токену."""
    user_id = verify_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    if user.is_banned:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Аккаунт заблокирован")
    return user


# --- Схемы запросов/ответов ---

class RequestCodeBody(BaseModel):
    phone: str


class VerifyCodeBody(BaseModel):
    phone: str
    code: str


class SendMessageBody(BaseModel):
    chat_id: int
    content: str


# --- Эндпоинты авторизации ---

@app.post("/auth/request-code")
async def request_code(body: RequestCodeBody, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Запросить код авторизации.
    Backend генерирует код, сохраняет в Redis и дёргает Telegram-бота,
    чтобы тот отправил код в чат администратора (или пользователю напрямую).
    """
    phone = body.phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Номер телефона обязателен")

    code = _generate_code()

    # Сохранить код в Redis с TTL
    redis = await _get_redis()
    redis_key = f"auth_code:{phone}"
    await redis.setex(redis_key, settings.AUTH_CODE_TTL, code)
    await redis.aclose()

    # Уведомить бота через Telegram Bot API (fire-and-forget)
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": settings.ADMIN_CHAT_ID,
                    "text": f"🔐 Код для {phone}: <b>{code}</b>\nИстекает через 5 минут.",
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
    except Exception:
        # Не прерываем поток — бот может быть временно недоступен
        pass

    return {"status": "ok", "message": "Код отправлен"}


@app.post("/auth/verify-code")
async def verify_code(body: VerifyCodeBody, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Проверить код авторизации.
    Если пользователь новый — создать аккаунт.
    Возвращает JWT-токен.
    """
    phone = body.phone.strip()
    code = body.code.strip()

    # Проверить код из Redis
    redis = await _get_redis()
    redis_key = f"auth_code:{phone}"
    stored_code = await redis.get(redis_key)

    if stored_code is None:
        await redis.aclose()
        raise HTTPException(status_code=400, detail="Код истёк или не существует")

    if stored_code != code:
        await redis.aclose()
        raise HTTPException(status_code=400, detail="Неверный код")

    # Удалить использованный код
    await redis.delete(redis_key)
    await redis.aclose()

    # Найти или создать пользователя
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(phone=phone)
        db.add(user)
        await db.flush()  # получить id без коммита

    token = create_token(user.id)
    return {"token": token, "user_id": user.id}


# --- Эндпоинты пользователя ---

@app.get("/users/me")
async def get_me(current_user: User = Depends(get_current_user)) -> dict:
    """Получить профиль текущего пользователя."""
    return {
        "id": current_user.id,
        "phone": current_user.phone,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "avatar_url": current_user.avatar_url,
        "is_premium": current_user.is_premium,
        "stars_balance": current_user.stars_balance,
        "created_at": current_user.created_at.isoformat(),
    }


# --- Эндпоинты чатов ---

@app.get("/chats")
async def get_chats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Получить список чатов текущего пользователя."""
    result = await db.execute(
        select(Chat)
        .join(ChatMember, ChatMember.chat_id == Chat.id)
        .where(ChatMember.user_id == current_user.id)
    )
    chats = result.scalars().all()
    return {
        "chats": [
            {
                "id": c.id,
                "type": c.type,
                "title": c.title,
                "created_at": c.created_at.isoformat(),
            }
            for c in chats
        ]
    }


@app.get("/chats/{chat_id}/messages")
async def get_messages(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Получить историю сообщений чата."""
    # Проверить, что пользователь — участник чата
    membership = await db.execute(
        select(ChatMember).where(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id == current_user.id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Нет доступа к чату")

    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id, Message.is_deleted == False)  # noqa: E712
        .order_by(Message.created_at.asc())
        .limit(100)
    )
    messages = result.scalars().all()
    return {
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "content": m.content,
                "media_url": m.media_url,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    }


@app.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: int,
    body: SendMessageBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Отправить сообщение в чат."""
    # Проверить участие
    membership = await db.execute(
        select(ChatMember).where(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id == current_user.id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Нет доступа к чату")

    msg = Message(chat_id=chat_id, sender_id=current_user.id, content=body.content)
    db.add(msg)
    await db.flush()

    # Уведомить всех участников чата через WebSocket
    members_result = await db.execute(
        select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
    )
    member_ids = [row[0] for row in members_result.fetchall()]

    ws_data = {
        "type": "new_message",
        "chat_id": chat_id,
        "message": {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
        },
    }
    for uid in member_ids:
        await manager.send_to_user(uid, ws_data)

    return {"id": msg.id, "created_at": msg.created_at.isoformat()}


# --- WebSocket ---

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(ws: WebSocket, user_id: int) -> None:
    """
    WebSocket-канал реального времени для пользователя.
    Клиент должен отправить первым сообщением: {"token": "<jwt>"}
    """
    await ws.accept()

    # Аутентификация по токену в первом сообщении
    try:
        raw = await ws.receive_text()
        data = json.loads(raw)
        token = data.get("token", "")
    except Exception:
        await ws.close(code=4000)
        return

    verified_id = verify_token(token)
    if verified_id != user_id:
        await ws.close(code=4001)
        return

    # Добавить в менеджер (без повторного accept — уже принят выше)
    manager._connections.setdefault(user_id, []).append(ws)

    try:
        while True:
            # Держим соединение открытым, обрабатываем пинги
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, ws)


# --- Healthcheck ---

@app.get("/health")
async def health() -> dict:
    """Railway healthcheck."""
    return {"status": "ok"}
