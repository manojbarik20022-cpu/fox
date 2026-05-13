"""Маленькие переиспользуемые виджеты."""
from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from .theme import COLOR_ACCENT, COLOR_PANEL, COLOR_TEXT_DIM

log = logging.getLogger("fox2.ui.widgets")


# Виртуальные keycode-ы клавиш V/C/X/A/Z в Windows VK / X11.
# На Windows event.keycode = VK_*, который не зависит от раскладки —
# поэтому Ctrl+V на русской раскладке («м») тоже должен сработать.
_CTRL_KEYCODES = {
    86: "paste",       # V
    67: "copy",        # C
    88: "cut",         # X
    65: "select_all",  # A
    90: "undo",        # Z
}

_TEXT_WIDGET_CLASSES = ("Entry", "TEntry", "Text", "Spinbox", "TCombobox")


def _is_text_widget(widget: tk.Misc | None) -> bool:
    if widget is None:
        return False
    try:
        return widget.winfo_class() in _TEXT_WIDGET_CLASSES
    except tk.TclError:
        return False


def _entry_select_all(widget: tk.Misc) -> None:
    cls = widget.winfo_class()
    if cls == "Text":
        widget.tag_add("sel", "1.0", "end-1c")  # type: ignore[attr-defined]
        widget.mark_set("insert", "end-1c")  # type: ignore[attr-defined]
    else:
        try:
            widget.select_range(0, "end")  # type: ignore[attr-defined]
            widget.icursor("end")  # type: ignore[attr-defined]
        except tk.TclError:
            pass


def _dispatch_clipboard(widget: tk.Misc, action: str) -> None:
    try:
        if action == "paste":
            widget.event_generate("<<Paste>>")
        elif action == "copy":
            widget.event_generate("<<Copy>>")
        elif action == "cut":
            widget.event_generate("<<Cut>>")
        elif action == "undo":
            widget.event_generate("<<Undo>>")
        elif action == "select_all":
            _entry_select_all(widget)
    except tk.TclError as exc:
        log.debug("clipboard action %s failed: %s", action, exc)


def _on_ctrl_keypress(event: tk.Event) -> str | None:
    action = _CTRL_KEYCODES.get(event.keycode)
    if action is None or not _is_text_widget(event.widget):
        return None
    _dispatch_clipboard(event.widget, action)
    return "break"


def _show_context_menu(event: tk.Event) -> str | None:
    widget = event.widget
    if not _is_text_widget(widget):
        return None
    with contextlib.suppress(tk.TclError):
        widget.focus_set()
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Вырезать", command=lambda: _dispatch_clipboard(widget, "cut"))
    menu.add_command(label="Копировать", command=lambda: _dispatch_clipboard(widget, "copy"))
    menu.add_command(label="Вставить", command=lambda: _dispatch_clipboard(widget, "paste"))
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: _dispatch_clipboard(widget, "select_all"))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()
    return "break"


def install_clipboard_bindings(root: tk.Misc) -> None:
    """Глобальные Ctrl+V/C/X/A/Z для русской раскладки + контекстное меню по правому клику.

    Стандартный tkinter под Windows ловит ``<Control-v>`` по символу,
    а на русской раскладке Ctrl+V даёт keysym=«м» (Cyrillic_em) — поэтому
    стандартный биндинг не срабатывает. Слушаем `<Control-KeyPress>` и
    смотрим на `event.keycode`, который равен Win-VK и не зависит от
    раскладки. Привязка идёт через ``bind_all`` на корневом окне.
    """
    root.bind_all("<Control-KeyPress>", _on_ctrl_keypress, add="+")
    # Правый клик: на Linux/Win обычно Button-3, на macOS — Button-2.
    root.bind_all("<Button-3>", _show_context_menu, add="+")
    root.bind_all("<Button-2>", _show_context_menu, add="+")


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


class PathPickerRow(ctk.CTkFrame):
    """Строка для пути к папке: подпись слева, поле ввода и кнопка «📁» справа.

    Кнопка открывает системный диалог выбора папки (``tkinter.filedialog
    .askdirectory``) и записывает выбранный путь в ``variable``. Если путь
    в поле уже валидный — диалог открывается на нём.
    """

    def __init__(
        self,
        master,
        label: str,
        variable: ctk.StringVar,
        *,
        label_width: int = 160,
        title: str | None = None,
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

        self.entry = ctk.CTkEntry(self, textvariable=variable)
        self.entry.grid(row=0, column=1, sticky="ew", pady=4)

        self._variable = variable
        self._dialog_title = title or label.rstrip(":")

        self.button = ctk.CTkButton(
            self,
            text="📁",
            width=36,
            command=self._pick,
        )
        self.button.grid(row=0, column=2, sticky="e", padx=(6, 0), pady=4)

    def _pick(self) -> None:
        current = self._variable.get().strip()
        initial: str | None = None
        if current:
            try:
                p = Path(current).expanduser()
                initial = str(p if p.is_dir() else p.parent)
            except OSError:
                initial = None
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title=f"Выберите: {self._dialog_title}",
            mustexist=False,
            initialdir=initial or "",
        )
        if chosen:
            self._variable.set(chosen)
            log.debug("Выбрана папка для %s: %s", self._dialog_title, chosen)
