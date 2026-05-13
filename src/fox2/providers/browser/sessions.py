"""Запуск Playwright Chromium с конкретным профилем (для логина и работы).

Используется UI вкладки «Браузер» (открыть окно для ручного логина) и провайдерами
Flow/Grok/Nano Banana (фоновая автоматизация под уже залогиненным профилем).

Google детектирует «обычный» Playwright-Chromium и блокирует вход с ошибкой
«Этот браузер или приложение небезопасны». Чтобы обойти:

* Подменяем user-agent на реальный Chrome на Windows.
* Прячем ``navigator.webdriver`` и бренд-стринг «Chrome for Testing»
  в ``navigator.userAgentData.brands`` через init-script.
* Отключаем automation-флаги в ``ignore_default_args``.

НАСТОЯЩИЙ Google Chrome из Program Files НЕ используем — Chrome
использует single-instance behaviour, и если у пользователя уже открыт обычный
Chrome, Playwright не может подключиться по CDP к новому процессу
(github.com/microsoft/playwright/issues/18046).
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
#
# NB: НЕ подменяем navigator.userAgentData — попытка подмены брендов
# приводит к зависанию Google login на этапе «Далее» после ввода почты
# (Google детектит inconsistency между UA и подменённым userAgentData).
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
# --disable-blink-features=AutomationControlled — ключевой стелс-флаг, без
# которого Google login детектит автоматизацию (даже с init-script, который
# подменяет navigator.webdriver). Chrome 140+ показывает из-за него жёлтую
# полоску предупреждения — это known trade-off.
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-default-browser-check",
    "--no-first-run",
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
    """Запустить bundled Playwright-Chromium с навешенными стелс-флагами и init-script."""
    common_kwargs = {
        "user_data_dir": profile_dir,
        "headless": headless,
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "accept_downloads": True,
        "user_agent": DEFAULT_UA,
        "args": STEALTH_ARGS,
        # Playwright по умолчанию добавляет --enable-automation — палит автоматизацию,
        # и Google login после этого блокирует вход с «небезопасный браузер».
        # NB: --no-sandbox оставляем (Playwright добавит его сам), хоть Chrome 140+
        # и показывает жёлтую полоску. Без --no-sandbox Google всё равно блокирует
        # вход — этот стелс-сценарий (d429f55) был проверен пользователем как
        # рабочий, а вариант с убиранием --no-sandbox — как сломанный.
        "ignore_default_args": ["--enable-automation"],
    }

    # Запускаем bundled Chromium (брендирован как «Chrome for Testing» на странице about:).
    # Системный Chrome из Program Files НЕ используем: если пользователь уже
    # запустил обычный Chrome, Playwright не может подключиться по CDP к новому
    # процессу (Chrome отдаёт single-instance lock уже запущенному).
    # Детали: github.com/microsoft/playwright/issues/18046
    ctx = p.chromium.launch_persistent_context(**common_kwargs)
    log.info("Запущен Playwright Chromium")

    # Применяем глубокие стелс-патчи через playwright-stealth (~20 evasions:
    # WebGL vendor, audio context, navigator.permissions, sec-ch-ua, navigator.plugins,
    # iframe contentWindow, chrome.runtime, и т. д.). Это куда серьёзнее, чем
    # один init-script ниже.
    try:
        from playwright_stealth import Stealth  # type: ignore[import-not-found]

        # chrome_runtime=False оставляем дефолт (включение ломает некоторые сайты),
        # остальные evasions включены по умолчанию.
        Stealth(
            navigator_languages_override=("ru-RU", "ru"),
            navigator_platform_override="Win32",
            navigator_user_agent_override=DEFAULT_UA,
        ).apply_stealth_sync(ctx)
        log.info("playwright-stealth применён к контексту")
    except ImportError:
        log.warning("playwright-stealth не установлен — используем только базовый init-script")
    except Exception as exc:
        log.warning("playwright-stealth не применился: %s", exc)

    # Дополнительный fallback-init-script (на случай если stealth недоступен).
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


# ---- Импорт cookies из обычного браузера (план В, если Google login заблокирован) ----

# Список поддерживаемых браузеров и их функции-загрузчики из browser_cookie3.
SUPPORTED_BROWSERS = ("chrome", "edge", "brave", "opera", "chromium", "vivaldi", "firefox")

# Домены, которые нужны для Flow/Grok/Gemini.
GOOGLE_COOKIE_DOMAINS = (
    ".google.com",
    ".labs.google",
    ".accounts.google.com",
)
GROK_COOKIE_DOMAINS = (".grok.com", ".x.ai", ".x.com")


class CookieImportError(RuntimeError):
    """Ошибка при импорте cookies из обычного браузера."""


# Имена SQLite-файлов с cookies для разных движков.
# Chrome 96+ переехал на Network/Cookies; старый Chrome и Edge/Brave используют просто Cookies.
# Firefox держит в cookies.sqlite.
COOKIE_FILE_PATTERNS = (
    "Network/Cookies",  # Chromium 96+
    "Cookies",           # старый Chromium / Edge / Brave
    "cookies.sqlite",    # Firefox
)


def _resolve_cookie_file(path: str | Path) -> str:
    """Если ``path`` — файл, вернёт как есть. Если папка — ищет внутри SQLite-файл
    cookies (Network/Cookies, Cookies или cookies.sqlite). Поддерживает Chrome Portable
    (где cookies лежат в ``Data/profile/Default/Network/Cookies``).

    Поднимает ``CookieImportError`` если ничего не нашёл.
    """
    p = Path(path)
    if p.is_file():
        return str(p)
    if not p.exists():
        raise CookieImportError(f"Путь не существует: {p}")

    # Кандидаты в порядке убывания приоритета: Default-профиль > любой другой профиль.
    candidates: list[Path] = []
    for pattern in COOKIE_FILE_PATTERNS:
        # 1) Прямо внутри указанной папки.
        direct = p / pattern
        if direct.is_file():
            candidates.append(direct)
        # 2) Внутри подпапок профиля: Data/profile/Default/<pattern>, profile/Default/<pattern>,
        #    User Data/Default/<pattern>, и т. п.
        for prof in p.rglob("Default"):
            if not prof.is_dir():
                continue
            cf = prof / pattern
            if cf.is_file():
                candidates.append(cf)
        # 3) И вообще все Network/Cookies внутри (Chrome multi-profile + Chrome Portable variants).
        for cf in p.rglob(pattern.split("/")[-1] if "/" in pattern else pattern):
            if cf.is_file() and cf not in candidates:
                # Проверяем, что родительская папка — это профиль (Default или Profile *).
                parent_name = cf.parent.name
                grandparent = cf.parent.parent.name if cf.parent.parent else ""
                if (
                    parent_name == "Network" and grandparent.startswith(("Default", "Profile"))
                ) or parent_name.startswith(("Default", "Profile")):
                    candidates.append(cf)

    # Дедуплицируем, сохраняя порядок.
    seen: set[Path] = set()
    uniq: list[Path] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    if not uniq:
        raise CookieImportError(
            f"В папке {p} не нашёл файл cookies. Ожидал Default/Network/Cookies "
            f"(Chrome 96+) или Default/Cookies (старый Chrome / Edge / Brave) "
            f"или cookies.sqlite (Firefox)."
        )

    log.info("Auto-resolved cookies file: %s (из %d кандидатов)", uniq[0], len(uniq))
    return str(uniq[0])


def _resolve_key_file(cookie_file: str | Path) -> str | None:
    """Найти ``Local State`` рядом с Cookies-файлом (для расшифровки DPAPI ключа
    Chromium на Windows). Возвращает None если не нашёл.

    Структура Chrome Portable: ``<root>/Data/profile/Default/Network/Cookies`` →
    ``<root>/Data/profile/Local State`` (поднимаемся на 3 уровня).
    Стандартный Chrome: ``User Data/Default/Network/Cookies`` →
    ``User Data/Local State`` (тоже 3 уровня).
    """
    p = Path(cookie_file).parent
    for _ in range(5):
        cand = p / "Local State"
        if cand.is_file():
            return str(cand)
        if p.parent == p:
            break
        p = p.parent
    return None


def _convert_cookie(c: Any) -> dict[str, Any]:
    """``http.cookiejar.Cookie`` → формат Playwright ``add_cookies``."""
    same_site = "Lax"
    rest = getattr(c, "_rest", None) or {}
    raw_ss = rest.get("SameSite") or rest.get("sameSite")
    if isinstance(raw_ss, str):
        normalized = raw_ss.capitalize()
        if normalized in ("Strict", "Lax", "None"):
            same_site = normalized

    expires = c.expires if c.expires else -1
    # browser_cookie3 ставит rest={"HttpOnly": ""} (пустая строка) когда флаг включён,
    # и {} когда выключен. Поэтому проверяем именно наличие ключа, не значение.
    http_only = "HttpOnly" in rest or "httpOnly" in rest
    return {
        "name": c.name,
        "value": c.value or "",
        "domain": c.domain,
        "path": c.path or "/",
        "expires": float(expires),
        "httpOnly": http_only,
        "secure": bool(c.secure),
        "sameSite": same_site,
    }


def _load_browser_cookies(
    browser: str,
    *,
    cookie_file: str | None = None,
    domains: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Прочитать cookies из обычного браузера через browser_cookie3."""
    try:
        import browser_cookie3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise CookieImportError(
            "Модуль browser_cookie3 не установлен. Перезапусти run.bat — "
            "он его дотянет, либо вручную: pip install browser-cookie3"
        ) from exc

    browser = browser.lower()
    if browser not in SUPPORTED_BROWSERS:
        raise CookieImportError(f"Неизвестный браузер: {browser}")

    loader = getattr(browser_cookie3, browser, None)
    if loader is None:
        raise CookieImportError(f"browser_cookie3 не поддерживает {browser}")

    # Если указан путь и это папка (Chrome Portable) — авто-резолвим до Cookies-файла.
    key_file: str | None = None
    if cookie_file:
        cookie_file = _resolve_cookie_file(cookie_file)
        # Для chromium-форков нужен Local State (DPAPI-key для расшифровки cookies).
        # Для firefox — не нужно.
        if browser != "firefox":
            key_file = _resolve_key_file(cookie_file)
            if key_file is None:
                log.warning(
                    "Не нашёл Local State рядом с %s — будет попытка расшифровки "
                    "стандартным ключом (для портативного Chrome это может не сработать)",
                    cookie_file,
                )

    domains = domains or ("",)  # пустая строка = все домены
    seen: set[tuple[str, str, str]] = set()
    cookies: list[dict[str, Any]] = []
    loader_kwargs: dict[str, Any] = {"cookie_file": cookie_file}
    if key_file is not None:
        loader_kwargs["key_file"] = key_file
    for domain in domains:
        try:
            cj = loader(domain_name=domain, **loader_kwargs)
        except Exception as exc:
            raise CookieImportError(
                f"Не удалось прочитать cookies из {browser} "
                f"(домен {domain or '*'}): {exc}. "
                "Закрой все окна браузера перед импортом."
            ) from exc
        for c in cj:
            key = (c.name, c.domain, c.path or "/")
            if key in seen:
                continue
            seen.add(key)
            try:
                cookies.append(_convert_cookie(c))
            except Exception as exc:
                log.debug("пропускаем cookie %s: %s", c.name, exc)
    return cookies


