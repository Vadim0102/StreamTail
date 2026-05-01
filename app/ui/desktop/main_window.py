import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import sv_ttk
from datetime import datetime
from app.utils.logger import logger
from app.ui.desktop.auth_tab import AuthTab

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_SUPPORTED = True
except ImportError:
    TRAY_SUPPORTED = False
    logger.warning("pystray не установлен. Функции системного трея отключены.")


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
        self.cards = {}

        self._loop = asyncio.get_event_loop()

        self.root = tk.Tk()
        self.root.title(f"StreamTail v{app_core.config['app']['version']} — Stream Manager")
        self.root.geometry("950x650")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._set_theme()
        self._build_ui()
        self._subscribe_events()

        self.tray_icon = None

    def _set_theme(self):
        sv_ttk.set_theme("dark")

    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

        self.tab_dashboard = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_dashboard, text=" 📺  Дашборд ")

        master_frame = ttk.LabelFrame(self.tab_dashboard, text=" ⚡ Массовое управление ", padding=15)
        master_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(master_frame, text="Общее название:").grid(row=0, column=0, sticky="w")
        self.master_title = tk.StringVar()
        ttk.Entry(master_frame, textvariable=self.master_title).grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        ttk.Label(master_frame, text="Общая категория:").grid(row=1, column=0, sticky="w")
        self.master_game = tk.StringVar()
        ttk.Combobox(
            master_frame, textvariable=self.master_game, values=self.app_core.game_service.get_favorites()
        ).grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # Кнопка добавления в избранное
        ttk.Button(master_frame, text="💾 В избранное", command=self.save_game_to_favorites).grid(row=1, column=2, padx=5, pady=5)

        # Кнопка ПОИСКА
        ttk.Button(master_frame, text="🔍 Найти игру", command=self.open_search_dialog).grid(row=1, column=3, padx=5, pady=5)

        self.btn_apply_all = ttk.Button(master_frame, text="⚡ ПРИМЕНИТЬ КО ВСЕМ", command=self.on_apply_all)
        self.btn_apply_all.grid(row=0, column=2, columnspan=2, sticky="nsew", padx=5, pady=5)
        master_frame.columnconfigure(1, weight=1)

        self.dash_frame = ttk.Frame(self.tab_dashboard)
        self.dash_frame.pack(fill=tk.BOTH, expand=True)
        self.loading_label = ttk.Label(self.dash_frame, text="⏳ Загрузка...", font=("Segoe UI", 12))
        self.loading_label.pack(expand=True)

        # Вкладка 2: Авторизация (НОВОЕ)
        self.tab_auth = AuthTab(self.notebook, self.app_core)
        self.notebook.add(self.tab_auth, text=" 🔑  Авторизация ")

        # Вкладка 3: Лог
        self.tab_log = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_log, text=" 📋  Лог событий ")
        self.log_panel = EventLogPanel(self.tab_log)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=4)
        self.status_label = ttk.Label(status_frame, text=" Готов к работе")
        self.status_label.pack(side=tk.LEFT)

    def open_search_dialog(self):
        """Всплывающее окно поиска игр."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Поиск игры (через Twitch)")
        dialog.geometry("350x400")
        dialog.transient(self.root)
        dialog.grab_set()

        query_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=query_var).pack(fill=tk.X, padx=10, pady=10)
        listbox = tk.Listbox(dialog, font=("Segoe UI", 10), background="#2a2a2a", foreground="white")
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        async def do_search():
            q = query_var.get()
            listbox.delete(0, tk.END)
            listbox.insert(tk.END, "Поиск...")
            results = await self.app_core.game_service.search_games(q)
            listbox.delete(0, tk.END)
            if not results:
                listbox.insert(tk.END, "Ничего не найдено")
            for r in results:
                listbox.insert(tk.END, r)

        ttk.Button(dialog, text="Искать", command=lambda: asyncio.create_task(do_search())).pack(fill=tk.X, padx=10)

        def on_select():
            sel = listbox.curselection()
            if sel:
                val = listbox.get(sel[0])
                if val not in ["Поиск...", "Ничего не найдено"]:
                    self.master_game.set(val)
                    self.save_game_to_favorites()
                    dialog.destroy()

        ttk.Button(dialog, text="Выбрать и закрыть", command=on_select).pack(fill=tk.X, padx=10, pady=10)

    # ── Динамическая загрузка карточек ────────────────────────────────────────

    def _build_platform_cards(self):
        """Вызывается после загрузки плагинов или успешной авторизации."""
        # 1. Уничтожаем загрузочный текст, если он есть
        if hasattr(self, 'loading_label') and self.loading_label.winfo_exists():
            self.loading_label.destroy()

        # 2. ОЧИЩАЕМ старые карточки (иначе они накладываются друг на друга)
        for widget in self.dash_frame.winfo_children():
            widget.destroy()
        self.cards.clear()

        col = 0
        # 3. Строим карточки заново
        for name, plugin in self.app_core.plugin_manager.all().items():
            if plugin.enabled:
                card = PlatformCard(self.dash_frame, name, self.app_core)
                card.grid(row=0, column=col, sticky="nsew", padx=8, pady=5)
                self.dash_frame.columnconfigure(col, weight=1)
                self.cards[name] = card
                col += 1

        # 4. Если нет платформ — показываем предупреждение
        if col == 0:
            ttk.Label(
                self.dash_frame,
                text="⚠️  Нет активных платформ.\nВозможно, ошибка в коде плагинов.",
                font=("Segoe UI", 11),
                foreground="#dc3545",
                justify=tk.CENTER,
            ).pack(expand=True)
            self.log_panel.append("Платформы не загружены", "warn")
        else:
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

    # ── Работа с треем (НОВОЕ) ────────────────────────────────────────────────

    def _on_close_window(self):
        """Обрабатывает нажатие 'Крестика'."""
        if TRAY_SUPPORTED:
            self.root.withdraw()  # Скрываем окно
            self._show_tray_icon()
            self.log_panel.append("Приложение свернуто в системный трей.", "info")
            if hasattr(self.app_core, "notification_service"):
                self.app_core.notification_service._show_toast("StreamTail работает в фоне")
        else:
            self._quit_app()

    def _create_tray_image(self):
        """Создает простую заглушку-иконку для трея."""
        image = Image.new('RGB', (64, 64), color=(14, 14, 26))
        dc = ImageDraw.Draw(image)
        dc.ellipse((16, 16, 48, 48), fill=(166, 227, 161))
        return image

    def _show_tray_icon(self):
        if self.tray_icon:
            return

        def show_window(icon, item):
            icon.stop()
            self.tray_icon = None
            # ИЗМЕНЕНО: потокобезопасный вызов для разворачивания окна!
            self._loop.call_soon_threadsafe(self.root.deiconify)

        def quit_app(icon, item):
            icon.stop()
            # ИЗМЕНЕНО: потокобезопасный вызов для выхода!
            self._loop.call_soon_threadsafe(self._quit_app)

        menu = pystray.Menu(
            pystray.MenuItem('Открыть StreamTail', show_window, default=True),
            pystray.MenuItem('Выход', quit_app)
        )

        image = self._create_tray_image()
        self.tray_icon = pystray.Icon("StreamTail", image, "StreamTail", menu)

        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _quit_app(self):
        logger.info("Закрытие приложения...")
        self.app_core.shutdown()
        self.root.destroy()
