"""Сервис синтеза речи через edge-tts.

Движок: edge-tts (Python пакет, обёртка над Microsoft Edge TTS).
Бесплатный, без API-ключей.
"""
import asyncio
import logging
import uuid
from pathlib import Path

import aiohttp
import edge_tts

logger = logging.getLogger(__name__)

TMP_DIR = Path("/tmp/tts_bot")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Доступные голоса (фиксированный список)
# lang -> [(voice_id, label)]
VOICES: dict[str, list[tuple[str, str]]] = {
    "uz": [
        ("uz-UZ-MadinaNeural", "Madina (F)"),
        ("uz-UZ-SardorNeural", "Sardor (M)"),
    ],
    "ru": [
        ("ru-RU-SvetlanaNeural", "Светлана (F)"),
        ("ru-RU-DmitryNeural", "Дмитрий (M)"),
    ],
    "en": [
        ("en-US-JennyNeural", "Jenny US (F)"),
        ("en-US-GuyNeural", "Guy US (M)"),
        ("en-GB-SoniaNeural", "Sonia UK (F)"),
    ],
}

MAX_TEXT_LEN = 4000
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = (1, 2, 4)
EDGE_TTS_TIMEOUT = 60   # сек на один вызов edge-tts save
FFMPEG_TIMEOUT = 30     # сек на конвертацию в OGG/Opus

# Исключения, которые имеет смысл ретраить (сетевые/временные)
_RETRYABLE_EXCEPTIONS: tuple = (
    aiohttp.ClientError,
    asyncio.TimeoutError,
)
# edge_tts UnexpectedResponse/WebSocketError — сетевые, ретраим.
# NoAudioReceived НЕ ретраим — это значит что текст не распознан
# движком (пустой / только эмодзи / странные символы), повтор бесполезен.
_edge_exc_module = getattr(edge_tts, "exceptions", None)
if _edge_exc_module is not None:
    for _name in ("UnexpectedResponse", "WebSocketError"):
        _exc = getattr(_edge_exc_module, _name, None)
        if _exc is not None:
            _RETRYABLE_EXCEPTIONS = _RETRYABLE_EXCEPTIONS + (_exc,)


def get_voices(lang: str) -> list[tuple[str, str]]:
    """Возвращает список голосов для языка."""
    return VOICES.get(lang, VOICES["en"])


def is_valid_voice(lang: str, voice: str) -> bool:
    return any(v == voice for v, _ in get_voices(lang))


async def _edge_save(text: str, voice: str, mp3_path: Path) -> None:
    """Однократный вызов edge-tts с сохранением в mp3 файл (с таймаутом)."""
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await asyncio.wait_for(
        communicate.save(str(mp3_path)),
        timeout=EDGE_TTS_TIMEOUT,
    )


async def _convert_to_ogg(mp3_path: Path, ogg_path: Path) -> None:
    """Конвертирует MP3 → OGG/Opus через ffmpeg (для send_voice)."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(mp3_path),
        "-c:a", "libopus", "-b:a", "64k",
        str(ogg_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=FFMPEG_TIMEOUT,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        raise
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (code={proc.returncode}): "
            f"{stderr.decode('utf-8', errors='ignore')[:200]}"
        )


async def synthesize(text: str, voice: str, fmt: str = "voice") -> Path:
    """Синтезирует речь, возвращает путь к временному файлу.

    fmt: "voice" → OGG/Opus (для send_voice), "mp3" → MP3 (для send_audio).
    Вызывающий обязан удалить файл после отправки.
    """
    if not text or not text.strip():
        raise ValueError("empty text")
    if len(text) > MAX_TEXT_LEN:
        raise ValueError(f"text too long: {len(text)} > {MAX_TEXT_LEN}")

    uid = uuid.uuid4().hex
    work_dir = TMP_DIR / uid
    work_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = work_dir / "output.mp3"

    # retry с экспоненциальным backoff — ретраим только сетевые ошибки
    last_err: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            await _edge_save(text, voice, mp3_path)
            if not mp3_path.exists() or mp3_path.stat().st_size == 0:
                raise RuntimeError("edge-tts produced empty file")
            last_err = None
            break
        except _RETRYABLE_EXCEPTIONS as exc:
            last_err = exc
            logger.warning(
                "edge-tts attempt %d/%d failed (retryable): %s",
                attempt + 1, RETRY_ATTEMPTS, exc,
            )
            if attempt < RETRY_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_BACKOFF[attempt])
        except Exception as exc:  # noqa: BLE001
            # не сетевая ошибка — не ретраим, пробрасываем сразу
            logger.warning("edge-tts non-retryable error: %s", exc)
            last_err = exc
            break

    if last_err is not None:
        # подчищаем рабочую папку
        try:
            mp3_path.unlink(missing_ok=True)
            work_dir.rmdir()
        except OSError:
            pass
        raise last_err

    if fmt == "mp3":
        return mp3_path

    # fmt == "voice" → конвертируем в OGG/Opus
    ogg_path = work_dir / "output.ogg"
    try:
        await _convert_to_ogg(mp3_path, ogg_path)
    finally:
        mp3_path.unlink(missing_ok=True)
    return ogg_path


def cleanup_file(path: Path | str | None) -> None:
    """Удаляет файл и его пустую родительскую папку (best-effort)."""
    if not path:
        return
    p = Path(path)
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        parent = p.parent
        if parent != TMP_DIR and parent.is_relative_to(TMP_DIR):
            parent.rmdir()
    except OSError:
        pass


def classify_error(exc: Exception) -> str:
    """Классификация ошибок для юзер-френдли сообщений."""
    msg = str(exc).lower()
    if isinstance(exc, ValueError):
        if "too long" in msg:
            return "text_too_long"
        if "empty" in msg:
            return "empty_text"
    if isinstance(exc, asyncio.TimeoutError) or "timeout" in msg:
        return "timeout"
    if isinstance(exc, aiohttp.ClientError):
        return "api_error"
    if "ffmpeg" in msg:
        return "ffmpeg_error"
    if "no audio" in msg:
        return "no_audio"
    if "websocket" in msg or "connection" in msg:
        return "api_error"
    return "unknown"
