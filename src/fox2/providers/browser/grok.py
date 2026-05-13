"""Браузерные провайдеры Grok (grok.com): картинки через Grok Imagine, видео при наличии.

Grok доступен бесплатно ограниченно (без подписки X Premium есть ежедневный лимит на
картинки/видео). Мы считаем условные «кредиты» так же, как у Flow, чтобы ротация
аккаунтов работала единообразно: 1 = картинка, 5 = видео.

Селекторы — best-effort. На ошибке провайдер сохраняет debug-скриншот.
"""
from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ...utils.paths import app_dir, ensure_dir
from ..base import ImageProvider, ProviderError, VideoProvider
from .accounts import COST, BrowserAccountManager
from .sessions import chromium_session

log = logging.getLogger("fox2.browser.grok")

GROK_URL = "https://grok.com/"
DEFAULT_IMAGE_TIMEOUT = 90.0
DEFAULT_VIDEO_TIMEOUT = 240.0


def _save_debug_screenshot(page: Any, label: str) -> Path:
    path = ensure_dir(app_dir() / "debug") / f"grok_{label}_{datetime.now():%Y%m%d_%H%M%S}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception as exc:
        log.warning("Не удалось сохранить скриншот %s: %s", path, exc)
    return path


class GrokController:
    def __init__(self, page: Any) -> None:
        self.page = page

    def navigate(self) -> None:
        log.info("Grok: открываю %s", GROK_URL)
        self.page.goto(GROK_URL, wait_until="domcontentloaded", timeout=60_000)
        with contextlib.suppress(Exception):
            self.page.wait_for_load_state("networkidle", timeout=15_000)

    def select_mode_image(self) -> None:
        """Переключает Grok в режим картинок (Imagine)."""
        page = self.page
        for sel in [
            "button:has-text('Imagine')",
            "[role='tab']:has-text('Imagine')",
            "button:has-text('Image')",
            "a[href*='imagine' i]",
        ]:
            try:
                el = page.locator(sel).first
                if el.count():
                    el.click(timeout=3_000)
                    return
            except Exception:
                continue
        log.debug("Grok: image mode toggle не найден — возможно режим уже активен.")

    def select_mode_video(self) -> None:
        page = self.page
        for sel in [
            "button:has-text('Video')",
            "[role='tab']:has-text('Video')",
            "button:has-text('Grok Video')",
        ]:
            try:
                el = page.locator(sel).first
                if el.count():
                    el.click(timeout=3_000)
                    return
            except Exception:
                continue
        log.debug("Grok: video mode toggle не найден.")

    def submit_prompt(self, prompt: str) -> int:
        page = self.page
        before = page.locator("img[src*='blob'], video, [data-result]").count()
        textbox = None
        for sel in [
            "textarea[placeholder*='Ask Grok' i]",
            "textarea",
            "[contenteditable='true']",
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
            raise ProviderError("Grok: не нашёл поле ввода.")
        textbox.click()
        textbox.fill(prompt)

        # Enter обычно отправляет промт.
        textbox.press("Enter")
        log.info("Grok: промт отправлен (%s)", prompt[:60])
        return before

    def wait_for_new_asset(self, count_before: int, *, timeout: float) -> Any:
        page = self.page
        deadline = time.time() + timeout
        while time.time() < deadline:
            assets = page.locator("img[src*='blob'], img[src*='https'], video")
            count = assets.count()
            if count > count_before:
                return assets.last
            time.sleep(2.0)
        _save_debug_screenshot(page, "wait_timeout")
        raise ProviderError(
            f"Grok: за {timeout:.0f}с не появилось результата. "
            "Возможно дневной лимит исчерпан."
        )

    def download_asset(self, asset_locator: Any, out_path: Path, *, kind: str) -> Path:
        page = self.page
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            src = asset_locator.get_attribute("src", timeout=3_000)
            if src and src.startswith("blob:"):
                data = page.evaluate(
                    """async (url) => {
                        const r = await fetch(url);
                        const buf = await r.arrayBuffer();
                        const arr = new Uint8Array(buf);
                        return Array.from(arr);
                    }""",
                    src,
                )
                out_path.write_bytes(bytes(data))
                return out_path
            if src:
                resp = page.request.get(src, timeout=60_000)
                out_path.write_bytes(resp.body())
                return out_path
        except Exception as exc:
            log.warning("Grok: download fallback не сработал: %s", exc)
        _save_debug_screenshot(page, f"download_failed_{kind}")
        raise ProviderError(
            f"Grok: не удалось скачать {kind}. Смотри debug-скриншот."
        )


class GrokImage(ImageProvider):
    name = "grok_browser"

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
        cost = COST["grok:image"]
        account = self.accounts.acquire("grok", cost)
        log.info(
            "Grok image: использую аккаунт %s (осталось %d)",
            account.name, account.credits_remaining(),
        )
        with chromium_session(account.profile_dir, headless=False) as (_ctx, page):
            ctrl = GrokController(page)
            ctrl.navigate()
            ctrl.select_mode_image()
            count_before = ctrl.submit_prompt(prompt)
            asset = ctrl.wait_for_new_asset(count_before, timeout=DEFAULT_IMAGE_TIMEOUT)
            ctrl.download_asset(asset, out_path, kind="image")
        self.accounts.consume(account, cost)
        return out_path


class GrokVideo(VideoProvider):
    name = "grok_browser"

    def __init__(self, accounts: BrowserAccountManager) -> None:
        self.accounts = accounts

    def animate(
        self,
        image_path: Path,
        out_path: Path,
        *,
        prompt: str = "",
        duration: float = 5.0,
    ) -> Path:
        cost = COST["grok:video"]
        account = self.accounts.acquire("grok", cost)
        log.info(
            "Grok video: использую аккаунт %s (осталось %d)",
            account.name, account.credits_remaining(),
        )
        with chromium_session(account.profile_dir, headless=False) as (_ctx, page):
            ctrl = GrokController(page)
            ctrl.navigate()
            ctrl.select_mode_video()
            count_before = ctrl.submit_prompt(prompt or "cinematic shot")
            asset = ctrl.wait_for_new_asset(count_before, timeout=DEFAULT_VIDEO_TIMEOUT)
            ctrl.download_asset(asset, out_path, kind="video")
        self.accounts.consume(account, cost)
        return out_path
