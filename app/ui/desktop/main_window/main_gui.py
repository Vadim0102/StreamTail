import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import sys
from PIL import Image, ImageDraw

from app.utils.logger import logger
from app.ui.desktop.auth_tab import AuthTab
from app.ui.desktop.settings_tab import SettingsTab
from app.ui.desktop.main_window.event_log_panel import EventLogPanel
from app.ui.desktop.main_window.obs_dock import OBSDockWindow
from app.ui.desktop.main_window.platform_card import PlatformCard
from app.ui.desktop.main_window.chat_panel import ChatPanelMixin
from app.utils import db
from app.core import __version__

try:
    import pystray

    TRAY_SUPPORTED = True
except ImportError:
    TRAY_SUPPORTED = False
    logger.warning("pystray не установлен. Функции системного трея отключены.")


class StreamTailGUI(ChatPanelMixin):
    def __init__(self, app_core):
        self.app_core = app_core
        self.cards = {}
        self._loop = asyncio.get_event_loop()

        self.root = tk.Tk()
        self.root.title(f"StreamTail v{__version__} — Stream Manager")
        self.root.geometry("1000x750")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._set_theme()
        self._set_window_icon()
        self._build_ui()
        self._subscribe_events()
        self._setup_loguru_sink()  # Подключение глобального перехватчика логов

        self.tray_icon = None
        self.obs_dock = None

    def _set_theme(self):
        from app.utils import theme_manager
        theme_manager.apply_theme(self.root)

    def _set_window_icon(self):
        from app.utils.paths import get_asset_path
        icon_path = get_asset_path("icon.ico")
        if icon_path.exists():
            try:
                if sys.platform == "win32":
                    self.root.iconbitmap(str(icon_path))
                else:
                    from PIL import ImageTk
                    img = Image.open(icon_path)
                    photo = ImageTk.PhotoImage(img)
                    self.root.iconphoto(True, photo)
                    self._icon_ref = photo
            except Exception as e:
                logger.debug(f"Ошибка установки иконки главного окна: {e}")

    def _setup_loguru_sink(self):
        """Интегрирует все логи системного логгера Loguru в панель логов GUI."""
        from loguru import logger as loguru_logger

        def gui_log_sink(message):
            try:
                record = message.record
                level_name = record["level"].name
                msg_text = record["message"]

                tag = "info"
                if level_name == "WARNING":
                    tag = "warn"
                elif level_name in ("ERROR", "CRITICAL"):
                    tag = "offline"  # Красный цвет текста для ошибок

                log_line = f"[{level_name}] {msg_text}"

                # Безопасное планирование вставки текста в GUI из любого потока
                if hasattr(self, "log_panel") and self.log_panel.winfo_exists():
                    self.root.after(0, self.log_panel.append, log_line, tag)
            except Exception:
                pass

        # Сохраняем ID обработчика, чтобы иметь возможность удалить его при выходе
        self._gui_sink_id = loguru_logger.add(
            gui_log_sink, level="INFO", format="{message}", backtrace=False, diagnose=False
        )

    def remove_loguru_sink(self):
        """Безопасно отключает перехватчик логов перед закрытием окон."""
        if hasattr(self, "_gui_sink_id"):
            from loguru import logger as loguru_logger
            try:
                loguru_logger.remove(self._gui_sink_id)
            except Exception:
                pass
            del self._gui_sink_id

    def _create_tray_image(self):
        from app.utils.paths import get_asset_path
        icon_path = get_asset_path("icon.ico")
        try:
            if icon_path.exists():
                return Image.open(icon_path).convert("RGBA")
        except Exception as e:
            logger.debug(f"Не удалось загрузить иконку для трея: {e}")

        image = Image.new('RGB', (64, 64), color=(14, 14, 26))
        dc = ImageDraw.Draw(image)
        dc.ellipse((16, 16, 48, 48), fill=(166, 227, 161))
        return image

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

        self.btn_apply_all = ttk.Button(master_frame, text="⚡ ПРИМЕНИТЬ КО ВСЕМ", command=self.on_apply_all)
        self.btn_apply_all.grid(row=0, column=2, columnspan=3, sticky="ew", padx=5, pady=5)

        ttk.Button(master_frame, text="💾 В избранное", command=self.save_game_to_favorites).grid(row=1, column=2,
                                                                                                 padx=5, pady=5,
                                                                                                 sticky="ew")

        ttk.Button(master_frame, text="🔍 Найти игру", command=self.open_search_dialog).grid(row=1, column=3, padx=5,
                                                                                            pady=5, sticky="ew")

        self.btn_refresh_now = ttk.Button(master_frame, text="🔁 Обновить статусы", command=self.on_force_refresh)
        self.btn_refresh_now.grid(row=1, column=4, padx=5, pady=5, sticky="ew")

        master_frame.columnconfigure(1, weight=1)

        self.dash_frame = ttk.Frame(self.tab_dashboard)
        self.dash_frame.pack(fill=tk.BOTH, expand=True)
        self.loading_label = ttk.Label(self.dash_frame, text="⏳ Загрузка...", font=("Segoe UI", 12))
        self.loading_label.pack(expand=True)

        self.tab_settings = SettingsTab(self.notebook, self.app_core)
        self.notebook.add(self.tab_settings, text=" ⚙️ Настройки ")

        self.tab_auth = AuthTab(self.notebook, self.app_core)
        self.notebook.add(self.tab_auth, text=" 🔑  Авторизация ")

        self.tab_chat = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_chat, text=" 💬  Мультичат ")
        self._build_chat_tab()

        self.tab_log = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_log, text=" 📋  Лог событий ")
        self.log_panel = EventLogPanel(self.tab_log)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=4)

        self.status_label = ttk.Label(status_frame, text=" Готов к работе")
        self.status_label.pack(side=tk.LEFT)

        self.btn_obs_dock = ttk.Button(
            status_frame,
            text="📊 OBS Док",
            command=self.open_obs_dock,
            width=12
        )
        self.btn_obs_dock.pack(side=tk.RIGHT)

        self.apply_theme_to_custom_widgets()

    def apply_theme_to_custom_widgets(self):
        from app.utils import theme_manager
        colors = theme_manager.get_theme_colors()

        if hasattr(self, "log_panel") and self.log_panel.winfo_exists():
            self.log_panel.text.configure(
                background=colors["field_bg"],
                foreground=colors["fg"],
                insertbackground=colors["fg"],
                selectbackground=colors["select_bg"]
            )
            self.log_panel.text.tag_configure("live", foreground=colors["text_green"])
            self.log_panel.text.tag_configure("offline", foreground=colors["text_red"])
            self.log_panel.text.tag_configure("info", foreground=colors["text_blue"])
            self.log_panel.text.tag_configure("warn", foreground=colors["text_sec"])

        if hasattr(self, "tab_settings") and self.tab_settings.winfo_exists():
            if hasattr(self.tab_settings, "canvas") and self.tab_settings.canvas.winfo_exists():
                self.tab_settings.canvas.configure(
                    background=colors["bg"]
                )
            if hasattr(self.tab_settings, "instructions") and self.tab_settings.instructions.winfo_exists():
                self.tab_settings.instructions.text_widget.configure(
                    background=colors["field_bg"],
                    foreground=colors["fg"]
                )

        if hasattr(self, "chat_text") and self.chat_text.winfo_exists():
            self.chat_text.configure(
                background=colors["field_bg"],
                foreground=colors["fg"],
                insertbackground=colors["fg"],
                selectbackground=colors["select_bg"]
            )

    def open_obs_dock(self):
        if self.obs_dock is not None and self.obs_dock.winfo_exists():
            self.obs_dock.lift()
            self.obs_dock.focus_force()
        else:
            self.obs_dock = OBSDockWindow(self.root, self.app_core, self)

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
        else:
            self._set_status(f"Активных платформ: {len(self.cards)}")

    def save_game_to_favorites(self):
        new_game = self.master_game.get().strip()
        if new_game:
            if self.app_core.game_service.add_favorite(new_game):
                games = self.app_core.game_service.get_favorites()
                master_cb = \
                    [w for w in self.tab_dashboard.winfo_children()[0].winfo_children() if isinstance(w, ttk.Combobox)][
                        0]
                master_cb['values'] = games

                for card in self.cards.values():
                    card.combo_game['values'] = games
            else:
                pass

    def _subscribe_events(self):
        self.app_core.event_bus.subscribe("plugins.loaded", self._on_plugins_loaded)
        self.app_core.event_bus.subscribe("stream.status_checked", self._on_status_checked)
        self.app_core.event_bus.subscribe("chat.message_received", self._on_chat_message_received)
        self.app_core.event_bus.subscribe("chat.message_deleted", self._on_chat_message_deleted)
        self.app_core.event_bus.subscribe("chat.user_banned", self._on_chat_user_banned)
        self.app_core.event_bus.subscribe("chat.message_id_updated", self._on_chat_message_id_updated)

    def _on_plugins_loaded(self, data: dict):
        self._build_platform_cards()

    def _on_status_checked(self, data: dict):
        platform = data.get("platform", "?")

        if platform in self.cards:
            self.cards[platform].update_data(data)

        is_live = data.get("is_live", False)

        self._set_status(
            f"Последнее обновление: {platform} — {'🟢 В ЭФИРЕ' if is_live else '🔴 оффлайн'}"
        )

    def on_apply_all(self):
        self.btn_apply_all.config(state="disabled")
        self._set_status("Выполняется массовое обновление...")
        asyncio.create_task(self._apply_all_async())

    def on_force_refresh(self):
        self.btn_refresh_now.config(state="disabled")
        self._set_status("Выполняется принудительный опрос платформ...")
        asyncio.create_task(self._force_refresh_async())

    async def _force_refresh_async(self):
        try:
            tasks = []
            for name, plugin in self.app_core.plugin_manager.all().items():
                if plugin.enabled:
                    async def single_update(p_name=name, p_plugin=plugin):
                        try:
                            status = await p_plugin.get_status()
                            status["platform"] = p_name
                            self.app_core.event_bus.emit("stream.status_checked", status)
                        except Exception as e:
                            logger.debug(f"Ошибка ручного обновления {p_name}: {e!r}")

                    tasks.append(single_update())

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self.btn_refresh_now.config(state="normal")
            self._set_status("Статусы платформ обновлены")

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
                elif r:
                    msgs.append(f"✅ {r}")

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
            if hasattr(self.app_core, "notification_service"):
                self.app_core.notification_service._show_toast("StreamTail работает в фоне")
        else:
            self._quit_app()

    def _show_tray_icon(self):
        if self.tray_icon:
            return

        def show_window(icon, item):
            icon.stop()
            self.tray_icon = None
            self._loop.call_soon_threadsafe(self.root.deiconify)

        def quit_app(icon, item):
            icon.stop()
            self.tray_icon = None
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
        # Безопасный асинхронный выход
        asyncio.create_task(self._quit_app_async())

    async def _quit_app_async(self):
        # 1. Сначала отключаем перехватчик логов во избежание TclError при уничтожении виджетов
        self.remove_loguru_sink()
        # 2. Ожидаем завершения всех фоновых задач, гасим серверы и закрываем сокеты чатов
        await self.app_core.shutdown_async()
        # 3. Уничтожаем окно Tkinter в последнюю очередь, мягко прерывая async_mainloop
        self.root.destroy()
