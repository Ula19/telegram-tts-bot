"""Точка входа — запуск TTS-бота"""
import asyncio
import logging
import os
import sys
import time

# uvloop ускоряет asyncio в 2-4 раза (не работает на Windows!)
try:
    import uvloop
    uvloop.install()
except ImportError:
    pass  # на Windows — работаем без uvloop

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings

# настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# флаг-файл для crash recovery
CRASH_FLAG = ".crash_flag"


async def main() -> None:
    """Инициализация и запуск бота"""
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # подключаем хэндлеры (порядок важен: start → admin → tts — tts последний!)
    from bot.handlers import start, admin, tts
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(tts.router)

    # подключаем мидлвари
    from bot.middlewares.rate_limit import RateLimitMiddleware
    from bot.middlewares.subscription import SubscriptionMiddleware

    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # фоновая очистка: rate_limit, /tmp, БД-кэш
    async def _background_cleanup() -> None:
        """Фоновая задача: каждые 5 мин — память+tmp; раз в сутки — БД-кэш."""
        from bot.middlewares.rate_limit import cleanup_stale_entries
        from bot.database import async_session
        from bot.database.crud import delete_old_tts_cache

        TMP_DIR = "/tmp/tts_bot"
        FILE_TTL = 30 * 60          # 30 минут — временные файлы
        DB_CACHE_TTL_DAYS = 30      # 30 дней — записи tts_requests
        DB_CLEANUP_INTERVAL = 86400  # раз в сутки

        last_db_cleanup = 0.0
        while True:
            await asyncio.sleep(300)  # 5 минут

            # 1. протухшие записи rate limit
            removed = cleanup_stale_entries()
            if removed:
                logger.info("Очистка: удалено %d записей rate limit", removed)

            # 2. /tmp/tts_bot — файлы и пустые папки старше 30 мин
            now = time.time()
            cutoff = now - FILE_TTL
            files_cleaned = 0
            dirs_cleaned = 0
            try:
                for entry in os.scandir(TMP_DIR):
                    try:
                        if entry.is_file() and entry.stat().st_mtime < cutoff:
                            os.remove(entry.path)
                            files_cleaned += 1
                        elif entry.is_dir():
                            # удаляем файлы внутри + пустую папку
                            for sub in os.scandir(entry.path):
                                try:
                                    if sub.is_file() and sub.stat().st_mtime < cutoff:
                                        os.remove(sub.path)
                                        files_cleaned += 1
                                except OSError:
                                    pass
                            try:
                                if entry.stat().st_mtime < cutoff:
                                    os.rmdir(entry.path)  # упадёт если не пуста
                                    dirs_cleaned += 1
                            except OSError:
                                pass
                    except OSError:
                        pass
            except FileNotFoundError:
                os.makedirs(TMP_DIR, exist_ok=True)
            if files_cleaned or dirs_cleaned:
                logger.info(
                    "Очистка /tmp/tts_bot: %d файлов, %d папок",
                    files_cleaned, dirs_cleaned,
                )

            # 3. БД-кэш TtsRequest — раз в сутки
            if now - last_db_cleanup >= DB_CLEANUP_INTERVAL:
                last_db_cleanup = now
                try:
                    async with async_session() as session:
                        deleted = await delete_old_tts_cache(
                            session, days=DB_CACHE_TTL_DAYS,
                        )
                    if deleted:
                        logger.info(
                            "Очистка БД: удалено %d записей tts_requests старше %d дней",
                            deleted, DB_CACHE_TTL_DAYS,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Очистка БД tts_requests упала: %s", exc)

    @dp.startup()
    async def on_startup() -> None:
        # создаём таблицы в БД
        from bot.database import engine
        from bot.database.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Таблицы БД созданы")

        # проверяем crash recovery
        if os.path.exists(CRASH_FLAG):
            logger.warning("Обнаружен crash-flag — предыдущий запуск завершился аварийно")
            os.remove(CRASH_FLAG)

        # ставим crash-flag (уберём при нормальном завершении)
        with open(CRASH_FLAG, "w") as f:
            f.write("running")

        # запускаем фоновую очистку
        asyncio.create_task(_background_cleanup())
        logger.info("Фоновая очистка запущена (интервал 5 мин)")

        bot_info = await bot.get_me()
        logger.info(f"Бот @{bot_info.username} запущен!")

        # ставим дефолтное меню команд
        from bot.utils.commands import set_default_commands
        await set_default_commands(bot)
        logger.info("Дефолтное меню команд установлено")

    @dp.shutdown()
    async def on_shutdown() -> None:
        # убираем crash-flag при нормальном завершении
        if os.path.exists(CRASH_FLAG):
            os.remove(CRASH_FLAG)
        logger.info("Бот остановлен")

    # запускаем polling
    try:
        logger.info("Запуск polling...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
