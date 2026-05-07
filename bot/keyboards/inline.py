"""Inline-клавиатуры — меню, подписка, TTS"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings
from bot.emojis import E_ID
from bot.i18n import t


def get_start_keyboard(user_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню бота"""
    buttons = [
        [InlineKeyboardButton(
            text=t("btn.tts", lang),
            callback_data="tts_start",
            style="primary",
            icon_custom_emoji_id=E_ID["music"],
        )],
        [
            InlineKeyboardButton(
                text=t("btn.profile", lang),
                callback_data="my_profile",
                style="success",
                icon_custom_emoji_id=E_ID["profile"],
            ),
            InlineKeyboardButton(
                text=t("btn.help", lang),
                callback_data="my_help",
                style="success",
                icon_custom_emoji_id=E_ID["info"],
            ),
        ],
        [InlineKeyboardButton(
            text=t("btn.language", lang),
            callback_data="change_language",
            style="success",
            icon_custom_emoji_id=E_ID["gear"],
        )],
    ]

    # кнопка админки для админов
    if user_id in settings.admin_id_list:
        buttons.append([InlineKeyboardButton(
            text=t("btn.admin_panel", lang),
            callback_data="admin_panel",
            style="danger",
            icon_custom_emoji_id=E_ID["lock"],
        )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Кнопка 'Назад' в главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t("btn.back", lang),
            callback_data="back_to_menu",
            style="success",
            icon_custom_emoji_id=E_ID["back"],
        )],
    ])


def get_subscription_keyboard(
    channels: list[dict], lang: str = "ru"
) -> InlineKeyboardMarkup:
    """Клавиатура подписки на каналы"""
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"{ch['title']}",
            url=ch["invite_link"],
            style="primary",
            icon_custom_emoji_id=E_ID["megaphone"],
        )])
    buttons.append([InlineKeyboardButton(
        text=t("btn.check_sub", lang),
        callback_data="check_subscription",
        style="success",
        icon_custom_emoji_id=E_ID["check"],
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_language_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора языка интерфейса"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Русский",
                callback_data="set_lang_ru",
                style="primary",
                icon_custom_emoji_id=E_ID["flag_ru"],
            ),
            InlineKeyboardButton(
                text="O'zbek",
                callback_data="set_lang_uz",
                style="primary",
                icon_custom_emoji_id=E_ID["flag_uz"],
            ),
            InlineKeyboardButton(
                text="English",
                callback_data="set_lang_en",
                style="primary",
                icon_custom_emoji_id=E_ID["flag_gb"],
            ),
        ],
    ])


def get_tts_lang_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Выбор языка озвучки (uz/ru/en)."""
    buttons = [
        [
            InlineKeyboardButton(
                text=t("btn.tts_lang_uz", lang),
                callback_data="tts_lang_uz",
                style="primary",
                icon_custom_emoji_id=E_ID["flag_uz"],
            ),
            InlineKeyboardButton(
                text=t("btn.tts_lang_ru", lang),
                callback_data="tts_lang_ru",
                style="primary",
                icon_custom_emoji_id=E_ID["flag_ru"],
            ),
            InlineKeyboardButton(
                text=t("btn.tts_lang_en", lang),
                callback_data="tts_lang_en",
                style="primary",
                icon_custom_emoji_id=E_ID["flag_gb"],
            ),
        ],
        [InlineKeyboardButton(
            text=t("btn.back", lang),
            callback_data="back_to_menu",
            style="success",
            icon_custom_emoji_id=E_ID["back"],
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_tts_voice_keyboard(
    voices: list[tuple[str, str]], lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Выбор голоса. voices: [(voice_id, label)]."""
    buttons: list[list[InlineKeyboardButton]] = []
    for voice_id, label in voices:
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"tts_voice_{voice_id}",
            style="primary",
            icon_custom_emoji_id=E_ID["music"],
        )])
    buttons.append([InlineKeyboardButton(
        text=t("btn.back", lang),
        callback_data="tts_back_to_lang",
        style="success",
        icon_custom_emoji_id=E_ID["back"],
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_tts_format_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Выбор формата: голосовое (OGG/Opus) или MP3."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("btn.format_voice", lang),
                callback_data="tts_format_voice",
                style="primary",
                icon_custom_emoji_id=E_ID["music"],
            ),
            InlineKeyboardButton(
                text=t("btn.format_mp3", lang),
                callback_data="tts_format_mp3",
                style="primary",
                icon_custom_emoji_id=E_ID["download"],
            ),
        ],
        [InlineKeyboardButton(
            text=t("btn.back", lang),
            callback_data="tts_back_to_voice",
            style="success",
            icon_custom_emoji_id=E_ID["back"],
        )],
    ])
