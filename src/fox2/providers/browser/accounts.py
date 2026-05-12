"""Менеджер браузерных аккаунтов с учётом дневных кредитов и авто-ротацией.

Используется браузерными провайдерами (Flow, Grok, Nano Banana) — на каждый провайдер
заводится один или несколько аккаунтов, у каждого свой профиль Playwright и свой
счётчик израсходованных кредитов за день.

Аккаунты хранятся в ``~/Fox2Clone/accounts.json``. Каждый профиль Chromium лежит в
``~/Fox2Clone/playwright_profiles/<имя>/``.
"""
from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from ...utils.paths import app_dir, ensure_dir

log = logging.getLogger("fox2.browser.accounts")


# Дневные лимиты по провайдерам (в «кредитах»). Стоимость каждой операции — у провайдера.
DAILY_LIMITS: dict[str, int] = {
    "flow": 50,        # 50 кредитов/день на бесплатном тарифе
    "grok": 100,       # условно, у Grok нет жёсткого «кредитного» лимита; считаем картинки
    "nano_banana": 0,  # 0 = безлимит, не учитываем кредиты
}

# Стоимость операций (кредитов). 0 = бесплатно.
COST: dict[str, int] = {
    "flow:image": 1,        # Imagen (basic) в Flow стоит ~1 кредит
    "flow:video": 5,        # Veo на бесплатном — 5 кредитов за ролик
    "grok:image": 1,
    "grok:video": 5,
    "nano_banana:image": 0,
}


class AccountExhausted(RuntimeError):
    """Все аккаунты данного провайдера исчерпали дневной лимит."""


class BrowserAccount(BaseModel):
    """Браузерный аккаунт + счётчик кредитов на сегодня."""

    name: str
    provider: str  # "flow", "grok", "nano_banana"
    profile_dir: str = ""  # путь к Playwright user-data; пусто = автогенерация
    credits_used_today: int = 0
    last_reset: str = ""  # ISO date YYYY-MM-DD последнего сброса счётчика
    note: str = ""

    def daily_limit(self) -> int:
        return DAILY_LIMITS.get(self.provider, 0)

    def credits_remaining(self) -> int:
        """Сколько кредитов осталось до конца дня. 0 (лимит) = безлимит."""
        limit = self.daily_limit()
        if limit == 0:
            return 10**9  # «бесконечность»
        return max(0, limit - self.credits_used_today)

    def has_capacity_for(self, cost: int) -> bool:
        if self.daily_limit() == 0:
            return True
        return self.credits_remaining() >= cost


class AccountsConfig(BaseModel):
    """Содержимое accounts.json."""

    accounts: list[BrowserAccount] = Field(default_factory=list)


class BrowserAccountManager:
    """Загружает/сохраняет ``accounts.json`` и раздаёт аккаунты с учётом лимита."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else app_dir()
        ensure_dir(self.root)
        self.profiles_root = self.root / "playwright_profiles"
        ensure_dir(self.profiles_root)
        self.accounts_path = self.root / "accounts.json"
        self.config = self._load()

    # ---------- I/O ----------
    def _load(self) -> AccountsConfig:
        if not self.accounts_path.exists():
            return AccountsConfig()
        try:
            return AccountsConfig.model_validate_json(self.accounts_path.read_text("utf-8"))
        except Exception as exc:
            log.warning("Не удалось прочитать %s: %s. Старт с пустым списком.", self.accounts_path, exc)
            return AccountsConfig()

    def save(self) -> None:
        ensure_dir(self.root)
        self.accounts_path.write_text(self.config.model_dump_json(indent=2), encoding="utf-8")

    # ---------- CRUD ----------
    def list_all(self) -> list[BrowserAccount]:
        return list(self.config.accounts)

    def list_for(self, provider: str) -> list[BrowserAccount]:
        return [a for a in self.config.accounts if a.provider == provider]

    def get(self, name: str) -> BrowserAccount | None:
        return next((a for a in self.config.accounts if a.name == name), None)

    def add(self, name: str, provider: str, *, note: str = "") -> BrowserAccount:
        """Создаёт аккаунт + папку Playwright-профиля."""
        if not name.strip():
            raise ValueError("Имя аккаунта не может быть пустым")
        if provider not in DAILY_LIMITS:
            raise ValueError(f"Неизвестный провайдер: {provider}. Ожидаются: {list(DAILY_LIMITS)}")
        if self.get(name):
            raise ValueError(f"Аккаунт {name!r} уже существует")
        profile_dir = self.profiles_root / name
        ensure_dir(profile_dir)
        account = BrowserAccount(
            name=name,
            provider=provider,
            profile_dir=str(profile_dir),
            last_reset=date.today().isoformat(),
            note=note,
        )
        self.config.accounts.append(account)
        self.save()
        return account

    def remove(self, name: str, *, delete_profile: bool = True) -> None:
        account = self.get(name)
        if not account:
            return
        self.config.accounts = [a for a in self.config.accounts if a.name != name]
        self.save()
        if delete_profile and account.profile_dir:
            try:
                shutil.rmtree(account.profile_dir, ignore_errors=True)
            except OSError as exc:
                log.warning("Не удалось удалить профиль %s: %s", account.profile_dir, exc)

    # ---------- кредиты / ротация ----------
    def reset_if_new_day(self, account: BrowserAccount) -> None:
        today = date.today().isoformat()
        if account.last_reset != today:
            account.credits_used_today = 0
            account.last_reset = today

    def reset_all(self) -> None:
        today = date.today().isoformat()
        for a in self.config.accounts:
            a.credits_used_today = 0
            a.last_reset = today
        self.save()

    def acquire(self, provider: str, cost: int) -> BrowserAccount:
        """Возвращает первый аккаунт ``provider`` с достатком кредитов на ``cost``.

        Перед проверкой каждого аккаунта обновляет ``last_reset`` если наступил
        новый день. Если ни один аккаунт не подходит — кидает ``AccountExhausted``.
        """
        candidates = self.list_for(provider)
        if not candidates:
            raise AccountExhausted(
                f"Нет ни одного аккаунта для {provider!r}. Добавь во вкладке «Браузер»."
            )
        for a in candidates:
            self.reset_if_new_day(a)
            if a.has_capacity_for(cost):
                log.debug("acquire %s: %s (осталось %d)", provider, a.name, a.credits_remaining())
                return a
        used = ", ".join(f"{a.name}={a.credits_used_today}/{a.daily_limit()}" for a in candidates)
        raise AccountExhausted(
            f"Все аккаунты {provider!r} исчерпали дневной лимит. Использовано сегодня: {used}"
        )

    def consume(self, account: BrowserAccount, cost: int) -> None:
        """Списывает ``cost`` кредитов с аккаунта и сохраняет."""
        self.reset_if_new_day(account)
        account.credits_used_today += cost
        self.save()
        log.info(
            "Аккаунт %s: списано %d кредитов (итого сегодня %d/%d)",
            account.name,
            cost,
            account.credits_used_today,
            account.daily_limit() or 0,
        )
