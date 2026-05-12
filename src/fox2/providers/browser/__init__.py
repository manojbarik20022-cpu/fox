"""Браузерная автоматизация (Playwright + координатный fallback).

Используется для бесплатных вкладок нейросетей: Nano Banana (Gemini), Grok Imagine,
Google Flow (Veo3), Google AI Studio (TTS), и т.д. — где нет публичного API.

В MVP — это каркас:
- BrowserProfileManager: управление профилями Playwright (по одному на аккаунт).
- CoordinateAutomator: универсальный кликер по координатам (как в оригинальном Fox2).

Подключение конкретных сайтов — это уже надстройка в UI вкладок "Браузер" и "Озвучка Веб".
"""
from .accounts import (
    COST,
    DAILY_LIMITS,
    AccountExhausted,
    BrowserAccount,
    BrowserAccountManager,
)
from .coordinates import CoordinateAutomator
from .profiles import BrowserProfileManager
from .sessions import (
    LOGIN_URLS,
    PlaywrightUnavailable,
    chromium_session,
    login_url_for,
    open_for_login,
)

__all__ = [
    "COST",
    "DAILY_LIMITS",
    "LOGIN_URLS",
    "AccountExhausted",
    "BrowserAccount",
    "BrowserAccountManager",
    "BrowserProfileManager",
    "CoordinateAutomator",
    "PlaywrightUnavailable",
    "chromium_session",
    "login_url_for",
    "open_for_login",
]
