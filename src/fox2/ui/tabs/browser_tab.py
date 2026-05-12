"""Вкладка «Браузер» — аккаунты Flow/Grok/Nano Banana и старые координаты Fox2."""
from __future__ import annotations

import logging

import customtkinter as ctk

from ...core.settings import CoordinateProfile
from ...providers.browser import (
    DAILY_LIMITS,
    BrowserAccountManager,
    CoordinateAutomator,
    PlaywrightUnavailable,
    login_url_for,
    open_for_login,
)
from ..state import AppState
from ..theme import COLOR_TEXT_DIM
from ..widgets import AccentButton, CardFrame, LabelRow, SectionTitle

log = logging.getLogger("fox2.ui.browser")


PROVIDER_LABEL: dict[str, str] = {
    "flow": "Google Flow",
    "grok": "Grok",
    "nano_banana": "Nano Banana (Gemini)",
}


class BrowserTab(ctk.CTkFrame):
    def __init__(self, master, state: AppState) -> None:
        super().__init__(master, fg_color="transparent")
        self.state = state
        self.grid_columnconfigure(0, weight=1)
        # Скролл, чтобы помещалось при множестве аккаунтов.
        self.grid_rowconfigure(0, weight=1)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=0, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        self.accounts = BrowserAccountManager()
        self.automator = CoordinateAutomator()

        self._build_accounts()
        self._build_add_account()
        self._build_coordinates()

    # ---------------- accounts ----------------
    def _build_accounts(self) -> None:
        card = CardFrame(self._scroll)
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(0, weight=1)
        SectionTitle(header, "Аккаунты Flow / Grok / Nano Banana").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header, text="🔄 Сбросить кредиты", width=160, command=self._reset_credits
        ).grid(row=0, column=1, sticky="e")

        self.accounts_container = ctk.CTkFrame(card, fg_color="transparent")
        self.accounts_container.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 10))
        self.accounts_container.grid_columnconfigure(0, weight=1)
        self._refresh_accounts_view()

    def _refresh_accounts_view(self) -> None:
        # Сносим старые виджеты строк и перерисовываем.
        for child in self.accounts_container.winfo_children():
            child.destroy()

        accounts = self.accounts.list_all()
        if not accounts:
            ctk.CTkLabel(
                self.accounts_container,
                text="Пока ни одного аккаунта. Добавь ниже — программа откроет Chromium для ручного логина.",
                anchor="w",
                text_color=COLOR_TEXT_DIM,
                justify="left",
            ).grid(row=0, column=0, sticky="w", pady=4)
            return

        # Заголовок «таблицы»
        head = ctk.CTkFrame(self.accounts_container, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        for col, (text, weight) in enumerate(
            [("Имя", 2), ("Провайдер", 2), ("Использовано / лимит", 2), ("Действия", 3)]
        ):
            head.grid_columnconfigure(col, weight=weight)
            ctk.CTkLabel(head, text=text, anchor="w", text_color=COLOR_TEXT_DIM).grid(
                row=0, column=col, sticky="w", padx=4
            )

        for i, account in enumerate(accounts, start=1):
            self.accounts.reset_if_new_day(account)
            row = ctk.CTkFrame(self.accounts_container, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=2)
            for col, weight in enumerate([2, 2, 2, 3]):
                row.grid_columnconfigure(col, weight=weight)

            ctk.CTkLabel(row, text=account.name, anchor="w").grid(row=0, column=0, sticky="w", padx=4)
            ctk.CTkLabel(
                row, text=PROVIDER_LABEL.get(account.provider, account.provider), anchor="w"
            ).grid(row=0, column=1, sticky="w", padx=4)

            limit = account.daily_limit()
            credits_text = (
                f"{account.credits_used_today} / {limit}" if limit else f"{account.credits_used_today} / ∞"
            )
            ctk.CTkLabel(row, text=credits_text, anchor="w").grid(row=0, column=2, sticky="w", padx=4)

            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=3, sticky="e")
            ctk.CTkButton(
                actions,
                text="🔐 Войти заново",
                width=120,
                height=24,
                command=lambda a=account: self._login_existing(a.name),
            ).grid(row=0, column=0, padx=4)
            ctk.CTkButton(
                actions,
                text="🗑 Удалить",
                width=80,
                height=24,
                fg_color="#5a3030",
                hover_color="#7a3030",
                command=lambda a=account: self._delete_account(a.name),
            ).grid(row=0, column=1, padx=4)

    # ---------------- add account form ----------------
    def _build_add_account(self) -> None:
        card = CardFrame(self._scroll)
        card.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        card.grid_columnconfigure(0, weight=1)

        SectionTitle(card, "Добавить аккаунт").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )

        self.new_name_var = ctk.StringVar(value="")
        LabelRow(card, "Имя:", ctk.CTkEntry(card, textvariable=self.new_name_var)).grid(
            row=1, column=0, sticky="ew", padx=12
        )

        self.new_provider_var = ctk.StringVar(value="flow")
        LabelRow(
            card,
            "Провайдер:",
            ctk.CTkOptionMenu(
                card,
                variable=self.new_provider_var,
                values=list(DAILY_LIMITS.keys()),
            ),
        ).grid(row=2, column=0, sticky="ew", padx=12)

        AccentButton(card, text="➕ Добавить и войти", command=self._add_and_login).grid(
            row=3, column=0, sticky="ew", padx=12, pady=(8, 4)
        )
        self.add_status = ctk.CTkLabel(card, text="", anchor="w", justify="left")
        self.add_status.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 10))

    def _add_and_login(self) -> None:
        name = self.new_name_var.get().strip()
        provider = self.new_provider_var.get()
        if not name:
            self._set_add_status("Введи имя аккаунта.")
            return
        try:
            account = self.accounts.add(name, provider)
        except ValueError as exc:
            self._set_add_status(f"Ошибка: {exc}")
            return
        self._refresh_accounts_view()
        self._launch_login(account.profile_dir, provider, success_msg=f"Аккаунт {name} добавлен.")

    def _login_existing(self, name: str) -> None:
        a = self.accounts.get(name)
        if not a:
            return
        self._launch_login(a.profile_dir, a.provider, success_msg=f"Сессия для {name} обновлена.")

    def _launch_login(self, profile_dir: str, provider: str, *, success_msg: str) -> None:
        url = login_url_for(provider)
        self._set_add_status(
            f"Открываю Chromium для входа в {PROVIDER_LABEL.get(provider, provider)}…\n"
            "Войди в нужный аккаунт и закрой окно браузера, когда будешь готов."
        )

        def on_done() -> None:
            self.after(0, lambda: self._set_add_status(success_msg))
            self.after(0, self._refresh_accounts_view)

        def on_error(exc: Exception) -> None:
            msg = str(exc)
            if isinstance(exc, PlaywrightUnavailable):
                msg = (
                    "Playwright/Chromium не установлен. Перезапусти run.bat (или run.sh) — "
                    "он установит Chromium при следующем запуске."
                )
            self.after(0, lambda: self._set_add_status(f"Ошибка: {msg}"))

        try:
            open_for_login(profile_dir, url, on_done=on_done, on_error=on_error)
        except PlaywrightUnavailable as exc:
            on_error(exc)

    def _delete_account(self, name: str) -> None:
        self.accounts.remove(name)
        self._refresh_accounts_view()
        self._set_add_status(f"Аккаунт {name} удалён.")

    def _reset_credits(self) -> None:
        self.accounts.reset_all()
        self._refresh_accounts_view()
        self._set_add_status("Счётчики кредитов обнулены.")

    def _set_add_status(self, text: str) -> None:
        self.add_status.configure(text=text)

    # ---------------- coordinates (legacy Fox2) ----------------
    def _build_coordinates(self) -> None:
        card = CardFrame(self._scroll)
        card.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        card.grid_columnconfigure(0, weight=1)

        SectionTitle(card, "Координаты кликов (как в Fox2)").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )

        existing = [p.name for p in self.state.settings.coordinate_profiles] or ["default"]
        self.coord_profile_var = ctk.StringVar(
            value=self.state.settings.active_coordinate_profile or existing[0]
        )
        self.coord_menu = ctk.CTkOptionMenu(card, variable=self.coord_profile_var, values=existing)
        LabelRow(card, "Профиль координат:", self.coord_menu).grid(
            row=1, column=0, sticky="ew", padx=12
        )

        ctk.CTkLabel(
            card,
            text="Захват координаты: подведи мышь к нужной кнопке и нажми «Захватить»\n(программа подождёт 5 секунд).",
            anchor="w",
            justify="left",
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(8, 4))

        self.point_name_var = ctk.StringVar(value="Кнопка Generate")
        LabelRow(card, "Имя кнопки:", ctk.CTkEntry(card, textvariable=self.point_name_var)).grid(
            row=3, column=0, sticky="ew", padx=12
        )

        AccentButton(card, text="🎯 Захватить координату (5с)", command=self._capture_point).grid(
            row=4, column=0, sticky="ew", padx=12, pady=10
        )

        self.coord_status = ctk.CTkLabel(card, text="", anchor="w", justify="left")
        self.coord_status.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 10))

        if not self.automator.available():
            self.coord_status.configure(
                text="pyautogui не установлен. pip install pyautogui чтобы захватывать координаты."
            )

    def _capture_point(self) -> None:
        if not self.automator.available():
            return
        name = self.point_name_var.get().strip() or "point"

        def run() -> None:
            try:
                pt = self.automator.capture_after_delay(5.0)
                self._set_coord_status(f"{name}: X={pt.x} Y={pt.y}")
                profile_name = self.coord_profile_var.get()
                profiles = self.state.settings.coordinate_profiles
                prof = next((p for p in profiles if p.name == profile_name), None)
                if prof is None:
                    prof = CoordinateProfile(name=profile_name)
                    profiles.append(prof)
                prof.points[name] = {"x": pt.x, "y": pt.y, "delay": 0.5}
                self.state.settings.active_coordinate_profile = profile_name
                self.state.save_settings()
            except Exception as exc:
                self._set_coord_status(f"Ошибка: {exc}")

        self.state.submit(run)

    def _set_coord_status(self, text: str) -> None:
        self.after(0, lambda: self.coord_status.configure(text=text))
