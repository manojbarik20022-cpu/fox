"""Маленькие переиспользуемые виджеты."""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from .theme import COLOR_ACCENT, COLOR_PANEL, COLOR_TEXT_DIM


class LabelRow(ctk.CTkFrame):
    """Горизонтальная строка: подпись слева, виджет справа.

    Виджет, переданный аргументом, обычно создан с тем же родителем, что и
    сам ``LabelRow`` (типичная запись на месте вызова —
    ``LabelRow(card, "...", ctk.CTkEntry(card, ...))``). Чтобы такой виджет
    был корректно размещён внутри строки, используем ``in_=self`` и поднимаем
    его поверх фона строки через ``tkraise()`` — иначе непрозрачный фон
    родительского контейнера, который рисует ``CTkFrame`` с
    ``fg_color="transparent"``, закрывает виджет.
    """

    def __init__(
        self,
        master,
        label: str,
        widget: ctk.CTkBaseClass,
        *,
        label_width: int = 160,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        self.label = ctk.CTkLabel(
            self,
            text=label,
            width=label_width,
            anchor="w",
            text_color=COLOR_TEXT_DIM,
        )
        self.label.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.widget = widget
        if widget.master is self:
            self.widget.grid(row=0, column=1, sticky="ew", pady=4)
        else:
            self.widget.grid(row=0, column=1, sticky="ew", pady=4, in_=self)
            self.widget.tkraise()


class SectionTitle(ctk.CTkLabel):
    def __init__(self, master, text: str) -> None:
        super().__init__(
            master,
            text=text,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )


class AccentButton(ctk.CTkButton):
    def __init__(self, master, text: str, command: Callable[[], None] | None = None, **kw) -> None:
        super().__init__(
            master,
            text=text,
            command=command,
            fg_color=COLOR_ACCENT,
            hover_color="#8b62de",
            text_color="#ffffff",
            **kw,
        )


class CardFrame(ctk.CTkFrame):
    def __init__(self, master, **kw) -> None:
        super().__init__(master, fg_color=COLOR_PANEL, corner_radius=12, **kw)
