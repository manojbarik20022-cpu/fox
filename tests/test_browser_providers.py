"""Smoke-тесты браузерных провайдеров и их регистрации в фабриках.

Реально открывать Chromium и ходить в Flow/Grok/Gemini в этих тестах не нужно — это
делать в живом GUI. Тут проверяем:

* провайдеры импортируются без ошибок;
* фабрика отдаёт нужный тип по имени;
* если Playwright не установлен, фабрика поднимает ProviderError с понятным
  сообщением (а не падает где-то в недрах);
* AccountExhausted прорастает наружу из провайдера.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fox2.core.settings import AppSettings
from fox2.providers.base import ImageProvider, ProviderError, VideoProvider
from fox2.providers.browser import AccountExhausted, BrowserAccountManager
from fox2.providers.browser.flow import FlowImage, FlowVideo
from fox2.providers.browser.grok import GrokImage, GrokVideo
from fox2.providers.browser.nano_banana import NanoBananaImage
from fox2.providers.image.factory import make_image_provider
from fox2.providers.video.factory import make_video_provider


class FactoryDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = AppSettings()

    def test_image_factory_returns_flow(self) -> None:
        provider = make_image_provider("flow_browser", self.settings)
        self.assertIsInstance(provider, FlowImage)
        self.assertIsInstance(provider, ImageProvider)

    def test_image_factory_returns_grok(self) -> None:
        provider = make_image_provider("grok_browser", self.settings)
        self.assertIsInstance(provider, GrokImage)

    def test_image_factory_returns_nano_banana(self) -> None:
        provider = make_image_provider("nano_banana", self.settings)
        self.assertIsInstance(provider, NanoBananaImage)

    def test_video_factory_returns_flow(self) -> None:
        provider = make_video_provider("flow_browser", self.settings)
        self.assertIsInstance(provider, FlowVideo)
        self.assertIsInstance(provider, VideoProvider)

    def test_video_factory_returns_grok(self) -> None:
        provider = make_video_provider("grok_browser", self.settings)
        self.assertIsInstance(provider, GrokVideo)


class AccountExhaustionFlowTests(unittest.TestCase):
    """Проверяем, что когда нет аккаунтов — провайдер падает понятным образом
    (а не где-то на этапе Playwright)."""

    def test_flow_image_raises_when_no_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BrowserAccountManager(root=Path(tmp))
            provider = FlowImage(accounts=mgr)
            with self.assertRaises(AccountExhausted):
                provider.generate("test", Path(tmp) / "out.png")

    def test_flow_video_raises_when_no_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BrowserAccountManager(root=Path(tmp))
            provider = FlowVideo(accounts=mgr)
            with self.assertRaises(AccountExhausted):
                provider.animate(Path(tmp) / "fake.png", Path(tmp) / "out.mp4", prompt="x")

    def test_grok_image_raises_when_no_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BrowserAccountManager(root=Path(tmp))
            provider = GrokImage(accounts=mgr)
            with self.assertRaises(AccountExhausted):
                provider.generate("test", Path(tmp) / "out.png")

    def test_nano_banana_raises_when_no_flow_accounts(self) -> None:
        """Nano Banana использует Flow-аккаунты — без них падает с AccountExhausted."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BrowserAccountManager(root=Path(tmp))
            provider = NanoBananaImage(accounts=mgr)
            with self.assertRaises(AccountExhausted):
                provider.generate("test", Path(tmp) / "out.png")

    def test_flow_image_falls_through_to_video_provider(self) -> None:
        """Если в Flow-аккаунте мало кредитов для видео (10), но достаточно для картинки (1),
        FlowVideo упирается в AccountExhausted, а FlowImage выбирает тот же аккаунт."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BrowserAccountManager(root=Path(tmp))
            a = mgr.add("flow1", "flow")
            # Оставим 5 кредитов (хватит на картинку, но не на видео = 10)
            a.credits_used_today = 45
            mgr.save()

            video = FlowVideo(accounts=mgr)
            with self.assertRaises(AccountExhausted):
                video.animate(Path(tmp) / "fake.png", Path(tmp) / "out.mp4", prompt="x")

            image = FlowImage(accounts=mgr)
            with patch("fox2.providers.browser.flow.chromium_session") as mock_session:
                mock_session.side_effect = RuntimeError("test-bypass")
                with self.assertRaises(RuntimeError):
                    image.generate("test", Path(tmp) / "out.png")
                mock_session.assert_called_once()

    def test_nano_banana_uses_exhausted_flow_account(self) -> None:
        """С cost=0 Nano Banana работает даже когда Flow-аккаунт полностью исчерпан."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BrowserAccountManager(root=Path(tmp))
            a = mgr.add("flow1", "flow")
            a.credits_used_today = 50  # исчерпан
            mgr.save()

            provider = NanoBananaImage(accounts=mgr)
            with patch("fox2.providers.browser.nano_banana.chromium_session") as mock_session:
                mock_session.side_effect = RuntimeError("test-bypass")
                with self.assertRaises(RuntimeError):
                    provider.generate("test", Path(tmp) / "out.png")
                mock_session.assert_called_once()


