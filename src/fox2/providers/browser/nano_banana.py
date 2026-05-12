"""Nano Banana через Gemini-чат (gemini.google.com) — бесплатно, без счётчика кредитов.

Принцип: на gemini.google.com Gemini сам умеет рисовать картинки (модель «Nano Banana»
встроена в обычный чат, без отдельной подписки). Мы шлём промт, ждём картинку в ответе,
скачиваем blob.

Лимит — мягкий rate-limit Google, не «кредитный». BrowserAccountManager для этого
провайдера не учитывает кредиты (DAILY_LIMIT = 0 = ∞).
"""
from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ...utils.paths import app_dir, ensure_dir
from ..base import ImageProvider, ProviderError
from .accounts import COST, BrowserAccountManager
from .sessions import chromium_session

log = logging.getLogger("fox2.browser.nano_banana")

GEMINI_URL = "https://gemini.google.com/app"
DEFAULT_TIMEOUT = 90.0


def _save_debug_screenshot(page: Any, label: str) -> Path:
    path = ensure_dir(app_dir() / "debug") / f"nb_{label}_{datetime.now():%Y%m%d_%H%M%S}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception as exc:
        log.warning("nb screenshot fail: %s", exc)
    return path


class NanoBananaImage(ImageProvider):
    """Картинки через Gemini-чат (модель Nano Banana встроена)."""

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
        cost = COST["nano_banana:image"]  # = 0
        account = self.accounts.acquire("nano_banana", cost)
        log.info("Nano Banana: аккаунт %s", account.name)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with chromium_session(account.profile_dir, headless=False) as (_ctx, page):
            page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60_000)
            with contextlib.suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=15_000)

            # Поле ввода — обычно contenteditable div, либо textarea.
            textbox = None
            for sel in [
                "div[contenteditable='true']",
                "textarea[placeholder*='Ask' i]",
                "textarea",
            ]:
                try:
                    t = page.locator(sel).first
                    if t.count():
                        textbox = t
                        break
                except Exception:
                    continue
            if textbox is None:
                _save_debug_screenshot(page, "no_textbox")
                raise ProviderError("Gemini: не нашёл поле ввода.")

            # Пользователю не обязательно явно просить «нарисуй», Gemini понимает «Generate an image of …».
            request_text = f"Generate an image of: {prompt}" if prompt else "Generate an image."
            count_before = page.locator("img").count()
            textbox.click()
            textbox.fill(request_text)
            textbox.press("Enter")

            # Ждём новую картинку в потоке ответа.
            deadline = time.time() + DEFAULT_TIMEOUT
            asset = None
            while time.time() < deadline:
                imgs = page.locator("img")
                if imgs.count() > count_before:
                    # Берём самую последнюю (новую).
                    asset = imgs.nth(imgs.count() - 1)
                    src = asset.get_attribute("src") or ""
                    # Игнорируем мелкие иконки UI: ждём «blob:» или https с разумным URL.
                    if src.startswith("blob:") or "googleusercontent" in src:
                        break
                time.sleep(2.0)
            if asset is None:
                _save_debug_screenshot(page, "wait_timeout")
                raise ProviderError(
                    f"Nano Banana: за {DEFAULT_TIMEOUT:.0f}с картинка не появилась."
                )

            src = asset.get_attribute("src") or ""
            if src.startswith("blob:"):
                data = page.evaluate(
                    """async (url) => {
                        const r = await fetch(url);
                        const buf = await r.arrayBuffer();
                        return Array.from(new Uint8Array(buf));
                    }""",
                    src,
                )
                out_path.write_bytes(bytes(data))
            else:
                resp = page.request.get(src, timeout=60_000)
                out_path.write_bytes(resp.body())

        self.accounts.consume(account, cost)  # = 0, для красоты в логе
        return out_path
