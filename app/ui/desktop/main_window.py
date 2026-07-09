import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import sv_ttk
from datetime import datetime
from app.utils.logger import logger
from app.ui.desktop.auth_tab import AuthTab
from app.ui.desktop.settings_tab import SettingsTab
from app.utils import db
from app.core import __version__

try:
    import pystray
    from PIL import Image, ImageDraw

    TRAY_SUPPORTED = True
except ImportError:
    TRAY_SUPPORTED = False
    logger.warning("pystray не установлен. Функции системного трея отключены.")


class PlatformCard(ttk.LabelFrame):
    def __init__(self, parent, platform: str, app_core, *args, **kwargs):
        super().__init__(parent, text=f" {platform.upper()} ", padding=15, *args, **kwargs)
        self.platform = platform
        self.app_core = app_core

        self.lbl_status = ttk.Label(self, text="Ожидание...", font=("Segoe UI", 11, "bold"))
        self.lbl_status.grid(row=0, column=0, sticky="w", pady=(0, 5))

        # Кнопка ручного выбора трансляции для YouTube и RUTUBE
        if self.platform in ("youtube", "rutube"):
            self.btn_select = ttk.Button(self, text="⚙️ Выбрать стрим", command=self.on_select_broadcast, width=15)
            self.btn_select.grid(row=0, column=1, sticky="e", pady=(0, 5))

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
        is_live = data.get("is_live", False)
        status_text = "🟢 В ЭФИРЕ" if is_live else "🔴 ОФФЛАЙН"
        color = "#28a745" if is_live else "#dc3545"

        self.lbl_status.config(text=status_text, foreground=color)
        self.lbl_viewers.config(text=f"👁 Зрители: {data.get('viewers', 0)}")

        focused = None
        try:
            focused = self.focus_get()
        except Exception:
            pass

        if focused not in (self.entry_title, self.combo_game):
            new_title = data.get("title")
            if new_title and str(new_title).strip():
                self.title_var.set(new_title)

            new_game = data.get("game")
            if new_game and str(new_game).strip():
                self.game_var.set(new_game)

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

    def on_select_broadcast(self):
        """Всплывающее окно асинхронного выбора трансляций."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Выбор трансляции — {self.platform.upper()}")
        dialog.geometry("500x350")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        lbl_loading = ttk.Label(dialog, text="⏳ Загрузка списка трансляций, пожалуйста подождите...",
                                font=("Segoe UI", 10))
        lbl_loading.pack(pady=10)

        listbox = tk.Listbox(dialog, font=("Consolas", 9), background="#2a2a2a", foreground="white")
        listbox.pack(fill="both", expand=True, padx=15, pady=5)

        broadcasts = []

        async def fetch_and_fill():
            nonlocal broadcasts
            plugin = self.app_core.plugin_manager.get(self.platform)
            if not plugin:
                lbl_loading.config(text="❌ Ошибка: Плагин платформы не найден")
                return

            if not plugin.token:
                lbl_loading.config(text="❌ Нет токена авторизации/кук. Настройте платформу!")
                return

            if hasattr(plugin, "get_broadcasts"):
                broadcasts = await plugin.get_broadcasts()
                lbl_loading.config(text="Выберите нужную трансляцию:")
                listbox.delete(0, tk.END)
                if not broadcasts:
                    listbox.insert(tk.END, "Трансляции не найдены.")
                for item in broadcasts:
                    listbox.insert(tk.END, f"[{item['status'].upper()}] {item['title']} (ID: {item['id']})")
            else:
                lbl_loading.config(text="❌ Платформа не поддерживает выбор стримов")

        asyncio.create_task(fetch_and_fill())

        def save_selection():
            sel = listbox.curselection()
            if sel and broadcasts:
                idx = sel[0]
                if idx < len(broadcasts):
                    selected = broadcasts[idx]

                    config = self.app_core.config

                    if self.platform == "youtube":
                        from app.auth.token_store import get_token, set_token
                        tok = get_token("youtube") or {}
                        tok["broadcast_id"] = selected["id"]
                        set_token("youtube", tok)
                    elif self.platform == "rutube":
                        platform_cfg = config["platforms"].setdefault("rutube", {})
                        platform_cfg["broadcast_id"] = selected["id"]
                        self.app_core.update_app_config(config)

                    messagebox.showinfo("Успех", f"Успешно привязана трансляция:\n{selected['title']}")
                    dialog.destroy()

                    async def trigger_single_update():
                        plugin = self.app_core.plugin_manager.get(self.platform)
                        if plugin and plugin.enabled:
                            try:
                                status = await plugin.get_status()
                                status["platform"] = self.platform
                                self.app_core.event_bus.emit("stream.status_checked", status)
                            except Exception as ex:
                                logger.debug(f"Ошибка ручного обновления {self.platform}: {ex!r}")

                    asyncio.create_task(trigger_single_update())

        btn_select = ttk.Button(dialog, text="✅ Выбрать трансляцию", command=save_selection)
        btn_select.pack(pady=15)


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

        self.text.tag_configure("time", foreground="#6c7086")
        self.text.tag_configure("live", foreground="#a6e3a1", font=("Consolas", 9, "bold"))
        self.text.tag_configure("offline", foreground="#f38ba8")
        self.text.tag_configure("info", foreground="#89b4fa")
        self.text.tag_configure("warn", foreground="#fab387")
        self.text.tag_configure("platform", foreground="#cba6f7", font=("Consolas", 9, "bold"))

    def append(self, message: str, tag: str = "info"):
        self.text.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.insert(tk.END, f"[{ts}] ", "time")
        self.text.insert(tk.END, message + "\n", tag)

        line_count = int(self.text.index(tk.END).split(".")[0])
        if line_count > self.MAX_LINES + 20:
            self.text.delete("1.0", f"{line_count - self.MAX_LINES}.0")

        self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.config(state=tk.DISABLED)


class StreamTailGUI:
    def __init__(self, app_core):
        self.app_core = app_core
        self.cards = {}
        self._loop = asyncio.get_event_loop()

        self.root = tk.Tk()
        self.root.title(f"StreamTail v{__version__} — Stream Manager")
        self.root.geometry("1000x720")

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

        # Вкладка 1: Дашборд
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

        ttk.Button(master_frame, text="💾 В избранное", command=self.save_game_to_favorites).grid(row=1, column=2,
                                                                                                 padx=5, pady=5)
        ttk.Button(master_frame, text="🔍 Найти игру", command=self.open_search_dialog).grid(row=1, column=3, padx=5,
                                                                                            pady=5)

        self.btn_apply_all = ttk.Button(master_frame, text="⚡ ПРИМЕНИТЬ КО ВСЕМ", command=self.on_apply_all)
        self.btn_apply_all.grid(row=0, column=2, columnspan=2, sticky="nsew", padx=5, pady=5)
        master_frame.columnconfigure(1, weight=1)

        self.dash_frame = ttk.Frame(self.tab_dashboard)
        self.dash_frame.pack(fill=tk.BOTH, expand=True)
        self.loading_label = ttk.Label(self.dash_frame, text="⏳ Загрузка...", font=("Segoe UI", 12))
        self.loading_label.pack(expand=True)

        # Вкладка 2: Настройки
        self.tab_settings = SettingsTab(self.notebook, self.app_core)
        self.notebook.add(self.tab_settings, text=" ⚙️ Настройки ")

        # Вкладка 3: Авторизация
        self.tab_auth = AuthTab(self.notebook, self.app_core)
        self.notebook.add(self.tab_auth, text=" 🔑  Авторизация ")

        # Вкладка 4: Лог
        self.tab_log = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_log, text=" 📋  Лог событий ")
        self.log_panel = EventLogPanel(self.tab_log)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=4)
        self.status_label = ttk.Label(status_frame, text=" Готов к работе")
        self.status_label.pack(side=tk.LEFT)

    def open_search_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Поиск игры (через Twitch)")
        dialog.geometry("350x400")
        dialog.transient(self.root)
        dialog.grab_set()

        query_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=query_var).pack(fill=tk.X, padx=10, pady=10)
        listbox = tk.Listbox(dialog, font=("Segoe UI", 10), background="#2a2a2a", foreground="white")
        listbox.pack(fill="both", expand=True, padx=10, pady=5)

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

    def _build_platform_cards(self):
        if hasattr(self, 'loading_label') and self.loading_label.winfo_exists():
            self.loading_label.destroy()

        for widget in self.dash_frame.winfo_children():
            widget.destroy()
        self.cards.clear()

        col = 0
        row = 0
        for name, plugin in self.app_core.plugin_manager.all().items():
            if plugin.enabled:
                card = PlatformCard(self.dash_frame, name, self.app_core)
                card.grid(row=row, column=col, sticky="nsew", padx=8, pady=5)
                self.dash_frame.columnconfigure(col, weight=1)
                self.cards[name] = card
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

        if len(self.cards) == 0:
            ttk.Label(
                self.dash_frame,
                text="⚠️  Нет активных платформ.\nВключите их в настройках.",
                font=("Segoe UI", 11),
                foreground="#dc3545",
                justify=tk.CENTER,
            ).pack(expand=True)
            self.log_panel.append("Платформы не загружены", "warn")
        else:
            self._set_status(f"Активных платформ: {len(self.cards)}")

    def save_game_to_favorites(self):
        new_game = self.master_game.get().strip()
        if new_game:
            if self.app_core.game_service.add_favorite(new_game):
                games = self.app_core.game_service.get_favorites()
                master_cb = \
                [w for w in self.tab_dashboard.winfo_children()[0].winfo_children() if isinstance(w, ttk.Combobox)][0]
                master_cb['values'] = games

                for card in self.cards.values():
                    card.combo_game['values'] = games

                self.log_panel.append(f"Категория '{new_game}' сохранена в избранное.", "info")
            else:
                self.log_panel.append(f"Категория '{new_game}' уже есть в списке.", "info")

    def _subscribe_events(self):
        self.app_core.event_bus.subscribe("plugins.loaded", self._on_plugins_loaded)
        self.app_core.event_bus.subscribe("stream.status_checked", self._on_status_checked)

    def _on_plugins_loaded(self, data: dict):
        self._build_platform_cards()

    def _on_status_checked(self, data: dict):
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

    def _set_status(self, text: str):
        self.status_label.config(text=f" {text}")

    def _on_close_window(self):
        hide_to_tray = db.get_setting("hide_to_tray", True)
        if TRAY_SUPPORTED and hide_to_tray:
            self.root.withdraw()
            self._show_tray_icon()
            self.log_panel.append("Приложение свернуто в системный трей.", "info")
            if hasattr(self.app_core, "notification_service"):
                self.app_core.notification_service._show_toast("StreamTail работает в фоне")
        else:
            self._quit_app()

    def _create_tray_image(self):
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
            self._loop.call_soon_threadsafe(self.root.deiconify)

        def quit_app(icon, item):
            icon.stop()
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