class FactoryUnknownProviderTests(unittest.TestCase):
    def test_unknown_image_provider_raises(self) -> None:
        with self.assertRaises(Exception) as ctx:
            make_image_provider("midjourney_browser", AppSettings())
        self.assertIn("Неизвестный", str(ctx.exception))

    def test_unknown_video_provider_raises(self) -> None:
        with self.assertRaises(Exception) as ctx:
            make_video_provider("veo3_browser", AppSettings())
        self.assertIn("Неизвестный", str(ctx.exception))


class ProviderErrorWhenPlaywrightMissingTests(unittest.TestCase):
    """Если playwright не установлен — фабрика должна поднять ProviderError,
    а не уронить весь GUI с ImportError. Реализован lazy import в фабрике."""

    def test_flow_lazy_import(self) -> None:
        # Имитация: успешный import (он есть) — провайдер создаётся.
        provider = make_image_provider("flow_browser", AppSettings())
        self.assertIsNotNone(provider)

    def test_lazy_import_failure_yields_provider_error(self) -> None:
        # Сэмулируем отсутствие playwright/flow.py через patch.
        with patch.dict(
            "sys.modules", {"fox2.providers.browser.flow": None}
        ), self.assertRaises(ProviderError):
            make_image_provider("flow_browser", AppSettings())


class CookieImportTests(unittest.TestCase):
    """Тесты для импорта cookies из обычного браузера (план В обхода Google login)."""

    def test_convert_cookie_basic(self) -> None:
        from http.cookiejar import Cookie

        from fox2.providers.browser.sessions import _convert_cookie

        c = Cookie(
            version=0,
            name="SID",
            value="abc123",
            port=None,
            port_specified=False,
            domain=".google.com",
            domain_specified=True,
            domain_initial_dot=True,
            path="/",
            path_specified=True,
            secure=True,
            expires=1700000000,
            discard=False,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": "", "SameSite": "Lax"},
            rfc2109=False,
        )
        result = _convert_cookie(c)
        self.assertEqual(result["name"], "SID")
        self.assertEqual(result["value"], "abc123")
        self.assertEqual(result["domain"], ".google.com")
        self.assertEqual(result["path"], "/")
        self.assertTrue(result["secure"])
        self.assertTrue(result["httpOnly"])
        self.assertEqual(result["sameSite"], "Lax")
        self.assertEqual(result["expires"], 1700000000.0)

    def test_convert_cookie_session_cookie(self) -> None:
        """Cookie без expires (session-only) должна получить -1."""
        from http.cookiejar import Cookie

        from fox2.providers.browser.sessions import _convert_cookie

        c = Cookie(
            version=0, name="X", value="y", port=None, port_specified=False,
            domain=".x.com", domain_specified=True, domain_initial_dot=True,
            path="/", path_specified=True, secure=False, expires=None,
            discard=True, comment=None, comment_url=None, rest={}, rfc2109=False,
        )
        result = _convert_cookie(c)
        self.assertEqual(result["expires"], -1.0)
        self.assertFalse(result["secure"])
        self.assertFalse(result["httpOnly"])
        self.assertEqual(result["sameSite"], "Lax")  # default

    def test_load_browser_cookies_unknown_browser(self) -> None:
        from fox2.providers.browser import CookieImportError
        from fox2.providers.browser.sessions import _load_browser_cookies

        with self.assertRaises(CookieImportError) as ctx:
            _load_browser_cookies("safari-12-banana")
        self.assertIn("Неизвестный браузер", str(ctx.exception))

    def test_load_browser_cookies_propagates_loader_error(self) -> None:
        """Если browser_cookie3 падает (например, нет такого браузера на машине) —
        мы оборачиваем в CookieImportError с понятным сообщением."""
        from fox2.providers.browser import CookieImportError
        from fox2.providers.browser.sessions import _load_browser_cookies

        with patch("browser_cookie3.chrome", side_effect=RuntimeError("no chrome on disk")):
            with self.assertRaises(CookieImportError) as ctx:
                _load_browser_cookies("chrome", domains=(".google.com",))
            self.assertIn("Закрой все окна", str(ctx.exception))
            self.assertIn("no chrome on disk", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
