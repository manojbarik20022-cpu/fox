"""Браузерные провайдеры Google Flow (Imagen 4 / Veo / Nano Banana на labs.google/fx/tools/flow).

Flow работает на бесплатном тарифе Google: 50 кредитов в день на аккаунт —
этого хватает на 5 видео Veo (по 10 кред/Generate, 2 выхода) или 50 картинок Imagen.
Nano Banana внутри Flow кредиты не списывает. С нашей стороны:

* считаем потраченные за день кредиты на каждый аккаунт (10 кред/видео, 1 кред/Imagen картинка)
* при исчерпании одного аккаунта (50 кред/день) — автоматически переключаемся на следующий
* Outputs per prompt в настройках Flow НЕ трогаем — оставляем дефолтные 2 выхода
  за Generate (это и есть «10 кред/видео»)

Селекторы написаны через role/text-локаторы Playwright и заведомо чувствительны
к редизайнам Google. При неудаче провайдер сохраняет скриншот страницы в
``~/Fox2Clone/debug/flow_<ts>.png`` — это пригодится, чтобы починить локаторы.
"""
from __future__ import annotations

import contextlib
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ...utils.paths import app_dir, ensure_dir
from ..base import ImageProvider, ProviderError, VideoProvider
from .accounts import COST, BrowserAccountManager
from .sessions import chromium_session

log = logging.getLogger("fox2.browser.flow")

FLOW_URL = "https://labs.google/fx/tools/flow"

# Сколько ждём результат (секунд). Видео в Flow Veo занимает 30-90 сек.
DEFAULT_IMAGE_TIMEOUT = 90.0
DEFAULT_VIDEO_TIMEOUT = 240.0


def _debug_dir() -> Path:
    return ensure_dir(app_dir() / "debug")


def _save_debug_screenshot(page: Any, label: str) -> Path:
    path = _debug_dir() / f"flow_{label}_{datetime.now():%Y%m%d_%H%M%S}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        log.warning("Скриншот ошибки сохранён: %s", path)
    except Exception as exc:
        log.warning("Не удалось сохранить скриншот %s: %s", path, exc)
    return path


