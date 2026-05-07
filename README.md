# Telegram TTS Bot

Telegram-бот для синтеза речи. Превращает текст в аудио через Microsoft Edge TTS — бесплатно, без API-ключей.

Стек: aiogram 3 · SQLAlchemy 2 (async) · PostgreSQL 16 · edge-tts · ffmpeg.

## Возможности

- Синтез речи на русском, узбекском и английском
- Выбор голоса (мужской / женский, для английского — US/UK акценты)
- Формат вывода: голосовое сообщение (OGG/Opus) или MP3
- Кэш в БД: повтор того же текста с тем же голосом — мгновенно из `file_id`
- Обязательная подписка на каналы (опционально, настраивается из админки)
- Админ-панель: статистика, управление каналами, рассылка
- Мультиязычный UI: русский, O'zbek, English
- Rate limit — 5 запросов/мин на пользователя
- Фоновая очистка: tmp-файлы (30 мин), старый кэш TTS (30 дней)

## Запуск (Docker)

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
python -m bot.main
```

## Стек

- `aiogram==3.26.0` — Telegram Bot API
- `SQLAlchemy==2.0.38` + `asyncpg==0.30.0` — PostgreSQL async ORM
- `edge-tts==7.2.8` — синтез речи (Microsoft Edge TTS)
- `pydantic-settings==2.8.1` — конфигурация из `.env`
- `alembic==1.14.1` — миграции БД (таблицы создаются через `create_all()`)
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
│   ├── models.py        — User / Channel / TtsRequest
│   └── crud.py          — CRUD запросы к БД
├── handlers/
│   ├── start.py         — /start, главное меню, смена языка, профиль
│   ├── tts.py           — FSM: текст → язык → голос → формат → синтез
│   └── admin.py         — /admin: статистика, каналы, рассылка
├── middlewares/
│   ├── subscription.py  — обязательная подписка на каналы
│   └── rate_limit.py    — 5 запросов/мин
├── keyboards/
│   ├── inline.py        — пользовательские клавиатуры (язык/голос/формат)
│   └── admin.py         — админские клавиатуры
├── services/
│   └── tts_service.py   — edge-tts синтез + ffmpeg конвертация
└── utils/
    ├── commands.py      — меню команд Telegram
    └── helpers.py       — вспомогательные функции
```

## Голоса

| Язык | Голоса |
|---|---|
| Русский | SvetlanaNeural (F), DmitryNeural (M) |
| O'zbek | MadinaNeural (F), SardorNeural (M) |
| English | JennyNeural (US F), GuyNeural (US M), SoniaNeural (UK F) |
