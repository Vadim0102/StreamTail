import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
from datetime import datetime
from app.utils.logger import logger


# ─────────────────────────────────────────────────────────────────────────────
# Карточка одной платформы
# ─────────────────────────────────────────────────────────────────────────────

class PlatformCard(ttk.LabelFrame):
    def __init__(self, parent, platform: str, app_core, *args, **kwargs):
        super().__init__(parent, text=f" {platform.upper()} ", padding=15, *args, **kwargs)
        self.platform = platform
        self.app_core = app_core

        self.lbl_status = ttk.Label(self, text="Ожидание...", font=("Segoe UI", 11, "bold"))
        self.lbl_status.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        self.lbl_viewers = ttk.Label(self, text="👁 Зрители: —", font=("Segoe UI", 10))
        self.lbl_viewers.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 15))

        ttk.Label(self, text="Название:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w")
        self.title_var = tk.StringVar()
        self.entry_title = ttk.Entry(self, textvariable=self.title_var, width=28)
        self.entry_title.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(self, text="Категория:", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w")
        self.game_var = tk.StringVar()
        self.combo_game = ttk.Combobox(
            self,
            textvariable=self.game_var,
            values=self.app_core.game_service.get_favorites(),
            width=26,
        )
        self.combo_game.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

        self.btn_apply = ttk.Button(
            self, text="Обновить платформу", command=self.on_apply
        )
        self.btn_apply.grid(row=4, column=0, columnspan=2, pady=(15, 0), sticky="ew")

        self.columnconfigure(1, weight=1)

    def update_data(self, data: dict):
        """Обновляет отображение. Вызывается ТОЛЬКО из главного потока."""
        is_live = data.get("is_live", False)
        status_text = "🟢 В ЭФИРЕ" if is_live else "🔴 ОФФЛАЙН"
        color = "#28a745" if is_live else "#dc3545"

        self.lbl_status.config(text=status_text, foreground=color)
        self.lbl_viewers.config(text=f"👁 Зрители: {data.get('viewers', 0)}")

        # Не перезаписываем поле, если оно сейчас в фокусе
        focused = self.focus_get()
        if focused not in (self.entry_title, self.combo_game):
            self.title_var.set(data.get("title", self.title_var.get()))
            self.game_var.set(data.get("game", self.game_var.get()))

    def on_apply(self):
        self.btn_apply.config(state="disabled")
        asyncio.create_task(self._apply_async())

    async def _apply_async(self):
        try:
            title = self.title_var.get().strip()
            game = self.game_var.get().strip()
            results = []
            if title:
                results.append(
                    await self.app_core.stream_service.update_title(self.platform, title)
                )
            if game:
                results.append(
                    await self.app_core.stream_service.update_game(self.platform, game)
                )
            msg = "\n".join(results) if results else "Нет данных для обновления"
            messagebox.showinfo(f"{self.platform} — Результат", msg)
        except Exception as e:
            logger.error(f"UI: ошибка обновления {self.platform}: {e}")
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.btn_apply.config(state="normal")


# ─────────────────────────────────────────────────────────────────────────────
# Вкладка «Лог событий»
# ─────────────────────────────────────────────────────────────────────────────

class EventLogPanel(ttk.Frame):
    MAX_LINES = 200

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self._build()

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(toolbar, text="Лог событий StreamTail", font=("Segoe UI", 10, "bold")).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="Очистить", command=self.clear).pack(side=tk.RIGHT)

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(
            frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED,
            background="#1e1e2e",
            foreground="#cdd6f4",
            insertbackground="#cdd6f4",
            selectbackground="#313244",
            relief=tk.FLAT,
            padx=8,
            pady=6,
        )
        scrollbar = ttk.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(fill=tk.BOTH, expand=True)

        # Цветовые теги
        self.text.tag_configure("time", foreground="#6c7086")
        self.text.tag_configure("live", foreground="#a6e3a1", font=("Consolas", 9, "bold"))
        self.text.tag_configure("offline", foreground="#f38ba8")
        self.text.tag_configure("info", foreground="#89b4fa")
        self.text.tag_configure("warn", foreground="#fab387")
        self.text.tag_configure("platform", foreground="#cba6f7", font=("Consolas", 9, "bold"))

    def append(self, message: str, tag: str = "info"):
        """Добавляет строку в лог. Потокобезопасен (вызывать из главного потока)."""
        self.text.config(state=tk.NORMAL)

        ts = datetime.now().strftime("%H:%M:%S")
        self.text.insert(tk.END, f"[{ts}] ", "time")
        self.text.insert(tk.END, message + "\n", tag)

        # Ограничиваем число строк
        line_count = int(self.text.index(tk.END).split(".")[0])
        if line_count > self.MAX_LINES + 20:
            self.text.delete("1.0", f"{line_count - self.MAX_LINES}.0")

        self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.config(state=tk.DISABLED)


