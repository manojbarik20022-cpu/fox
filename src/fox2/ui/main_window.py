"""Главное окно Fox2-clone: левая панель (сценарий + Запустить) + правая (7 вкладок)."""
from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from ..core.models import Aspect, PromptMode, VoicingMode
from ..core.pipeline import (
    generate_grid_images,
    generate_images_for_scenes,
    generate_prompts,
    synthesize_audio,
)
from ..core.prompts import build_llm_prompt, build_local_prompt
from ..providers.image.factory import make_image_provider
from ..providers.llm.factory import make_llm
from ..providers.tts.factory import make_tts
from ..utils.logging import get_ui_log_handler
from .state import AppState
from .tabs.assembly_tab import AssemblyTab
from .tabs.browser_tab import BrowserTab
from .tabs.media_tab import MediaTab
from .tabs.settings_tab import SettingsTab
from .tabs.video_tab import VideoTab
from .tabs.voice_web_tab import VoiceWebTab
from .tabs.voicing_tab import VoicingTab
from .theme import COLOR_BG, COLOR_PANEL, COLOR_PANEL_2, COLOR_RUN, COLOR_RUN_HOVER, COLOR_TEXT
from .widgets import LabelRow

log = logging.getLogger("fox2.ui.main")


STYLES = ["comic", "realism", "anime", "watercolor", "pencil", "3d"]
ASPECTS = ["16:9", "9:16", "1:1"]
LANGUAGES = ["original", "english", "russian"]


