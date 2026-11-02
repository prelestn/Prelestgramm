# Prelestgram

Приватный мессенджер для ≤ 10 человек, построенный на форке Telegram-FOSS.

## Архитектура

| Компонент | Технологии |
|---|---|
| Android-клиент | Telegram-FOSS UI + собственный REST/WS сетевой слой |
| Backend | FastAPI + PostgreSQL + Redis + MinIO + JWT |
| Бот-администратора | aiogram 3 (long polling) |
| Хостинг | Railway |
| CI | GitHub Actions → APK (debug + release) |

Package ID Android-приложения: `com.prelestgram.app`

---

## Быстрый старт (локально)

### Backend

```bash
cd backend
cp .env.example .env
# Заполнить .env: DATABASE_URL, REDIS_URL, TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, JWT_SECRET

pip install -r requirements.txt
uvicorn main:app --reload
```

### Telegram-бот

```bash
cd backend
python bot.py
```

### Android

```bash
./gradlew assembleDebug
# APK: TMessagesProj_App/build/outputs/apk/debug/
```

---

## Деплой на Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

1. Создать новый проект на [railway.app](https://railway.app)
2. Добавить сервисы: PostgreSQL, Redis
3. Подключить этот GitHub-репозиторий
4. В разделе **Variables** задать:
   - `TELEGRAM_BOT_TOKEN` — токен от @BotFather
   - `ADMIN_CHAT_ID` — ваш Telegram ID (узнать у @userinfobot)
   - `JWT_SECRET` — случайная строка (`python -c "import secrets; print(secrets.token_hex(32))"`)
   - `DATABASE_URL` и `REDIS_URL` — Railway подставит автоматически при связывании сервисов
5. Railway автоматически задеплоит backend при каждом `git push`

Для бота создать отдельный сервис в том же Railway-проекте с командой запуска:
```
python backend/bot.py
```

---

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Панель администратора |
| `/invite` | Создать инвайт-код |
| `/issue_number` | Выдать номер из пула (добавить `collectible` для коллекционного) |
| `/code <номер>` | Сгенерировать код авторизации и отправить в чат |
| `/balance <user_id>` | Показать баланс пользователя |
| `/give_stars <user_id> <amount>` | Начислить звёзды |
| `/give_gift <user_id> <gift_type>` | Выдать подарок |
| `/give_nft <user_id> <token_id>` | Выдать NFT |
| `/ban <user_id>` | Заблокировать пользователя |

---

## Структура репозитория

```
├── backend/                  # FastAPI-приложение + бот
│   ├── main.py               # API-эндпоинты + WebSocket
│   ├── bot.py                # Telegram-бот (aiogram 3)
│   ├── models.py             # SQLAlchemy-модели
│   ├── auth.py               # JWT-утилиты
│   ├── database.py           # Настройка БД
│   ├── config.py             # Pydantic-настройки
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── TMessagesProj/src/main/java/org/telegram/prelest/
│   ├── PrelestApp.java                    # Application-класс
│   ├── network/PrelestApiClient.java      # REST + WebSocket клиент
│   └── auth/PrelestAuthActivity.java      # Экран авторизации
├── .github/workflows/build.yml            # GitHub Actions CI
├── railway.json                           # Railway-конфигурация
└── gradle.properties                      # APP_PACKAGE=com.prelestgram.app
```

---

## Авторизация (полный цикл)

1. Пользователь вводит номер телефона в Prelestgram.
2. `PrelestAuthActivity` → `POST /auth/request-code` → backend генерирует 6-значный код, сохраняет в Redis (TTL 5 мин), шлёт через бота в Telegram.
3. Пользователь получает код и вводит его в приложении.
4. `POST /auth/verify-code` → backend проверяет код в Redis → создаёт/находит пользователя → возвращает JWT.
5. JWT сохраняется в `SharedPreferences`; все последующие запросы идут с заголовком `Authorization: Bearer <token>`.

Никаких реальных SMS и внешних платёжных систем.
