"""Хэндлер TTS — текст → аудио.

FSM: waiting_text → choose_language → choose_voice → choose_format → done.
"""
import asyncio
import hashlib
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    Message,
)

from bot.database import async_session
from bot.database.crud import (
    delete_tts_cache,
    get_cached_tts,
    get_user_language,
    increment_user_tts_count,
    save_tts_cache,
)
from bot.i18n import t
from bot.keyboards.inline import (
    get_back_keyboard,
    get_start_keyboard,
    get_tts_format_keyboard,
    get_tts_lang_keyboard,
    get_tts_voice_keyboard,
)
from bot.services import tts_service

logger = logging.getLogger(__name__)
router = Router()

# Семафор на параллельные синтезы (только сам edge-tts/ffmpeg, не retry-backoff)
_TTS_SEMAPHORE = asyncio.Semaphore(4)

MAX_TEXT_LEN = tts_service.MAX_TEXT_LEN


class TtsStates(StatesGroup):
    waiting_text = State()
    choose_language = State()
    choose_voice = State()
    choose_format = State()
    processing = State()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


# === Точки входа ===

@router.callback_query(F.data == "tts_start")
async def cb_tts_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Кнопка «Текст в аудио» — просим прислать текст."""
    async with async_session() as session:
        lang = await get_user_language(session, callback.from_user.id)

    await state.clear()
    await state.set_state(TtsStates.waiting_text)

    await callback.message.edit_text(
        t("tts.prompt", lang),
        reply_markup=get_back_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(TtsStates.waiting_text, F.text)
async def handle_text_in_state(message: Message, state: FSMContext) -> None:
    await _process_incoming_text(message, state)


@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def handle_text_default(message: Message, state: FSMContext) -> None:
    """Юзер прислал текст без активного FSM — обрабатываем как TTS."""
    await _process_incoming_text(message, state)


async def _process_incoming_text(message: Message, state: FSMContext) -> None:
    async with async_session() as session:
        lang = await get_user_language(session, message.from_user.id)

    text = (message.text or "").strip()
    if not text:
        await message.answer(t("error.empty_text", lang), parse_mode="HTML")
        return
    if len(text) > MAX_TEXT_LEN:
        await message.answer(
            t("error.text_too_long", lang, max_chars=MAX_TEXT_LEN),
            parse_mode="HTML",
        )
        return

    await state.update_data(tts_text=text)
    await state.set_state(TtsStates.choose_language)

    await message.answer(
        t("tts.choose_lang", lang),
        reply_markup=get_tts_lang_keyboard(lang),
        parse_mode="HTML",
    )


# === Выбор языка озвучки ===

@router.callback_query(
    StateFilter(TtsStates.choose_language, TtsStates.choose_voice, TtsStates.choose_format),
    F.data.startswith("tts_lang_"),
)
async def cb_choose_language(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    tts_lang = callback.data.removeprefix("tts_lang_")
    if tts_lang not in tts_service.VOICES:
        await callback.answer()
        return

    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)

    data = await state.get_data()
    if not data.get("tts_text"):
        await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)
        return

    await state.update_data(tts_lang=tts_lang)
    await state.set_state(TtsStates.choose_voice)

    voices = tts_service.get_voices(tts_lang)
    await callback.message.edit_text(
        t("tts.choose_voice", ui_lang),
        reply_markup=get_tts_voice_keyboard(voices, ui_lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tts_lang_"))
async def cb_choose_language_invalid(callback: CallbackQuery) -> None:
    """Клик по старой клавиатуре — сессия истекла."""
    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)
    await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)


@router.callback_query(
    StateFilter(TtsStates.choose_language, TtsStates.choose_voice, TtsStates.choose_format),
    F.data == "tts_back_to_lang",
)
async def cb_back_to_lang(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)
    await state.set_state(TtsStates.choose_language)
    await callback.message.edit_text(
        t("tts.choose_lang", ui_lang),
        reply_markup=get_tts_lang_keyboard(ui_lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "tts_back_to_lang")
async def cb_back_to_lang_invalid(callback: CallbackQuery) -> None:
    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)
    await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)


@router.callback_query(
    StateFilter(TtsStates.choose_voice, TtsStates.choose_format),
    F.data == "tts_back_to_voice",
)
async def cb_back_to_voice(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)

    data = await state.get_data()
    tts_lang = data.get("tts_lang")
    if not data.get("tts_text") or not tts_lang:
        await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)
        return

    await state.set_state(TtsStates.choose_voice)
    voices = tts_service.get_voices(tts_lang)
    await callback.message.edit_text(
        t("tts.choose_voice", ui_lang),
        reply_markup=get_tts_voice_keyboard(voices, ui_lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "tts_back_to_voice")
async def cb_back_to_voice_invalid(callback: CallbackQuery) -> None:
    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)
    await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)


# === Выбор голоса ===

@router.callback_query(
    StateFilter(TtsStates.choose_voice),
    F.data.startswith("tts_voice_"),
)
async def cb_choose_voice(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    voice = callback.data.removeprefix("tts_voice_")

    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)

    data = await state.get_data()
    tts_lang = data.get("tts_lang")
    if not data.get("tts_text") or not tts_lang:
        await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)
        return

    if not tts_service.is_valid_voice(tts_lang, voice):
        await callback.answer()
        return

    await state.update_data(tts_voice=voice)
    await state.set_state(TtsStates.choose_format)

    await callback.message.edit_text(
        t("tts.choose_format", ui_lang),
        reply_markup=get_tts_format_keyboard(ui_lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tts_voice_"))
async def cb_choose_voice_invalid(callback: CallbackQuery) -> None:
    """Клик по старой клавиатуре голосов — сессия истекла."""
    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)
    await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)


# === Выбор формата + синтез ===

@router.callback_query(
    StateFilter(TtsStates.choose_format),
    F.data.startswith("tts_format_"),
)
async def cb_choose_format(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    fmt = callback.data.removeprefix("tts_format_")
    if fmt not in ("voice", "mp3"):
        await callback.answer()
        return

    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)

    data = await state.get_data()
    text = data.get("tts_text")
    voice = data.get("tts_voice")
    if not text or not voice:
        await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)
        return

    # сразу переключаемся в processing — защита от дабл-клика
    await state.set_state(TtsStates.processing)

    await callback.message.edit_text(
        t("tts.processing", ui_lang),
        parse_mode="HTML",
    )
    await callback.answer()

    await _do_tts(
        callback=callback,
        state=state,
        text=text,
        voice=voice,
        fmt=fmt,
        ui_lang=ui_lang,
    )


@router.callback_query(F.data.startswith("tts_format_"))
async def cb_choose_format_invalid(callback: CallbackQuery) -> None:
    """Клик по старой клавиатуре форматов — сессия истекла или уже в обработке."""
    async with async_session() as session:
        ui_lang = await get_user_language(session, callback.from_user.id)
    await callback.answer(t("tts.invalid_session", ui_lang), show_alert=True)


async def _do_tts(
    callback: CallbackQuery,
    state: FSMContext,
    text: str,
    voice: str,
    fmt: str,
    ui_lang: str,
) -> None:
    """Синтез + отправка + кэширование."""
    text_hash = _hash_text(text)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    bot = callback.bot

    # 1. Проверяем кэш
    try:
        async with async_session() as session:
            cached = await get_cached_tts(session, text_hash, voice, fmt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_cached_tts failed: %s", exc)
        cached = None

    if cached is not None:
        try:
            if fmt == "voice":
                await bot.send_voice(chat_id, cached.file_id)
            else:
                await bot.send_audio(chat_id, cached.file_id)
            await _finalize_success(callback, state, ui_lang, user_id)
            return
        except Exception as exc:  # noqa: BLE001
            # file_id мог протухнуть — удаляем кэш и синтезируем заново
            logger.info("Cached file_id invalid, regenerating: %s", exc)
            try:
                async with async_session() as session:
                    await delete_tts_cache(session, text_hash, voice, fmt)
            except Exception as del_exc:  # noqa: BLE001
                logger.warning("delete_tts_cache failed: %s", del_exc)

    # 2. Синтез — семафор только на сам edge-tts/ffmpeg
    output_path = None
    try:
        async with _TTS_SEMAPHORE:
            output_path = await tts_service.synthesize(text, voice, fmt)

        # 3. Отправка
        if fmt == "voice":
            sent = await bot.send_voice(
                chat_id,
                FSInputFile(str(output_path)),
            )
            file_id = sent.voice.file_id if sent.voice else None
        else:
            sent = await bot.send_audio(
                chat_id,
                FSInputFile(str(output_path)),
                title="TTS",
            )
            file_id = sent.audio.file_id if sent.audio else None

        # 4. Кэш
        if file_id:
            try:
                async with async_session() as session:
                    await save_tts_cache(
                        session, user_id, text_hash, voice, fmt, file_id,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("save_tts_cache failed: %s", exc)

        await _finalize_success(callback, state, ui_lang, user_id)

    except Exception as exc:  # noqa: BLE001
        category = tts_service.classify_error(exc)
        # no_audio — не баг, а несовпадение языка голоса и текста: warning без traceback
        if category == "no_audio":
            logger.warning("TTS no_audio (voice/text language mismatch): %s", exc)
        else:
            logger.exception("TTS synthesis failed: %s", exc)
        if category == "text_too_long":
            err_text = t("error.text_too_long", ui_lang, max_chars=MAX_TEXT_LEN)
        elif category == "empty_text":
            err_text = t("error.empty_text", ui_lang)
        elif category == "no_audio":
            err_text = t("error.no_audio", ui_lang)
        elif category == "timeout":
            err_text = t("error.timeout", ui_lang)
        else:
            err_text = t("tts.error_synth", ui_lang)
        # удаляем "Озвучиваю..." сообщение чтобы не засорять чат
        try:
            await callback.message.delete()
        except Exception:  # noqa: BLE001
            pass
        try:
            await bot.send_message(
                chat_id, err_text,
                reply_markup=get_start_keyboard(user_id, ui_lang),
                parse_mode="HTML",
            )
        except Exception:  # noqa: BLE001
            pass
        await state.clear()
    finally:
        # Обязательная очистка временного файла
        if output_path is not None:
            tts_service.cleanup_file(output_path)


async def _finalize_success(
    callback: CallbackQuery,
    state: FSMContext,
    ui_lang: str,
    user_id: int,
) -> None:
    """Инкрементирует счётчик, чистит FSM, шлёт меню."""
    try:
        async with async_session() as session:
            await increment_user_tts_count(session, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("increment_user_tts_count failed: %s", exc)

    await state.clear()
    # удаляем "Озвучиваю..." сообщение чтобы не засорять чат
    try:
        await callback.message.delete()
    except Exception:  # noqa: BLE001
        pass
    try:
        await callback.bot.send_message(
            callback.message.chat.id,
            t("tts.done", ui_lang),
            reply_markup=get_start_keyboard(user_id, ui_lang),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        pass
