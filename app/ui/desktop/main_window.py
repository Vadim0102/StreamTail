import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
from app.utils.logger import logger


class PlatformCard(ttk.LabelFrame):
    def __init__(self, parent, platform, app_core, *args, **kwargs):
        super().__init__(parent, text=f" {platform.upper()} ", padding=15, *args, **kwargs)
        self.platform = platform
        self.app_core = app_core

        self.lbl_status = ttk.Label(self, text="Ожидание...", font=("Segoe UI", 11, "bold"))
        self.lbl_status.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        self.lbl_viewers = ttk.Label(self, text="👁 Зрители: 0", font=("Segoe UI", 10))
        self.lbl_viewers.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 15))

        ttk.Label(self, text="Название:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w")
        self.title_var = tk.StringVar()
        self.entry_title = ttk.Entry(self, textvariable=self.title_var, width=28)
        self.entry_title.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(self, text="Категория:", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w")
        self.game_var = tk.StringVar()
        self.combo_game = ttk.Combobox(self, textvariable=self.game_var,
                                       values=self.app_core.game_service.get_favorites(), width=26)
        self.combo_game.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

        self.btn_apply = ttk.Button(self, text="Обновить платформу", command=self.on_apply)
        self.btn_apply.grid(row=4, column=0, columnspan=2, pady=(15, 0), sticky="ew")

        self.columnconfigure(1, weight=1)

    def update_data(self, data):
        is_live = data.get('is_live', False)
        status_text = "🟢 В ЭФИРЕ" if is_live else "🔴 ОФФЛАЙН"
        color = "#28a745" if is_live else "#dc3545"

        self.lbl_status.config(text=status_text, foreground=color)
        self.lbl_viewers.config(text=f"👁 Зрители: {data.get('viewers', 0)}")

        if self.focus_get() not in (self.entry_title, self.combo_game):
            self.title_var.set(data.get('title', self.title_var.get()))
            self.game_var.set(data.get('game', self.game_var.get()))

    def on_apply(self):
        # Вместо threading запускаем асинхронную таску прямо в Tkinter-Loop!
        self.btn_apply.config(state="disabled")
        asyncio.create_task(self._apply_async())

    async def _apply_async(self):
        try:
            title, game = self.title_var.get(), self.game_var.get()
            res = []
            if title: res.append(await self.app_core.stream_service.update_title(self.platform, title))
            if game:  res.append(await self.app_core.stream_service.update_game(self.platform, game))

            msg = "\n".join(res) if res else "Нет данных для обновления"
            messagebox.showinfo(f"{self.platform} - Результат", msg)
        except Exception as e:
            logger.error(f"UI Ошибка обновления {self.platform}: {e}")
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.btn_apply.config(state="normal")


class StreamTailGUI:
    def __init__(self, app_core):
        self.app_core = app_core
        self.root = tk.Tk()
        self.root.title(f"StreamTail v{app_core.config['app']['version']} - Stream Manager")
        self.root.geometry("850x500")
        self.root.minsize(700, 450)

        self._set_theme()
        self._build_ui()
        self._subscribe_events()

    def _set_theme(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("TLabelframe", font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", foreground="#0056b3")
        style.configure("Master.TButton", font=("Segoe UI", 10, "bold"), background="#007bff", foreground="white")

    def _build_ui(self):
        main_container = ttk.Frame(self.root, padding=15)
        main_container.pack(fill=tk.BOTH, expand=True)

        master_frame = ttk.LabelFrame(main_container, text=" Массовое управление (Все платформы) ", padding=15)
        master_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(master_frame, text="Общее название:").grid(row=0, column=0, sticky="w")
        self.master_title = tk.StringVar()
        ttk.Entry(master_frame, textvariable=self.master_title).grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        ttk.Label(master_frame, text="Общая категория:").grid(row=1, column=0, sticky="w")
        self.master_game = tk.StringVar()
        ttk.Combobox(master_frame, textvariable=self.master_game,
                     values=self.app_core.game_service.get_favorites()).grid(row=1, column=1, sticky="ew", padx=10,
                                                                             pady=5)

        self.btn_apply_all = ttk.Button(master_frame, text="⚡ ПРИМЕНИТЬ КО ВСЕМ",
                                        style="Master.TButton", command=self.on_apply_all)
        self.btn_apply_all.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=5, pady=5, ipadx=10)
        master_frame.columnconfigure(1, weight=1)

        dash_frame = ttk.Frame(main_container)
        dash_frame.pack(fill=tk.BOTH, expand=True)

        self.cards = {}
        col = 0
        for name, plugin in self.app_core.plugin_manager.all().items():
            if plugin.enabled:
                card = PlatformCard(dash_frame, name, self.app_core)
                card.grid(row=0, column=col, sticky="nsew", padx=8, pady=5)
                dash_frame.columnconfigure(col, weight=1)
                self.cards[name] = card
                col += 1

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label = ttk.Label(status_frame, text=" Готов к работе", foreground="#555")
        self.status_label.pack(side=tk.LEFT, padx=10, pady=5)

    def _subscribe_events(self):
        self.app_core.event_bus.subscribe("stream.status_checked", self._on_status_checked)

    def _on_status_checked(self, data):
        platform = data.get('platform')
        if platform in self.cards:
            self.cards[platform].update_data(data)
            self.status_label.config(text=f" Последнее обновление: {platform} синхронизирован")

    def on_apply_all(self):
        self.btn_apply_all.config(state="disabled")
        self.status_label.config(text=" Выполняется массовое обновление...")
        asyncio.create_task(self._apply_all_async())

    async def _apply_all_async(self):
        try:
            title, game = self.master_title.get(), self.master_game.get()
            platforms = [n for n, p in self.app_core.plugin_manager.all().items() if p.enabled]

            # Параллельное выполнение запросов ко всем платформам (в 3 раза быстрее!)
            tasks = []
            for p in platforms:
                if title: tasks.append(self.app_core.stream_service.update_title(p, title))
                if game:  tasks.append(self.app_core.stream_service.update_game(p, game))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Фильтрация успешных и ошибочных
            msgs = [str(r) for r in results if r]
            messagebox.showinfo("Результат", "\n".join(msgs) if msgs else "Нечего обновлять")
        finally:
            self.btn_apply_all.config(state="normal")
            self.status_label.config(text=" Готов к работе")
