import tkinter as tk
from tkinter import ttk, messagebox


class StreamTailGUI:
    def __init__(self, app_core):
        self.app_core = app_core
        self.stream_service = app_core.stream_service
        self.plugin_manager = app_core.plugin_manager

        self.root = tk.Tk()
        self.root.title("StreamTail - Ultimate Stream Manager")
        self.root.geometry("450x350")
        self.root.resizable(False, False)

        self._build_ui()
        self._subscribe_events()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')

        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Выбор платформы
        ttk.Label(main_frame, text="Платформа:", font=('Helvetica', 10, 'bold')).pack(anchor="w")
        self.platform_var = tk.StringVar()
        platforms = list(self.plugin_manager.all().keys())
        self.platform_combo = ttk.Combobox(main_frame, textvariable=self.platform_var, values=platforms,
                                           state="readonly")
        if platforms:
            self.platform_combo.current(0)
        self.platform_combo.pack(fill=tk.X, pady=(0, 15))

        # Заголовок стрима
        ttk.Label(main_frame, text="Название трансляции:", font=('Helvetica', 10, 'bold')).pack(anchor="w")
        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(main_frame, textvariable=self.title_var)
        self.title_entry.pack(fill=tk.X, pady=(0, 15))

        # Категория (Игра)
        ttk.Label(main_frame, text="Категория / Игра:", font=('Helvetica', 10, 'bold')).pack(anchor="w")
        self.game_var = tk.StringVar()
        self.game_entry = ttk.Entry(main_frame, textvariable=self.game_var)
        self.game_entry.pack(fill=tk.X, pady=(0, 20))

        # Кнопка применения
        self.apply_btn = ttk.Button(main_frame, text="Обновить информацию", command=self.apply_changes)
        self.apply_btn.pack(fill=tk.X, pady=(0, 10))

        # Статус
        self.status_label = ttk.Label(main_frame, text="Статус: Ожидание...", foreground="gray")
        self.status_label.pack(side=tk.BOTTOM, anchor="w")

    def _subscribe_events(self):
        # Подписываемся на события из фонового потока (Scheduler)
        self.app_core.event_bus.subscribe("stream_status_checked", self._on_status_checked)

    def _on_status_checked(self, data):
        # Обновление UI из другого потока может быть опасным в Tkinter,
        # но для простых меток обычно работает. Лучше использовать root.after
        platform = data['platform']
        is_live = data['is_live']
        if self.platform_var.get() == platform:
            status_text = "🟢 В эфире" if is_live else "🔴 Оффлайн"
            self.root.after(0, lambda: self.status_label.config(text=f"Статус ({platform}): {status_text}"))

    def apply_changes(self):
        platform = self.platform_var.get()
        title = self.title_var.get()
        game = self.game_var.get()

        if not platform:
            messagebox.showwarning("Ошибка", "Выберите платфорту!")
            return

        results = []

        # Вызываем методы сервиса, если поля не пустые
        if title:
            res_title = self.stream_service.update_title(platform, title)
            results.append(str(res_title))
        if game:
            res_game = self.stream_service.update_game(platform, game)
            results.append(str(res_game))

        # Выводим результат пользователю
        if results:
            messagebox.showinfo("Успех", "\n".join(results))
        else:
            messagebox.showinfo("Внимание", "Заполните хотя бы одно поле для обновления.")

    def run(self):
        # Запуск главного цикла окна
        self.root.mainloop()
