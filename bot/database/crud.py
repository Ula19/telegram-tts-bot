"""CRUD операции с базой данных"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Channel, TtsRequest, User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    full_name: str,
    language: str | None = None,
) -> User:
    """Получить юзера или создать нового"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            language=language or "ru",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def get_user_language(session: AsyncSession, telegram_id: int) -> str:
    """Получить язык юзера (по умолчанию ru)"""
    result = await session.execute(
        select(User.language).where(User.telegram_id == telegram_id)
    )
    lang = result.scalar_one_or_none()
    return lang or "ru"


async def update_user_language(
    session: AsyncSession, telegram_id: int, language: str
) -> None:
    """Обновить язык юзера"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        user.language = language
        await session.commit()


async def get_active_channels(session: AsyncSession) -> list[Channel]:
    """Получить все каналы для обязательной подписки"""
    result = await session.execute(select(Channel))
    return list(result.scalars().all())


async def add_channel(
    session: AsyncSession,
    channel_id: int,
    title: str,
    invite_link: str,
) -> Channel:
    """Добавить канал для обязательной подписки"""
    result = await session.execute(
        select(Channel).where(Channel.channel_id == channel_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError(f"Канал {channel_id} уже добавлен")

    channel = Channel(
        channel_id=channel_id,
        title=title,
        invite_link=invite_link,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def remove_channel(session: AsyncSession, channel_id: int) -> bool:
    """Удалить канал. Возвращает True если удалён"""
    result = await session.execute(
        select(Channel).where(Channel.channel_id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        return False

    await session.delete(channel)
    await session.commit()
    return True


async def get_user_stats(session: AsyncSession) -> dict:
    """Статистика: всего юзеров, за сегодня, озвучиваний"""
    from sqlalchemy import func as sa_func

    total = await session.execute(select(sa_func.count(User.id)))
    total_users = total.scalar() or 0

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await session.execute(
        select(sa_func.count(User.id)).where(User.created_at >= today)
    )
    today_users = today_result.scalar() or 0

    downloads = await session.execute(
        select(sa_func.sum(User.download_count))
    )
    total_downloads = downloads.scalar() or 0

    channels = await session.execute(select(sa_func.count(Channel.id)))
    total_channels = channels.scalar() or 0

    return {
        "total_users": total_users,
        "today_users": today_users,
        "total_downloads": total_downloads,
        "total_channels": total_channels,
    }


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    """Получить все telegram_id юзеров для рассылки"""
    result = await session.execute(select(User.telegram_id))
    return [row[0] for row in result.all()]


async def get_cached_tts(
    session: AsyncSession,
    text_hash: str,
    voice: str,
    fmt: str,
) -> TtsRequest | None:
    """Ищет кэш по хешу текста + голосу + формату"""
    result = await session.execute(
        select(TtsRequest).where(
            TtsRequest.text_hash == text_hash,
            TtsRequest.voice == voice,
            TtsRequest.format == fmt,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def save_tts_cache(
    session: AsyncSession,
    user_id: int,
    text_hash: str,
    voice: str,
    fmt: str,
    file_id: str,
) -> TtsRequest:
    """Сохраняет file_id для повторной отправки без синтеза"""
    req = TtsRequest(
        user_id=user_id,
        text_hash=text_hash,
        voice=voice,
        format=fmt,
        file_id=file_id,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def increment_user_tts_count(
    session: AsyncSession, telegram_id: int
) -> None:
    """Увеличивает download_count у юзера после успешной озвучки"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        user.download_count = (user.download_count or 0) + 1
        await session.commit()


async def delete_tts_cache(
    session: AsyncSession,
    text_hash: str,
    voice: str,
    fmt: str,
) -> None:
    """Удаляет кэш-запись (например, при протухшем file_id)."""
    result = await session.execute(
        select(TtsRequest).where(
            TtsRequest.text_hash == text_hash,
            TtsRequest.voice == voice,
            TtsRequest.format == fmt,
        )
    )
    for req in result.scalars().all():
        await session.delete(req)
    await session.commit()


async def delete_old_tts_cache(
    session: AsyncSession, days: int = 30,
) -> int:
    """Удаляет записи кэша старше N дней. Возвращает число удалённых строк."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        delete(TtsRequest).where(TtsRequest.created_at < cutoff)
    )
    await session.commit()
    return result.rowcount or 0