def import_cookies_into_profile(
    profile_dir: str | Path,
    *,
    browser: str = "chrome",
    cookie_file: str | None = None,
    domains: tuple[str, ...] | None = None,
) -> int:
    """Импортирует Google/Grok cookies из обычного браузера в Playwright-профиль.

    Возвращает количество импортированных cookies. После успешного импорта
    Playwright-профиль будет считать пользователя залогиненным — никакая
    страница входа Google не понадобится.

    ``browser`` — chrome/edge/brave/opera/chromium/vivaldi/firefox.
    ``cookie_file`` — кастомный путь к SQLite-файлу cookies (для Chrome Portable
    указать ``<portable>/Data/profile/Default/Cookies`` или ``...Network/Cookies``).
    ``domains`` — кортеж доменов (по умолчанию Google + labs.google).
    """
    if domains is None:
        domains = GOOGLE_COOKIE_DOMAINS

    cookies = _load_browser_cookies(browser, cookie_file=cookie_file, domains=domains)
    if not cookies:
        raise CookieImportError(
            f"В {browser} не нашлось ни одной cookie для доменов {domains}. "
            "Проверь, что ты залогинен в Google в этом браузере."
        )

    profile_dir = Path(profile_dir)
    ensure_dir(profile_dir)
    # Через headless-сессию Playwright проставляем cookies в persistent профиль.
    # На закрытии context'а cookies сохраняются в user_data_dir/Default/Cookies.
    with chromium_session(profile_dir, headless=True) as (ctx, _page):
        ctx.add_cookies(cookies)  # type: ignore[arg-type]
    log.info("Импортировано %d cookies из %s в %s", len(cookies), browser, profile_dir)
    return len(cookies)


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
