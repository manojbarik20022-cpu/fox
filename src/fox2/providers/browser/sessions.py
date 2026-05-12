"""Запуск Playwright Chromium с конкретным профилем (для логина и работы).

Используется UI вкладки «Браузер» (открыть окно для ручного логина) и провайдерами
Flow/Grok/Nano Banana (фоновая автоматизация под уже залогиненным профилем).
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...utils.paths import ensure_dir

if TYPE_CHECKING:  # pragma: no cover - только для type checker
    pass

log = logging.getLogger("fox2.browser.sessions")


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


@contextmanager
def chromium_session(
    profile_dir: str | Path,
    *,
    headless: bool = False,
    viewport: tuple[int, int] = (1280, 800),
):
    """Контекстный менеджер: возвращает (browser_context, page) для Playwright Chromium.

    ``profile_dir`` — persistent user-data dir (cookies/local storage сохраняются между
    запусками). Если папки нет — создаётся.
    """
    profile_dir = Path(profile_dir)
    ensure_dir(profile_dir)
    sync_playwright = _import_playwright()
    with sync_playwright() as p:  # type: ignore[misc]
        ctx = p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            viewport={"width": viewport[0], "height": viewport[1]},
            accept_downloads=True,
        )
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
    "flow": "https://labs.google/flow",
    "grok": "https://grok.com/",
    "nano_banana": "https://gemini.google.com/app",
}


def login_url_for(provider: str) -> str:
    return LOGIN_URLS.get(provider, "about:blank")
