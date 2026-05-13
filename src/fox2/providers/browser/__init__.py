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
    GOOGLE_COOKIE_DOMAINS,
    GROK_COOKIE_DOMAINS,
    LOGIN_URLS,
    SUPPORTED_BROWSERS,
    CookieImportError,
    PlaywrightUnavailable,
    chromium_session,
    import_cookies_into_profile,
    login_url_for,
    open_for_login,
)

__all__ = [
    "COST",
    "DAILY_LIMITS",
    "GOOGLE_COOKIE_DOMAINS",
    "GROK_COOKIE_DOMAINS",
    "LOGIN_URLS",
    "SUPPORTED_BROWSERS",
    "AccountExhausted",
    "BrowserAccount",
    "BrowserAccountManager",
    "BrowserProfileManager",
    "CookieImportError",
    "CoordinateAutomator",
    "PlaywrightUnavailable",
    "chromium_session",
    "import_cookies_into_profile",
    "login_url_for",
    "open_for_login",
]
