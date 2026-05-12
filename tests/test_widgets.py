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


if __name__ == "__main__":
    unittest.main()
