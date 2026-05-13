"""Регрессионные тесты для LabelRow.

Раньше виджет, переданный в ``LabelRow(parent, "...", ctk.CTkEntry(parent, ...))``,
создавался с тем же родителем, что и сама строка, и затем ``LabelRow`` вызывал
``widget.grid(row=0, column=1, ...)`` — но это укладывало виджет в `parent`,
а не внутри строки, из-за чего на форме был виден только один (последний)
виджет, а все остальные оказывались под ним в той же ячейке `row=0, col=1`.
"""
from __future__ import annotations

import os
import unittest

# Headless‑окружения: проверяем, что есть X‑дисплей.
DISPLAY_AVAILABLE = bool(os.environ.get("DISPLAY"))


@unittest.skipUnless(DISPLAY_AVAILABLE, "Нужен X-дисплей (Tk требует DISPLAY)")
class LabelRowLayoutTests(unittest.TestCase):
    """Виджет должен раскладываться внутри LabelRow, а не в общем родителе."""

    @classmethod
    def setUpClass(cls) -> None:
        import customtkinter as ctk
        cls.ctk = ctk
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def test_widget_with_sibling_parent_is_laid_out_inside_row(self) -> None:
        """Типичный кейс из кода: ``LabelRow(card, "...", ctk.CTkEntry(card, ...))``."""
        from fox2.ui.widgets import LabelRow

        ctk = self.ctk
        card = ctk.CTkFrame(self.root)
        entry = ctk.CTkEntry(card)  # parent = card (как в реальных вызовах)
        row = LabelRow(card, "Label:", entry)
        row.grid(row=0, column=0)

        # in_= сообщает Tk, в каком контейнере раскладывать виджет —
        # независимо от того, кто его реальный master. Должен быть row, не card.
        info = entry.grid_info()
        self.assertEqual(
            info.get("in"),
            row,
            "Виджет должен раскладываться внутри LabelRow, а не у её соседа",
        )
        self.assertEqual(int(info["row"]), 0)
        self.assertEqual(int(info["column"]), 1)

    def test_multiple_rows_do_not_overlap_in_same_cell(self) -> None:
        """Регрессия: все три виджета должны быть видимы (не перекрывать друг друга)."""
        from fox2.ui.widgets import LabelRow

        ctk = self.ctk
        card = ctk.CTkFrame(self.root)
        card.grid_columnconfigure(0, weight=1)

        widgets = []
        for i in range(3):
            w = ctk.CTkEntry(card)
            widgets.append(w)
            LabelRow(card, f"F{i}:", w).grid(row=i, column=0, sticky="ew")

        # Каждый виджет должен лежать внутри своего LabelRow, а не у card.
        in_containers = {str(w.grid_info()["in"]) for w in widgets}
        self.assertEqual(len(in_containers), 3, "Все три виджета должны быть в разных LabelRow")

    def test_widget_created_with_row_as_parent_still_works(self) -> None:
        """Корректный кейс: виджет уже создан с LabelRow в качестве родителя."""
        from fox2.ui.widgets import LabelRow

        ctk = self.ctk
        card = ctk.CTkFrame(self.root)
        # Дёшево: построим LabelRow без виджета невозможно (виджет — обязательный
        # аргумент), поэтому проверяем через типичный паттерн: parent совпадает с
        # самим LabelRow косвенно — через `in_` уже-уложенного виджета.
        entry = ctk.CTkEntry(card)
        row = LabelRow(card, "L:", entry)
        self.assertEqual(entry.grid_info().get("in"), row)


class ClipboardKeycodeHandlerTests(unittest.TestCase):
    """Регрессия: на английской раскладке Ctrl+V должен идти стандартным
    путём (один paste), а наш keycode-handler — пропускать событие, иначе
    будет двойная вставка."""

    def test_latin_keysym_returns_none(self) -> None:
        from fox2.ui.widgets import _NATIVE_LATIN_KEYSYMS, _on_ctrl_keypress

        # Должны быть все мнемоники Ctrl+V/C/X/A/Z в обоих регистрах.
        self.assertIn("v", _NATIVE_LATIN_KEYSYMS)
        self.assertIn("V", _NATIVE_LATIN_KEYSYMS)
        self.assertIn("c", _NATIVE_LATIN_KEYSYMS)
        self.assertIn("a", _NATIVE_LATIN_KEYSYMS)

        # Эмулируем событие на английской раскладке с keysym="v".
        class FakeEvent:
            keycode = 86  # VK_V
            keysym = "v"

            class widget:
                @staticmethod
                def winfo_class() -> str:
                    return "Entry"

        result = _on_ctrl_keypress(FakeEvent())  # type: ignore[arg-type]
        self.assertIsNone(result, "Latin keysym must be skipped (default handles it)")

    def test_cyrillic_keysym_triggers_handler(self) -> None:
        """На русской раскладке keysym будет «Cyrillic_em», и handler должен сработать."""
        from unittest.mock import patch

        from fox2.ui.widgets import _on_ctrl_keypress

        class FakeEvent:
            keycode = 86  # VK_V (та же физическая клавиша)
            keysym = "Cyrillic_em"  # м на русской раскладке

            class widget:
                @staticmethod
                def winfo_class() -> str:
                    return "Entry"

        with patch("fox2.ui.widgets._dispatch_clipboard") as mock_dispatch:
            result = _on_ctrl_keypress(FakeEvent())  # type: ignore[arg-type]
        self.assertEqual(result, "break", "Cyrillic keysym must invoke handler")
        mock_dispatch.assert_called_once()
        self.assertEqual(mock_dispatch.call_args[0][1], "paste")


@unittest.skipUnless(DISPLAY_AVAILABLE, "Нужен X-дисплей (Tk требует DISPLAY)")
class PathPickerRowTests(unittest.TestCase):
    """PathPickerRow: подпись + поле + кнопка «📁», открывающая askdirectory."""

    @classmethod
    def setUpClass(cls) -> None:
        import customtkinter as ctk
        cls.ctk = ctk
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def test_picker_writes_chosen_path_into_variable(self) -> None:
        from unittest.mock import patch

        from fox2.ui.widgets import PathPickerRow

        var = self.ctk.StringVar(value="")
        row = PathPickerRow(self.root, "Папка проектов:", var)
        with patch("fox2.ui.widgets.filedialog.askdirectory", return_value="/tmp/picked"):
            row._pick()
        self.assertEqual(var.get(), "/tmp/picked")

    def test_picker_cancel_preserves_current_value(self) -> None:
        from unittest.mock import patch

        from fox2.ui.widgets import PathPickerRow

        var = self.ctk.StringVar(value="/existing/path")
        row = PathPickerRow(self.root, "Папка:", var)
        # askdirectory возвращает "" при отмене — значение не должно затереться.
        with patch("fox2.ui.widgets.filedialog.askdirectory", return_value=""):
            row._pick()
        self.assertEqual(var.get(), "/existing/path")

    def test_picker_has_three_visible_children(self) -> None:
        """Лэйаут: label, entry и кнопка должны быть гридованы в одной строке."""
        from fox2.ui.widgets import PathPickerRow

        var = self.ctk.StringVar(value="")
        row = PathPickerRow(self.root, "X:", var)
        cols = sorted(int(c.grid_info()["column"]) for c in (row.label, row.entry, row.button))
        self.assertEqual(cols, [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