class FlowController:
    """Низкоуровневая обёртка над Flow UI (Imagen / Veo).

    Использует уже залогиненный Playwright-профиль. Каждый запрос:
      1. открывает labs.google/fx/tools/flow
      2. если нет активного проекта — создаёт «Fox2-clone»
      3. переключает таб (Видео / Изображения)
      4. вводит промт, нажимает Create
      5. ждёт появления новых результатов в правой панели
      6. скачивает первый новый файл в out_path
    """

    PROJECT_NAME = "Fox2-clone"

    def __init__(self, page: Any) -> None:
        self.page = page

    # ---------------- общий цикл ----------------
    def navigate(self, timeout_ms: int = 60_000) -> None:
        log.info("Flow: открываю %s", FLOW_URL)
        self.page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=timeout_ms)
        # Подождём пока UI окончательно подгрузится (есть либо «New project» либо проект).
        with contextlib.suppress(Exception):
            self.page.wait_for_load_state("networkidle", timeout=15_000)

    def ensure_project(self) -> None:
        """Открывает существующий проект Fox2-clone или создаёт новый."""
        page = self.page
        # Если мы уже в Scenebuilder — крошка содержит «Scenebuilder».
        if page.locator("text=Scenebuilder").count():
            return

        # Ищем карточку проекта с нашим именем — она будет на главной Flow.
        project_card = page.locator(f"text={self.PROJECT_NAME}").first
        try:
            if project_card.count():
                project_card.click(timeout=5_000)
                page.wait_for_load_state("networkidle", timeout=15_000)
                return
        except Exception as exc:
            log.debug("project_card click skipped: %s", exc)

        # Иначе создаём новый.
        log.info("Flow: создаю новый проект %s", self.PROJECT_NAME)
        # «New project» / «+» / «Создать проект» — пробуем по нескольким маркерам.
        for selector in [
            "button:has-text('New project')",
            "button:has-text('Создать проект')",
            "button[aria-label='New project']",
            "[data-testid='new-project']",
        ]:
            try:
                btn = page.locator(selector).first
                if btn.count():
                    btn.click(timeout=5_000)
                    break
            except Exception:
                continue

        with contextlib.suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=20_000)

        # Переименуем проект (необязательно, но удобно искать его потом).
        try:
            edit_btn = page.locator("button[aria-label='Edit project']").first
            if edit_btn.count():
                edit_btn.click(timeout=3_000)
                input_field = page.locator("input[type='text']").first
                input_field.fill(self.PROJECT_NAME)
                save_btn = page.locator("button:has-text('Save')").first
                if save_btn.count():
                    save_btn.click(timeout=3_000)
        except Exception as exc:
            log.debug("Не смог переименовать проект (некритично): %s", exc)

    def select_mode(self, mode: str) -> None:
        """mode = 'image' или 'video'."""
        page = self.page
        target_text = "Images" if mode == "image" else "Videos"
        for selector in [
            f"button:has-text('{target_text}')",
            f"[role='tab']:has-text('{target_text}')",
            f"text={target_text}",
        ]:
            try:
                el = page.locator(selector).first
                if el.count():
                    el.click(timeout=3_000)
                    return
            except Exception:
                continue
        log.warning("Flow: не нашёл переключатель режима %r", mode)

    def set_outputs_per_prompt(self, n: int = 1) -> None:
        """В Settings выставляет Outputs per prompt = n. Экономит кредиты."""
        page = self.page
        # Открываем настройки (tune icon).
        for selector in [
            "button[aria-label*='Settings' i]",
            "button[aria-label*='Tune' i]",
            "button:has-text('Settings')",
        ]:
            try:
                btn = page.locator(selector).first
                if btn.count():
                    btn.click(timeout=3_000)
                    break
            except Exception:
                continue

        # Ищем поле Outputs / Количество. Обычно это input number или slider.
        for sel in [
            "input[aria-label*='Outputs' i]",
            "input[aria-label*='outputs' i]",
        ]:
            try:
                inp = page.locator(sel).first
                if inp.count():
                    inp.fill(str(n))
                    return
            except Exception:
                continue

        # Альтернатива: кнопки 1/2/3/4
        for sel in [
            f"button:has-text('{n}'):near(:text('Outputs'))",
            f"[role='radio'][aria-label='{n}']",
        ]:
            try:
                el = page.locator(sel).first
                if el.count():
                    el.click(timeout=2_000)
                    return
            except Exception:
                continue
        log.debug("Flow: settings/outputs не выставил — оставляю как есть")

    def submit_prompt(self, prompt: str, *, timeout: float) -> int:
        """Вписывает промт и нажимает Create. Возвращает количество клипов
        в asset-панели *до* генерации (нужно потом ждать, пока счётчик увеличится).
        """
        page = self.page
        # Найдём кол-во карточек до генерации.
        before = page.locator("[role='img'], [data-asset], .asset, video").count()

        # Промт-инпут.
        textbox = None
        for sel in [
            "textarea[placeholder*='Generate' i]",
            "textarea[aria-label*='Prompt' i]",
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
            raise ProviderError("Flow: не нашёл поле промта на странице.")
        textbox.click()
        textbox.fill(prompt)

        # Кнопка Create.
        for sel in [
            "button[aria-label*='Create' i]",
            "button:has-text('Create')",
            "button[aria-label*='Generate' i]",
            "button:has-text('Generate')",
        ]:
            try:
                btn = page.locator(sel).first
                if btn.count() and btn.is_enabled():
                    btn.click(timeout=5_000)
                    log.info("Flow: Create нажат (промт: %s)", prompt[:60])
                    return before
            except Exception:
                continue
        _save_debug_screenshot(page, "no_create_button")
        raise ProviderError("Flow: не нашёл активную кнопку Create.")

    def wait_for_new_asset(self, count_before: int, *, timeout: float) -> Any:
        """Ждёт появления нового элемента в asset-панели. Возвращает локатор первого нового."""
        page = self.page
        deadline = time.time() + timeout
        while time.time() < deadline:
            assets = page.locator("[role='img'], [data-asset], .asset, video, img[src*='blob']")
            count = assets.count()
            if count > count_before:
                return assets.first
            time.sleep(2.0)
        _save_debug_screenshot(page, "wait_timeout")
        raise ProviderError(
            f"Flow: за {timeout:.0f}с не появилось нового результата. "
            "Возможно, кредиты закончились или Flow подвис."
        )

    def download_asset(self, asset_locator: Any, out_path: Path, *, kind: str) -> Path:
        """Скачивает asset (картинку или видео) в out_path."""
        page = self.page
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Пробуем правый-клик → «Сохранить как» — но это требует диалога ОС.
        #    Вместо этого ищем встроенную кнопку Download в hover-меню.
        with contextlib.suppress(Exception):
            asset_locator.hover(timeout=3_000)

        for sel in [
            "button[aria-label*='Download' i]",
            "button:has-text('Download')",
            "a[download]",
        ]:
            try:
                dl = page.locator(sel).first
                if dl.count():
                    with page.expect_download(timeout=60_000) as download_info:
                        dl.click()
                    download = download_info.value
                    download.save_as(str(out_path))
                    log.info("Flow: скачано в %s", out_path)
                    return out_path
            except Exception as exc:
                log.debug("download via %r не удался: %s", sel, exc)
                continue

        # 2. Fallback: достаём src/blob и сохраняем через page.evaluate.
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
                log.info("Flow: blob сохранён в %s (%d bytes)", out_path, len(data))
                return out_path
            if src:
                # обычный URL — качаем через playwright request.
                resp = page.request.get(src, timeout=60_000)
                out_path.write_bytes(resp.body())
                return out_path
        except Exception as exc:
            log.warning("Flow: fallback download не сработал: %s", exc)

        _save_debug_screenshot(page, f"download_failed_{kind}")
        raise ProviderError(
            "Flow: не удалось скачать результат. "
            f"Проверь дебаг-скриншот в {_debug_dir()}."
        )


class FlowImage(ImageProvider):
    """Картинки через Flow (Imagen/Nano Banana Pro платно, расходуя кредиты)."""

    name = "flow_browser"

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
        cost = COST["flow:image"]
        account = self.accounts.acquire("flow", cost)
        log.info("Flow image: использую аккаунт %s (осталось %d кред)", account.name, account.credits_remaining())
        with chromium_session(account.profile_dir, headless=False) as (_ctx, page):
            ctrl = FlowController(page)
            ctrl.navigate()
            ctrl.ensure_project()
            ctrl.select_mode("image")
            count_before = ctrl.submit_prompt(prompt, timeout=DEFAULT_IMAGE_TIMEOUT)
            new_asset = ctrl.wait_for_new_asset(count_before, timeout=DEFAULT_IMAGE_TIMEOUT)
            ctrl.download_asset(new_asset, out_path, kind="image")
        self.accounts.consume(account, cost)
        return out_path


class FlowVideo(VideoProvider):
    """Видео через Flow Veo (10 кред / Generate при дефолтных 2 выходах)."""

    name = "flow_browser"

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
        cost = COST["flow:video"]
        account = self.accounts.acquire("flow", cost)
        log.info("Flow video: использую аккаунт %s (осталось %d кред)", account.name, account.credits_remaining())
        # Для image-to-video промт берётся из «prompt» если есть, иначе из имени файла.
        effective_prompt = prompt or _prompt_from_filename(image_path)
        with chromium_session(account.profile_dir, headless=False) as (_ctx, page):
            ctrl = FlowController(page)
            ctrl.navigate()
            ctrl.ensure_project()
            ctrl.select_mode("video")
            # TODO: загрузить картинку как референс через «+ ingredient» когда селекторы
            #       будут понятны. Сейчас работаем чистым text-to-video.
            count_before = ctrl.submit_prompt(effective_prompt, timeout=DEFAULT_VIDEO_TIMEOUT)
            new_asset = ctrl.wait_for_new_asset(count_before, timeout=DEFAULT_VIDEO_TIMEOUT)
            ctrl.download_asset(new_asset, out_path, kind="video")
        self.accounts.consume(account, cost)
        return out_path


def _prompt_from_filename(path: Path) -> str:
    """Использует имя файла как fallback-промт (если основной не передан)."""
    name = re.sub(r"[^a-zA-Zа-яА-Я0-9 ]", " ", path.stem)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "cinematic scene"
