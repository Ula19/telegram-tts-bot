"""Утилиты и вспомогательные функции"""


def truncate_text(text: str, max_len: int = 4096) -> str:
    """Обрезает текст до максимальной длины"""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def is_empty_text(text: str) -> bool:
    """Проверяет, является ли текст пустым или состоящим только из пробелов"""
    return not text or not text.strip()
