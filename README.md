# bot_4_tts — Telegram-бот для синтеза речи (TTS)

Бот превращает текст в аудио через Microsoft Edge TTS (edge-tts).
Aiogram 3 + SQLAlchemy + PostgreSQL + edge-tts + ffmpeg.

## Возможности

- Синтез речи через edge-tts (Microsoft, бесплатно, без API-ключей)
- Поддержка языков: русский, узбекский, английский
- Выбор голоса (мужской / женский)
- Форматы: OGG/Opus (голосовое сообщение) или MP3
- Обязательная подписка на каналы (middleware)
- Админ-панель: статистика, управление каналами, рассылка
- Мультиязычность: русский, O'zbek, English
- Rate limit — 5 запросов/мин на юзера

## Деплой (Docker)

```bash
cp .env.example .env
# заполнить .env (BOT_TOKEN, DB_*, ADMIN_IDS)
docker compose up -d --build
docker compose logs -f bot
```

## Локальная разработка

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполнить .env
python -m bot.main
```

## Стек

- `aiogram==3.26.0` — Telegram Bot API
- `SQLAlchemy==2.0.38` + `asyncpg==0.30.0` — PostgreSQL async ORM
- `edge-tts>=6.1.9` — синтез речи (Microsoft Edge TTS)
- `pydantic-settings==2.8.1` — конфигурация из `.env`
- `alembic==1.14.1` — миграции БД (таблицы создаются через `create_all()`)
- `aiofiles==24.1.0` — асинхронная работа с файлами
- `uvloop==0.22.1` — ускорение asyncio
- `ffmpeg` (системный) — конвертация MP3 → OGG/Opus

## Структура

```
bot/
├── main.py              — entrypoint, роутеры, мидлвари, фоновая очистка
├── config.py            — pydantic-settings из .env
├── i18n.py              — переводы (ru/uz/en) + detect_language()
├── emojis.py            — премиум-эмодзи (E_ID и E)
├── database/
│   ├── __init__.py      — engine + async_session
│   ├── models.py        — User / Channel / TODO TtsRequest
│   └── crud.py          — CRUD запросы к БД
├── handlers/
│   ├── start.py         — /start, главное меню, смена языка, профиль
│   ├── tts.py           — TODO: FSM приём текста → синтез → отправка
│   └── admin.py         — /admin: статистика, каналы, рассылка
├── middlewares/
│   ├── subscription.py  — обязательная подписка на каналы
│   └── rate_limit.py    — 5 запросов/мин
├── keyboards/
│   ├── inline.py        — пользовательские клавиатуры (TODO: TTS кнопки)
│   └── admin.py         — админские клавиатуры
├── services/
│   └── tts_service.py   — TODO: edge-tts синтез + ffmpeg конвертация
└── utils/
    ├── commands.py      — меню команд Telegram
    └── helpers.py       — вспомогательные функции
```
