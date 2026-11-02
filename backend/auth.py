"""
Вспомогательные функции для JWT-авторизации.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from backend.config import settings


def create_token(user_id: int) -> str:
    """Создать JWT-токен для пользователя."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> int | None:
    """
    Проверить JWT-токен и вернуть user_id.
    Возвращает None при невалидном или просроченном токене.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            return None
        return int(user_id_str)
    except (JWTError, ValueError):
        return None
