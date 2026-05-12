"""Фабрика видео-провайдеров."""
from __future__ import annotations

from ...core.settings import AppSettings
from ..base import ProviderError, ProviderNotConfigured, VideoProvider
from ..browser import BrowserAccountManager
from .local_kenburns import LocalKenBurnsVideo

KNOWN_VIDEO = ("ffmpeg", "flow_browser", "grok_browser")


def make_video_provider(name: str, settings: AppSettings) -> VideoProvider:
    name = (name or "").lower().strip()
    if name == "ffmpeg":
        return LocalKenBurnsVideo()
    if name == "flow_browser":
        try:
            from ..browser.flow import FlowVideo
        except ImportError as exc:
            raise ProviderError(
                "Playwright не установлен. Запусти run.bat/run.sh, он поставит Chromium."
            ) from exc
        return FlowVideo(accounts=BrowserAccountManager())
    if name == "grok_browser":
        try:
            from ..browser.grok import GrokVideo
        except ImportError as exc:
            raise ProviderError(
                "Playwright не установлен. Запусти run.bat/run.sh, он поставит Chromium."
            ) from exc
        return GrokVideo(accounts=BrowserAccountManager())
    raise ProviderNotConfigured(
        f"Неизвестный video-провайдер: {name!r}. Известные: {', '.join(KNOWN_VIDEO)}."
    )
