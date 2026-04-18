import tkinter as tk
from tkinter import ttk, messagebox
import threading


class PlatformCard(ttk.LabelFrame):
    def __init__(self, parent, platform, app_core, *args, **kwargs):
        super().__init__(parent, text=f" {platform.upper()} ", padding=15, *args, **kwargs)
        self.platform = platform
        self.app_core = app_core

        # Элементы интерфейса карточки
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

        btn_apply = ttk.Button(self, text="Обновить платформу", command=self.apply_changes)
        btn_apply.grid(row=4, column=0, columnspan=2, pady=(15, 0), sticky="ew")

        self.columnconfigure(1, weight=1)

    def update_data(self, data):
        is_live = data.get('is_live', False)
        status_text = "🟢 В ЭФИРЕ" if is_live else "🔴 ОФФЛАЙН"
        color = "#28a745" if is_live else "#dc3545"

        self.lbl_status.config(text=status_text, foreground=color)
        self.lbl_viewers.config(text=f"👁 Зрители: {data.get('viewers', 0)}")

        # Не перезаписываем поля, если пользователь прямо сейчас в них что-то пишет
        if self.focus_get() not in (self.entry_title, self.combo_game):
            self.title_var.set(data.get('title', self.title_var.get()))
            self.game_var.set(data.get('game', self.game_var.get()))

    def apply_changes(self):
        title = self.title_var.get()
        game = self.game_var.get()

        def worker():
            res = []
            if title: res.append(self.app_core.stream_service.update_title(self.platform, title))
            if game: res.append(self.app_core.stream_service.update_game(self.platform, game))
            self.after(0, lambda: messagebox.showinfo(f"{self.platform} - Результат",
                                                      "\n".join(res) if res else "Нет данных для обновления"))

        threading.Thread(target=worker, daemon=True).start()


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
            style.theme_use("clam")  # Современная гладкая тема

        style.configure("TLabelframe", font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", foreground="#0056b3")
        style.configure("TButton", font=("Segoe UI", 9))
        style.configure("Master.TButton", font=("Segoe UI", 10, "bold"), background="#007bff", foreground="white")

    def _build_ui(self):
        main_container = ttk.Frame(self.root, padding=15)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Мастер-панель (Общее управление)
        master_frame = ttk.LabelFrame(main_container, text=" Массовое управление (Все платформы) ", padding=15)
        master_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(master_frame, text="Общее название:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=5)
        self.master_title = tk.StringVar()
        ttk.Entry(master_frame, textvariable=self.master_title, font=("Segoe UI", 10)).grid(row=0, column=1,
                                                                                            sticky="ew", padx=10,
                                                                                            pady=5)

        ttk.Label(master_frame, text="Общая категория:", font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w",
                                                                                     padx=5)
        self.master_game = tk.StringVar()
        ttk.Combobox(master_frame, textvariable=self.master_game, values=self.app_core.game_service.get_favorites(),
                     font=("Segoe UI", 10)).grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        btn_apply_all = ttk.Button(master_frame, text="⚡ ПРИМЕНИТЬ КО ВСЕМ", style="Master.TButton",
                                   command=self.apply_all)
        btn_apply_all.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=5, pady=5, ipadx=10)

        master_frame.columnconfigure(1, weight=1)

        # Дашборд платформ
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

        # Статус бар
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label = ttk.Label(status_frame, text=" Готов к работе", font=("Segoe UI", 9, "italic"),
                                      foreground="#555")
        self.status_label.pack(side=tk.LEFT, padx=10, pady=5)

    def _subscribe_events(self):
        self.app_core.event_bus.subscribe("stream_status_checked", self._on_status_checked)

    def _on_status_checked(self, data):
        def update():
            platform = data.get('platform')
            if platform in self.cards:
                self.cards[platform].update_data(data)
                self.status_label.config(text=f" Последнее обновление: {platform} синхронизирован")

        self.root.after(0, update)

    def apply_all(self):
        title = self.master_title.get()
        game = self.master_game.get()
        platforms = [n for n, p in self.app_core.plugin_manager.all().items() if p.enabled]

        self.status_label.config(text=" Выполняется массовое обновление...")

        def worker():
            results = []
            for p in platforms:
                if title: results.append(self.app_core.stream_service.update_title(p, title))
                if game: results.append(self.app_core.stream_service.update_game(p, game))

            results = [r for r in results if r]
            self.root.after(0, lambda: messagebox.showinfo("Результат",
                                                           "\n".join(results) if results else "Нечего обновлять"))
            self.root.after(0, lambda: self.status_label.config(text=" Готов к работе"))

        threading.Thread(target=worker, daemon=True).start()

    def run(self):
        self.root.mainloop()