# ─────────────────────────────────────────────────────────────────────────────
# Главное окно
# ─────────────────────────────────────────────────────────────────────────────

class StreamTailGUI:
    def __init__(self, app_core):
        self.app_core = app_core
        self.cards: dict[str, PlatformCard] = {}

        self.root = tk.Tk()
        self.root.title(
            f"StreamTail v{app_core.config['app']['version']} — Stream Manager"
        )
        self.root.geometry("900x560")
        self.root.minsize(720, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._set_theme()
        self._build_ui()
        self._subscribe_events()

    # ── Тема ──────────────────────────────────────────────────────────────────

    def _set_theme(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("TLabelframe", font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", foreground="#0056b3")
        style.configure(
            "Master.TButton",
            font=("Segoe UI", 10, "bold"),
            background="#007bff",
            foreground="white",
        )
        style.configure("TNotebook.Tab", font=("Segoe UI", 9), padding=(10, 4))

    # ── Построение UI ─────────────────────────────────────────────────────────

    def _build_ui(self):
        # Notebook — вкладки «Дашборд» и «Лог»
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

        # ── Вкладка «Дашборд» ────────────────────────────────────────────────
        self.tab_dashboard = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_dashboard, text=" 📺  Дашборд ")

        # Панель массового управления
        master_frame = ttk.LabelFrame(
            self.tab_dashboard, text=" ⚡ Массовое управление (все платформы) ", padding=15
        )
        master_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(master_frame, text="Общее название:").grid(row=0, column=0, sticky="w")
        self.master_title = tk.StringVar()
        ttk.Entry(master_frame, textvariable=self.master_title).grid(
            row=0, column=1, sticky="ew", padx=10, pady=5
        )

        ttk.Label(master_frame, text="Общая категория:").grid(row=1, column=0, sticky="w")
        self.master_game = tk.StringVar()
        ttk.Combobox(
            master_frame,
            textvariable=self.master_game,
            values=self.app_core.game_service.get_favorites(),
        ).grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # Кнопка сохранения игры в базу
        self.btn_save_game = ttk.Button(
            master_frame,
            text="💾 В избранное",
            command=self.save_game_to_favorites
        )
        self.btn_save_game.grid(row=1, column=2, sticky="ew", padx=5, pady=5)

        self.btn_apply_all = ttk.Button(
            master_frame,
            text="⚡ ПРИМЕНИТЬ КО ВСЕМ",
            style="Master.TButton",
            command=self.on_apply_all,
        )
        self.btn_apply_all.grid(
            row=0, column=3, rowspan=2, sticky="nsew", padx=5, pady=5, ipadx=10
        )
        master_frame.columnconfigure(1, weight=1)

        # Контейнер для карточек платформ (заполняется после plugins.loaded)
        self.dash_frame = ttk.Frame(self.tab_dashboard)
        self.dash_frame.pack(fill=tk.BOTH, expand=True)

        # Заглушка «загрузка»
        self.loading_label = ttk.Label(
            self.dash_frame,
            text="⏳  Загрузка платформ...",
            font=("Segoe UI", 12),
            foreground="#888",
        )
        self.loading_label.pack(expand=True)

        # ── Вкладка «Лог» ────────────────────────────────────────────────────
        self.tab_log = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_log, text=" 📋  Лог событий ")
        self.log_panel = EventLogPanel(self.tab_log)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        # ── Статус-бар ───────────────────────────────────────────────────────
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=4)
        self.status_label = ttk.Label(
            status_frame, text=" Готов к работе", foreground="#555"
        )
        self.status_label.pack(side=tk.LEFT)
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, side=tk.BOTTOM)

    # ── Динамическая загрузка карточек ────────────────────────────────────────

    def _build_platform_cards(self):
        """Вызывается после plugins.loaded — строит карточки для активных платформ."""
        self.loading_label.destroy()

        col = 0
        for name, plugin in self.app_core.plugin_manager.all().items():
            if plugin.enabled:
                card = PlatformCard(self.dash_frame, name, self.app_core)
                card.grid(row=0, column=col, sticky="nsew", padx=8, pady=5)
                self.dash_frame.columnconfigure(col, weight=1)
                self.cards[name] = card
                col += 1

        if col == 0:
            ttk.Label(
                self.dash_frame,
                text="⚠️  Нет активных платформ.\nПроверьте config/app.yaml",
                font=("Segoe UI", 11),
                foreground="#dc3545",
                justify=tk.CENTER,
            ).pack(expand=True)
            self.log_panel.append("Нет активных платформ — проверьте config/app.yaml", "warn")
        else:
            platforms_str = ", ".join(self.cards.keys())
            self.log_panel.append(f"Загружены платформы: {platforms_str}", "info")
            self._set_status(f"Активных платформ: {col}")

    def save_game_to_favorites(self):
        new_game = self.master_game.get().strip()
        if new_game:
            if self.app_core.game_service.add_favorite(new_game):
                # Обновляем все combobox'ы
                games = self.app_core.game_service.get_favorites()
                # Обновляем в мастере
                master_cb = \
                [w for w in self.tab_dashboard.winfo_children()[0].winfo_children() if isinstance(w, ttk.Combobox)][0]
                master_cb['values'] = games

                # Обновляем в карточках платформ
                for card in self.cards.values():
                    card.combo_game['values'] = games

                self.log_panel.append(f"Категория '{new_game}' сохранена в избранное.", "info")
            else:
                self.log_panel.append(f"Категория '{new_game}' уже есть в списке.", "info")

    # ── Подписки на события ───────────────────────────────────────────────────

    def _subscribe_events(self):
        self.app_core.event_bus.subscribe("plugins.loaded", self._on_plugins_loaded)
        self.app_core.event_bus.subscribe("stream.status_checked", self._on_status_checked)

    def _on_plugins_loaded(self, data: dict):
        """Вызывается из asyncio-loop (главный поток) — безопасно трогать Tkinter."""
        self._build_platform_cards()

    def _on_status_checked(self, data: dict):
        """Вызывается из asyncio-loop (главный поток) — безопасно трогать Tkinter."""
        platform = data.get("platform", "?")

        if platform in self.cards:
            self.cards[platform].update_data(data)

        is_live = data.get("is_live", False)
        viewers = data.get("viewers", 0)
        title = data.get("title", "")

        tag = "live" if is_live else "offline"
        status_word = "В ЭФИРЕ" if is_live else "оффлайн"

        self.log_panel.append(
            f"{platform}  •  {status_word}  •  👁 {viewers}  •  «{title}»", tag
        )

        self._set_status(
            f"Последнее обновление: {platform} — {'🟢 В ЭФИРЕ' if is_live else '🔴 оффлайн'}"
        )

    # ── Массовое применение ───────────────────────────────────────────────────

    def on_apply_all(self):
        self.btn_apply_all.config(state="disabled")
        self._set_status("Выполняется массовое обновление...")
        asyncio.create_task(self._apply_all_async())

    async def _apply_all_async(self):
        try:
            title = self.master_title.get().strip()
            game = self.master_game.get().strip()
            platforms = [
                n for n, p in self.app_core.plugin_manager.all().items() if p.enabled
            ]

            tasks = []
            for p in platforms:
                if title:
                    tasks.append(self.app_core.stream_service.update_title(p, title))
                if game:
                    tasks.append(self.app_core.stream_service.update_game(p, game))

            if not tasks:
                messagebox.showinfo("Результат", "Нечего обновлять")
                return

            results = await asyncio.gather(*tasks, return_exceptions=True)
            msgs = []
            for r in results:
                if isinstance(r, Exception):
                    msgs.append(f"❌ {r}")
                    self.log_panel.append(f"Ошибка массового обновления: {r}", "warn")
                elif r:
                    msgs.append(f"✅ {r}")
                    self.log_panel.append(str(r), "info")

            messagebox.showinfo("Результат", "\n".join(msgs) if msgs else "Готово")
        except Exception as e:
            logger.error(f"Массовое обновление: {e}")
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.btn_apply_all.config(state="normal")
            self._set_status("Готов к работе")

    # ── Вспомогательные ───────────────────────────────────────────────────────

    def _set_status(self, text: str):
        self.status_label.config(text=f" {text}")

    def _on_close(self):
        self.app_core.shutdown()
        self.root.destroy()