class MainWindow(ctk.CTk):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        # NB: do NOT use `self.state` — Tk's window already has a `state()` method,
        # and customtkinter's scaling tracker calls it periodically.
        self.app_state = state
        self.app_state.start_worker()

        self.title("Fox2-clone")
        self.geometry("1280x780")
        self.configure(fg_color=COLOR_BG)

        ctk.set_appearance_mode(self.app_state.settings.appearance_mode or "Dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()
        self._wire_log_buffer()

    # ---------- LEFT ----------
    def _build_left_panel(self) -> None:
        left = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)
        left.grid_rowconfigure(11, weight=1)

        # Header
        header = ctk.CTkFrame(left, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            header,
            text="🦊 FOX2-clone",
            text_color="#c9b6ff",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(side="left")

        # Сценарий
        ctk.CTkLabel(left, text="Сценарий:", anchor="w").grid(
            row=1, column=0, sticky="w", padx=12, pady=(8, 4)
        )
        self.script_text = ctk.CTkTextbox(left, height=240)
        self.script_text.grid(row=2, column=0, sticky="nsew", padx=12)

        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=12, pady=6)
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(btns, text="📂 Загрузить TXT", command=self._load_txt).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ctk.CTkButton(btns, text="📋 Вставить из буфера", command=self._paste).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

        # Settings
        opts = ctk.CTkFrame(left, fg_color=COLOR_PANEL_2, corner_radius=10)
        opts.grid(row=4, column=0, sticky="ew", padx=12, pady=8)
        opts.grid_columnconfigure(0, weight=1)

        self.per_scene_var = ctk.StringVar(value="1")
        LabelRow(
            opts, "Предложений на сцену:", ctk.CTkEntry(opts, textvariable=self.per_scene_var, width=80)
        ).grid(row=0, column=0, sticky="ew", padx=10)

        self.style_var = ctk.StringVar(value="comic")
        LabelRow(opts, "Стиль:", ctk.CTkOptionMenu(opts, variable=self.style_var, values=STYLES)).grid(
            row=1, column=0, sticky="ew", padx=10
        )

        self.aspect_var = ctk.StringVar(value="16:9")
        LabelRow(opts, "Разрешение:", ctk.CTkOptionMenu(opts, variable=self.aspect_var, values=ASPECTS)).grid(
            row=2, column=0, sticky="ew", padx=10
        )

        self.language_var = ctk.StringVar(value="original")
        LabelRow(opts, "Язык сцен:", ctk.CTkOptionMenu(opts, variable=self.language_var, values=LANGUAGES)).grid(
            row=3, column=0, sticky="ew", padx=10
        )

        self.prompt_mode_var = ctk.StringVar(value="single")
        radio_frame = ctk.CTkFrame(opts, fg_color="transparent")
        radio_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=4)
        ctk.CTkLabel(radio_frame, text="Режим промтов:", width=160, anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkRadioButton(radio_frame, text="Просто промт", variable=self.prompt_mode_var, value="single").grid(
            row=0, column=1, padx=6
        )
        ctk.CTkRadioButton(radio_frame, text="Сетка 2×2", variable=self.prompt_mode_var, value="grid_2x2").grid(
            row=0, column=2, padx=6
        )

        self.voicing_mode_var = ctk.StringVar(value="groups")
        v_frame = ctk.CTkFrame(opts, fg_color="transparent")
        v_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=4)
        ctk.CTkLabel(v_frame, text="Озвучка:", width=160, anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkRadioButton(v_frame, text="Группы", variable=self.voicing_mode_var, value="groups").grid(
            row=0, column=1, padx=6
        )
        ctk.CTkRadioButton(v_frame, text="Сцены", variable=self.voicing_mode_var, value="scenes").grid(
            row=0, column=2, padx=6
        )

        # Run button
        self.run_btn = ctk.CTkButton(
            left,
            text="▶ Запустить",
            fg_color=COLOR_RUN,
            hover_color=COLOR_RUN_HOVER,
            text_color="#0e2010",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._run_pipeline,
            height=44,
        )
        self.run_btn.grid(row=5, column=0, sticky="ew", padx=12, pady=8)

        # Progress
        self.progress = ctk.CTkProgressBar(left)
        self.progress.set(0.0)
        self.progress.grid(row=6, column=0, sticky="ew", padx=12)

        self.status_label = ctk.CTkLabel(left, text="Ожидание...", anchor="w")
        self.status_label.grid(row=7, column=0, sticky="ew", padx=12, pady=(2, 6))

        # Log textbox + копировать/очистить
        log_header = ctk.CTkFrame(left, fg_color="transparent")
        log_header.grid(row=10, column=0, sticky="ew", padx=12)
        log_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_header, text="Лог:", anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            log_header,
            text="📋 Копировать",
            width=110,
            height=24,
            command=self._copy_log,
        ).grid(row=0, column=1, sticky="e", padx=(4, 0))
        ctk.CTkButton(
            log_header,
            text="🗑 Очистить",
            width=100,
            height=24,
            command=self._clear_log,
        ).grid(row=0, column=2, sticky="e", padx=(4, 0))

        self.log_box = ctk.CTkTextbox(left, height=160, fg_color="#0e0c18", text_color=COLOR_TEXT)
        self.log_box.grid(row=11, column=0, sticky="nsew", padx=12, pady=(2, 12))
        self.log_box.configure(state="disabled")

    # ---------- RIGHT ----------
    def _build_right_panel(self) -> None:
        right = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(right, fg_color="transparent")
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        for tab_name in (
            "Настройки",
            "Озвучка",
            "Медиа",
            "Видео",
            "Браузер",
            "Сборка",
            "Озвучка Веб",
        ):
            self.tabs.add(tab_name)

        SettingsTab(self.tabs.tab("Настройки"), self.app_state).pack(fill="both", expand=True)
        VoicingTab(self.tabs.tab("Озвучка"), self.app_state).pack(fill="both", expand=True)
        MediaTab(self.tabs.tab("Медиа"), self.app_state).pack(fill="both", expand=True)
        VideoTab(self.tabs.tab("Видео"), self.app_state).pack(fill="both", expand=True)
        BrowserTab(self.tabs.tab("Браузер"), self.app_state).pack(fill="both", expand=True)
        AssemblyTab(self.tabs.tab("Сборка"), self.app_state).pack(fill="both", expand=True)
        VoiceWebTab(self.tabs.tab("Озвучка Веб"), self.app_state).pack(fill="both", expand=True)

    def _wire_log_buffer(self) -> None:
        handler = get_ui_log_handler()

        def listener(line: str) -> None:
            self.after(0, self._append_log, line)

        handler.add_listener(listener)

    def _append_log(self, line: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _copy_log(self) -> None:
        text = self.log_box.get("1.0", "end").rstrip("\n")
        if not text:
            self._set_status("Лог пустой — нечего копировать.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        # Tk «отпускает» буфер при закрытии окна, если ничего не делать —
        # вызываем update(), чтобы данные доехали в системный clipboard.
        self.update()
        n_lines = text.count("\n") + 1
        self._set_status(f"Лог скопирован в буфер обмена ({n_lines} стр.)")

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self._set_status("Лог очищен.")

    # ---------- ACTIONS ----------
    def _load_txt(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        self.script_text.delete("1.0", "end")
        self.script_text.insert("1.0", text)

    def _paste(self) -> None:
        try:
            data = self.clipboard_get()
        except tk.TclError:
            return
        self.script_text.delete("1.0", "end")
        self.script_text.insert("1.0", data)

    def _run_pipeline(self) -> None:
        script = self.script_text.get("1.0", "end").strip()
        if not script:
            self._set_status("Вставь сценарий в поле слева.")
            return
        try:
            per_scene = max(1, int(self.per_scene_var.get()))
        except ValueError:
            per_scene = 1
        aspect = Aspect(self.aspect_var.get())
        prompt_mode = PromptMode(self.prompt_mode_var.get())
        voicing_mode = VoicingMode(self.voicing_mode_var.get())

        # Создаём проект
        project = self.app_state.open_or_create_project(name=f"Project_{int(__import__('time').time())}")
        project.meta.script = script
        project.meta.sentences_per_scene = per_scene
        project.meta.style = self.style_var.get()
        project.meta.aspect = aspect
        project.meta.language = self.language_var.get()
        project.meta.prompt_mode = prompt_mode
        project.meta.voicing_mode = voicing_mode
        project.rebuild_scenes_from_script()
        project.save()
        log.info("Создан проект %s, сцен: %d, групп: %d", project.path, len(project.meta.scenes), len(project.meta.groups))

        self._set_status("Генерирую промты...")
        self.progress.set(0.05)
        settings = self.app_state.settings

        def run() -> None:
            try:
                # 1) промты
                try:
                    llm = make_llm(settings.default_llm_provider, settings)

                    def prompt_fn(text: str) -> str:
                        return build_llm_prompt(llm, text, style=project.meta.style, aspect=aspect.value)

                except Exception as exc:
                    log.warning("LLM недоступен (%s), использую локальные шаблоны", exc)

                    def prompt_fn(text: str) -> str:
                        return build_local_prompt(text, style=project.meta.style, aspect=aspect.value)

                generate_prompts(project, prompt_fn)
                self._update_progress(0.20, "Промты готовы. Генерирую картинки...")

                # 2) картинки
                image_provider = make_image_provider(settings.default_image_provider, settings)
                if prompt_mode == PromptMode.GRID_2X2:
                    generate_grid_images(project, image_provider, progress=lambda m: log.info(m))
                else:
                    generate_images_for_scenes(project, image_provider, progress=lambda m: log.info(m))
                self._update_progress(0.55, "Картинки готовы. Озвучиваю...")

                # 3) озвучка
                tts = make_tts(settings.default_tts_provider, settings)
                synthesize_audio(
                    project,
                    tts,
                    by_groups=voicing_mode == VoicingMode.GROUPS,
                    progress=lambda m: log.info(m),
                )
                self._update_progress(1.0, "Готово. Перейди во вкладку «Сборка» для финальной склейки.")
            except Exception as exc:
                log.exception("Ошибка пайплайна")
                self._update_progress(0.0, f"Ошибка: {exc}")

        self.app_state.submit(run)

    def _update_progress(self, value: float, status: str) -> None:
        self.after(0, lambda: self.progress.set(value))
        self.after(0, lambda: self.status_label.configure(text=status))

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)
