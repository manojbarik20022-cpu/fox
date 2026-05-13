"""Вкладка «Настройки» — API ключи и общие настройки."""
from __future__ import annotations

import customtkinter as ctk

from ..state import AppState
from ..widgets import AccentButton, CardFrame, LabelRow, PathPickerRow, SectionTitle


class SettingsTab(ctk.CTkFrame):
    def __init__(self, master, state: AppState) -> None:
        super().__init__(master, fg_color="transparent")
        self.state = state
        self.grid_columnconfigure(0, weight=1)
        # Скролл-область забирает всю высоту, кнопка сохранения всегда внизу.
        self.grid_rowconfigure(0, weight=1)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._scroll.grid_columnconfigure(0, weight=1)

        self._build_general()
        self._build_keys()
        self._build_local()
        self._build_save_button()

    def _build_general(self) -> None:
        card = CardFrame(self._scroll)
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        card.grid_columnconfigure(0, weight=1)

        SectionTitle(card, "Общие").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        self.projects_root_var = ctk.StringVar(value=self.state.settings.projects_root)
        PathPickerRow(card, "Папка проектов:", self.projects_root_var).grid(
            row=1, column=0, sticky="ew", padx=12
        )

        self.downloads_var = ctk.StringVar(value=self.state.settings.downloads_dir)
        PathPickerRow(card, "Папка загрузок:", self.downloads_var).grid(
            row=2, column=0, sticky="ew", padx=12, pady=(0, 10)
        )

        # Дефолтные провайдеры
        SectionTitle(card, "Провайдеры по умолчанию").grid(
            row=3, column=0, sticky="w", padx=12, pady=(8, 4)
        )

        self.llm_var = ctk.StringVar(value=self.state.settings.default_llm_provider)
        LabelRow(
            card,
            "LLM:",
            ctk.CTkOptionMenu(
                card,
                variable=self.llm_var,
                values=["ollama", "lmstudio", "openai", "anthropic", "gemini", "grok"],
            ),
        ).grid(row=4, column=0, sticky="ew", padx=12)

        self.tts_var = ctk.StringVar(value=self.state.settings.default_tts_provider)
        LabelRow(
            card,
            "TTS:",
            ctk.CTkOptionMenu(card, variable=self.tts_var, values=["edge", "elevenlabs", "piper", "aistudio"]),
        ).grid(row=5, column=0, sticky="ew", padx=12)

        self.image_var = ctk.StringVar(value=self.state.settings.default_image_provider)
        LabelRow(
            card,
            "Картинки:",
            ctk.CTkOptionMenu(
                card,
                variable=self.image_var,
                values=["pollinations", "sd_webui", "nano_banana", "grok_browser", "flow_browser"],
            ),
        ).grid(row=6, column=0, sticky="ew", padx=12)

        self.video_var = ctk.StringVar(value=self.state.settings.default_video_provider)
        LabelRow(
            card,
            "Видео:",
            ctk.CTkOptionMenu(
                card,
                variable=self.video_var,
                values=["ffmpeg", "flow_browser", "grok_browser"],
            ),
        ).grid(row=7, column=0, sticky="ew", padx=12, pady=(0, 10))

    def _build_keys(self) -> None:
        card = CardFrame(self._scroll)
        card.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        card.grid_columnconfigure(0, weight=1)

        SectionTitle(card, "API ключи (хранятся локально, не коммитятся)").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 6)
        )

        self.openai_var = ctk.StringVar(value=self.state.settings.openai_api_key)
        LabelRow(
            card,
            "OpenAI:",
            ctk.CTkEntry(card, textvariable=self.openai_var, show="•"),
        ).grid(row=1, column=0, sticky="ew", padx=12)

        self.anthropic_var = ctk.StringVar(value=self.state.settings.anthropic_api_key)
        LabelRow(
            card,
            "Anthropic (Claude):",
            ctk.CTkEntry(card, textvariable=self.anthropic_var, show="•"),
        ).grid(row=2, column=0, sticky="ew", padx=12)

        self.gemini_var = ctk.StringVar(value=self.state.settings.google_api_key)
        LabelRow(
            card,
            "Google (Gemini):",
            ctk.CTkEntry(card, textvariable=self.gemini_var, show="•"),
        ).grid(row=3, column=0, sticky="ew", padx=12)

        self.xai_var = ctk.StringVar(value=self.state.settings.xai_api_key)
        LabelRow(
            card,
            "xAI (Grok):",
            ctk.CTkEntry(card, textvariable=self.xai_var, show="•"),
        ).grid(row=4, column=0, sticky="ew", padx=12)

        self.eleven_var = ctk.StringVar(value=self.state.settings.elevenlabs_api_key)
        LabelRow(
            card,
            "ElevenLabs API:",
            ctk.CTkEntry(card, textvariable=self.eleven_var, show="•"),
        ).grid(row=5, column=0, sticky="ew", padx=12)

        self.eleven_voice_var = ctk.StringVar(value=self.state.settings.elevenlabs_voice_id)
        LabelRow(
            card,
            "ElevenLabs voice_id:",
            ctk.CTkEntry(card, textvariable=self.eleven_voice_var),
        ).grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 10))

    def _build_local(self) -> None:
        card = CardFrame(self._scroll)
        card.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        card.grid_columnconfigure(0, weight=1)

        SectionTitle(card, "Локальные движки").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        self.ollama_url_var = ctk.StringVar(value=self.state.settings.ollama_base_url)
        LabelRow(card, "Ollama URL:", ctk.CTkEntry(card, textvariable=self.ollama_url_var)).grid(
            row=1, column=0, sticky="ew", padx=12
        )

        self.ollama_model_var = ctk.StringVar(value=self.state.settings.ollama_model)
        LabelRow(card, "Ollama модель:", ctk.CTkEntry(card, textvariable=self.ollama_model_var)).grid(
            row=2, column=0, sticky="ew", padx=12
        )

        self.lmstudio_url_var = ctk.StringVar(value=self.state.settings.lmstudio_base_url)
        LabelRow(card, "LM Studio URL:", ctk.CTkEntry(card, textvariable=self.lmstudio_url_var)).grid(
            row=3, column=0, sticky="ew", padx=12
        )

        self.lmstudio_model_var = ctk.StringVar(value=self.state.settings.lmstudio_model)
        LabelRow(card, "LM Studio модель:", ctk.CTkEntry(card, textvariable=self.lmstudio_model_var)).grid(
            row=4, column=0, sticky="ew", padx=12
        )

        self.sd_url_var = ctk.StringVar(value=self.state.settings.sd_webui_base_url)
        LabelRow(card, "SD WebUI URL:", ctk.CTkEntry(card, textvariable=self.sd_url_var)).grid(
            row=5, column=0, sticky="ew", padx=12, pady=(0, 10)
        )

    def _build_save_button(self) -> None:
        # Кнопка приколочена внизу вкладки (не в скролле), чтобы всегда была видна.
        AccentButton(self, text="💾 Сохранить настройки", command=self._save).grid(
            row=1, column=0, sticky="ew", padx=8, pady=(4, 8)
        )

    def _save(self) -> None:
        s = self.state.settings
        s.projects_root = self.projects_root_var.get().strip()
        s.downloads_dir = self.downloads_var.get().strip()
        s.default_llm_provider = self.llm_var.get()
        s.default_tts_provider = self.tts_var.get()
        s.default_image_provider = self.image_var.get()
        s.default_video_provider = self.video_var.get()
        s.openai_api_key = self.openai_var.get().strip()
        s.anthropic_api_key = self.anthropic_var.get().strip()
        s.google_api_key = self.gemini_var.get().strip()
        s.xai_api_key = self.xai_var.get().strip()
        s.elevenlabs_api_key = self.eleven_var.get().strip()
        s.elevenlabs_voice_id = self.eleven_voice_var.get().strip()
        s.ollama_base_url = self.ollama_url_var.get().strip()
        s.ollama_model = self.ollama_model_var.get().strip()
        s.lmstudio_base_url = self.lmstudio_url_var.get().strip()
        s.lmstudio_model = self.lmstudio_model_var.get().strip()
        s.sd_webui_base_url = self.sd_url_var.get().strip()
        self.state.save_settings()
