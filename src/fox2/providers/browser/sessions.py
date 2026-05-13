"""Запуск Playwright Chromium с конкретным профилем (для логина и работы).

Используется UI вкладки «Браузер» (открыть окно для ручного логина) и провайдерами
Flow/Grok/Nano Banana (фоновая автоматизация под уже залогиненным профилем).

Google детектирует «обычный» Playwright-Chromium и блокирует вход с ошибкой
«Этот браузер или приложение небезопасны». Чтобы обойти:

1. **Сначала пробуем системный Google Chrome** (``channel="chrome"``) — Google
   к нему не придирается. Если не установлен — fallback на bundled Chromium.
2. **Стелс-флаги** на bundled Chromium: отключаем ``--enable-automation``,
   убираем ``navigator.webdriver``, ставим обычный user-agent.

Этого достаточно для прохождения Google login без перехода на полноценный
``playwright-stealth``.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ...utils.paths import ensure_dir

log = logging.getLogger("fox2.browser.sessions")


# Реалистичный user-agent (последний стабильный Chrome). Playwright по умолчанию
# использует HeadlessChrome/<ver> — это сразу палит автоматизацию.
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Скрипт, который выполняется ДО первого скрипта на странице.
# Прячет navigator.webdriver и навешивает «человеческие» свойства, по которым
# Google детектит автоматизацию.
STEALTH_INIT_SCRIPT = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
}
"""

# Аргументы Chromium, которые отключают automation-баннеры/флаги.
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-default-browser-check",
    "--no-first-run",
    "--disable-features=IsolateOrigins,site-per-process",
]


class PlaywrightUnavailable(RuntimeError):
    """Playwright не установлен или не удалось загрузить Chromium."""


def _import_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as exc:
        raise PlaywrightUnavailable(
            "Модуль playwright не установлен. Установи: pip install -e \".[browser]\" "
            "и затем: python -m playwright install chromium"
        ) from exc
    return sync_playwright


def _launch_persistent(p: Any, profile_dir: str, *, headless: bool, viewport: tuple[int, int]) -> Any:
    """Пытается запустить системный Chrome, при неудаче — bundled Chromium со стелс-флагами.

    В обоих случаях навешивает stealth init-script + реалистичный user-agent +
    отключает automation-флаги.
    """
    common_kwargs = {
        "user_data_dir": profile_dir,
        "headless": headless,
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "accept_downloads": True,
        "user_agent": DEFAULT_UA,
        "args": STEALTH_ARGS,
        "ignore_default_args": ["--enable-automation"],
    }

    # 1. Попытка: системный Google Chrome.
    try:
        ctx = p.chromium.launch_persistent_context(channel="chrome", **common_kwargs)
        log.info("Запущен системный Google Chrome (channel=chrome)")
    except Exception as exc:
        log.info("Системный Chrome недоступен (%s) — fallback на bundled Chromium", exc)
        ctx = p.chromium.launch_persistent_context(**common_kwargs)

    # Скрываем navigator.webdriver и т. п. на всех будущих страницах.
    try:
        ctx.add_init_script(STEALTH_INIT_SCRIPT)
    except Exception as exc:
        log.warning("Не удалось установить stealth init script: %s", exc)

    return ctx


@contextmanager
def chromium_session(
    profile_dir: str | Path,
    *,
    headless: bool = False,
    viewport: tuple[int, int] = (1280, 800),
):
    """Контекстный менеджер: возвращает (browser_context, page) для Playwright Chromium.

    ``profile_dir`` — persistent user-data dir (cookies/local storage сохраняются между
    запусками). Если папки нет — создаётся. Применяются стелс-флаги, чтобы Google
    разрешил логин.
    """
    profile_dir = Path(profile_dir)
    ensure_dir(profile_dir)
    sync_playwright = _import_playwright()
    with sync_playwright() as p:  # type: ignore[misc]
        ctx = _launch_persistent(p, str(profile_dir), headless=headless, viewport=viewport)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            yield ctx, page
        finally:
            try:
                ctx.close()
            except Exception as exc:
                log.debug("ctx.close() ignored: %s", exc)


def open_for_login(
    profile_dir: str | Path,
    login_url: str,
    *,
    on_done: Callable[[], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> threading.Thread:
    """Запускает Chromium в *отдельном потоке* и ведёт на ``login_url``.

    Блокируется до тех пор, пока пользователь не закроет окно браузера. После
    закрытия cookies/localStorage уже сохранены в ``profile_dir`` благодаря
    persistent-context. Вызывает ``on_done`` (или ``on_error``) в потоке Playwright.
    Возвращает запущенный ``threading.Thread`` (демон).
    """

    def _run() -> None:
        try:
            with chromium_session(profile_dir, headless=False) as (ctx, page):
                page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
                # Ждём, пока пользователь закроет ВСЕ страницы — это сигнал, что он завершил вход.
                while True:
                    open_pages = [pg for pg in ctx.pages if not pg.is_closed()]
                    if not open_pages:
                        break
                    time.sleep(0.5)
            if on_done:
                on_done()
        except Exception as exc:
            log.exception("Ошибка при открытии окна логина")
            if on_error:
                on_error(exc)

    thread = threading.Thread(target=_run, daemon=True, name="fox2-browser-login")
    thread.start()
    return thread


# Стандартные URL для входа.
LOGIN_URLS: dict[str, str] = {
    "flow": "https://labs.google/fx/tools/flow",
    "grok": "https://grok.com/",
}


def login_url_for(provider: str) -> str:
    return LOGIN_URLS.get(provider, "about:blank")
