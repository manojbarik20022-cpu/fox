"""Фабрика провайдеров картинок."""
from __future__ import annotations

from ...core.settings import AppSettings
from ..base import ImageProvider, ProviderError, ProviderNotConfigured
from ..browser import BrowserAccountManager
from .pollinations import PollinationsImage
from .sd_webui import SDWebUIImage

KNOWN_IMAGE = ("pollinations", "sd_webui", "flow_browser", "grok_browser", "nano_banana")


def make_image_provider(name: str, settings: AppSettings) -> ImageProvider:
    name = (name or "").lower().strip()
    if name == "pollinations":
        return PollinationsImage(model=settings.pollinations_model)
    if name == "sd_webui":
        return SDWebUIImage(base_url=settings.sd_webui_base_url)
    if name == "flow_browser":
        try:
            from ..browser.flow import FlowImage
        except ImportError as exc:
            raise ProviderError(
                "Playwright не установлен. Запусти run.bat/run.sh, он поставит Chromium."
            ) from exc
        return FlowImage(accounts=BrowserAccountManager())
    if name == "grok_browser":
        try:
            from ..browser.grok import GrokImage
        except ImportError as exc:
            raise ProviderError(
                "Playwright не установлен. Запусти run.bat/run.sh, он поставит Chromium."
            ) from exc
        return GrokImage(accounts=BrowserAccountManager())
    if name == "nano_banana":
        try:
            from ..browser.nano_banana import NanoBananaImage
        except ImportError as exc:
            raise ProviderError(
                "Playwright не установлен. Запусти run.bat/run.sh, он поставит Chromium."
            ) from exc
        return NanoBananaImage(accounts=BrowserAccountManager())
    raise ProviderNotConfigured(
        f"Неизвестный image-провайдер: {name!r}. Известные: {', '.join(KNOWN_IMAGE)}."
    )
