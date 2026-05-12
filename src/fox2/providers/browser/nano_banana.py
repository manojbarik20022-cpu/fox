"""Nano Banana через Flow (labs.google/fx/tools/flow) — бесплатно, без счётчика кредитов.

Nano Banana — это модель Google для генерации картинок. Внутри Flow есть отдельная
модель Imagen и отдельная Nano Banana; вторая в счётчик кредитов *не* попадает.
Поэтому мы переоткрываем тот же Flow-UI, выбираем в режиме Images модель
**Nano Banana**, и шлём промт. Кредитов с Flow-аккаунта не списываем.

Используем те же Flow-профили (один логин = доступ и к Imagen, и к Veo, и к Nano Banana).
Если ни одного Flow-аккаунта не добавлено, провайдер падает с понятным сообщением.
"""
from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...utils.paths import app_dir, ensure_dir
from ..base import ImageProvider, ProviderError
from .accounts import COST, BrowserAccountManager
from .flow import FlowController
from .sessions import chromium_session

log = logging.getLogger("fox2.browser.nano_banana")

DEFAULT_TIMEOUT = 90.0


def _save_debug_screenshot(page: Any, label: str) -> Path:
    path = ensure_dir(app_dir() / "debug") / f"nb_{label}_{datetime.now():%Y%m%d_%H%M%S}.png"
    with contextlib.suppress(Exception):
        page.screenshot(path=str(path), full_page=True)
    return path


def _select_model_nano_banana(page: Any) -> None:
    """Открывает дропдаун модели в режиме Images Flow и выбирает Nano Banana."""
    # Кнопка переключения модели обычно показывает текущее значение («Imagen 4», «Nano Banana»).
    for sel in [
        "button:has-text('Imagen')",
        "button:has-text('Image model')",
        "button[aria-label*='Model' i]",
        "[data-testid='model-picker']",
    ]:
        try:
            btn = page.locator(sel).first
            if btn.count():
                btn.click(timeout=3_000)
                break
        except Exception as exc:
            log.debug("model picker %r skipped: %s", sel, exc)

    # Выбираем пункт «Nano Banana» в открывшемся меню.
    for sel in [
        "[role='option']:has-text('Nano Banana')",
        "li:has-text('Nano Banana')",
        "button:has-text('Nano Banana')",
        "text=Nano Banana",
    ]:
        try:
            opt = page.locator(sel).first
            if opt.count():
                opt.click(timeout=3_000)
                log.info("Flow: модель переключена на Nano Banana")
                return
        except Exception as exc:
            log.debug("nano banana option %r skipped: %s", sel, exc)

    log.warning("Flow: не нашёл пункт Nano Banana в дропдауне — оставляю текущую модель")


class NanoBananaImage(ImageProvider):
    """Картинки через Flow с моделью Nano Banana — 0 кредитов."""

    name = "nano_banana"

    def __init__(self, accounts: BrowserAccountManager) -> None:
        self.accounts = accounts

    def generate(
        self,
        prompt: str,
        out_path: Path,
        *,
        width: int = 1024,
        height: int = 576,
        seed: int | None = None,
    ) -> Path:
        cost = COST["flow:nano_banana"]  # = 0
        # Используем те же Flow-аккаунты: cost=0, любой аккаунт подойдёт даже исчерпанный.
        account = self.accounts.acquire("flow", cost)
        log.info("Nano Banana: использую Flow-аккаунт %s (cost=0)", account.name)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with chromium_session(account.profile_dir, headless=False) as (_ctx, page):
            ctrl = FlowController(page)
            ctrl.navigate()
            ctrl.ensure_project()
            ctrl.select_mode("image")
            _select_model_nano_banana(page)
            count_before = ctrl.submit_prompt(prompt, timeout=DEFAULT_TIMEOUT)
            try:
                new_asset = ctrl.wait_for_new_asset(count_before, timeout=DEFAULT_TIMEOUT)
            except ProviderError:
                _save_debug_screenshot(page, "wait_timeout")
                raise
            ctrl.download_asset(new_asset, out_path, kind="image")

        # Кредиты не списываем — но вызовем consume(0) ради единого лога.
        self.accounts.consume(account, cost)
        return out_path
