import tkinter as tk
from tkinter import ttk, messagebox
from app.utils import db
from app.utils.config import save_config
from app.utils.paths import get_asset_path
from app.utils.logger import logger


class CollapsibleInstruction(ttk.Frame):
    def __init__(self, parent, title="❓ Инструкция: Как получить ID и секреты платформ", *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.collapsed = True

        self.btn = ttk.Button(self, text="▶ Показать инструкцию по авторизации", command=self.toggle)
        self.btn.pack(fill="x")

        self.content_frame = ttk.Frame(self, padding=10)

        self.text_widget = tk.Text(
            self.content_frame,
            height=18,
            wrap="word",
            font=("Segoe UI", 9),
            background="#2a2a3a",
            foreground="#cdd6f4",
            relief="flat",
            padx=10,
            pady=10
        )
        self.text_widget.pack(fill="both", expand=True)

        # Динамическая загрузка внешней инструкции
        instructions = self._load_instructions()
        self.text_widget.insert("1.0", instructions)
        self.text_widget.config(state="disabled")

    def _load_instructions(self) -> str:
        try:
            path = get_asset_path("instructions.txt")
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            logger.debug(f"Не удалось загрузить инструкции из внешнего файла: {e!r}")

        return "Ошибка: Файл инструкций 'assets/instructions.txt' не найден."

    def toggle(self):
        if self.collapsed:
            self.content_frame.pack(fill="both", expand=True, pady=5)
            self.btn.config(text="▼ Скрыть инструкцию по авторизации")
            self.collapsed = False
        else:
            self.content_frame.pack_forget()
            self.btn.config(text="▶ Показать инструкцию по авторизации")
            self.collapsed = True


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app_core, *args, **kwargs):
        super().__init__(parent, padding=15, *args, **kwargs)
        self.app_core = app_core
        self._build_ui()

    def _build_ui(self):
        bottom_bar = ttk.Frame(self, padding=(0, 10, 0, 0))
        bottom_bar.pack(side="bottom", fill="x")

        self.btn_save = ttk.Button(bottom_bar, text="💾 Сохранить настройки", command=self.save_settings)
        self.btn_save.pack(fill="x")

        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas, padding=10)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )

        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        ttk.Label(
            self.scrollable_frame,
            text="⚙️ Настройки StreamTail",
            font=("Segoe UI", 16, "bold")
        ).pack(anchor="w", pady=(0, 10))

        self.instructions = CollapsibleInstruction(self.scrollable_frame)
        self.instructions.pack(fill="x", pady=(0, 15))

        app_frame = ttk.LabelFrame(self.scrollable_frame, text=" Основные настройки ", padding=10)
        app_frame.pack(fill="x", pady=5)

        self.hide_to_tray_var = tk.BooleanVar(value=db.get_setting("hide_to_tray", True))
        self.cb_tray = ttk.Checkbutton(
            app_frame,
            text="Сворачивать в трей при закрытии приложения (крестик)",
            variable=self.hide_to_tray_var
        )
        self.cb_tray.pack(anchor="w", pady=5)

        check_frame = ttk.Frame(app_frame)
        check_frame.pack(fill="x", pady=5)
        ttk.Label(check_frame, text="Интервал проверки статуса (сек):").pack(side="left")
        self.interval_var = tk.StringVar(value=str(self.app_core.config["app"].get("check_interval", 15)))
        self.entry_interval = ttk.Entry(check_frame, textvariable=self.interval_var, width=10)
        self.entry_interval.pack(side="left", padx=10)

        proxy_frame = ttk.Frame(app_frame)
        proxy_frame.pack(fill="x", pady=5)
        ttk.Label(proxy_frame, text="Глобальный прокси-сервер (http/socks5):").pack(side="left")
        self.proxy_var = tk.StringVar(value=str(self.app_core.config["app"].get("proxy_url", "")))
        self.entry_proxy = ttk.Entry(proxy_frame, textvariable=self.proxy_var, width=35)
        self.entry_proxy.pack(side="left", padx=10)

        theme_frame = ttk.Frame(app_frame)
        theme_frame.pack(fill="x", pady=5)
        ttk.Label(theme_frame, text="Тема оформления интерфейса:").pack(side="left")

        from app.utils import theme_manager
        self.theme_var = tk.StringVar(value=theme_manager.get_current_theme_name())
        self.combo_theme = ttk.Combobox(
            theme_frame,
            textvariable=self.theme_var,
            values=list(theme_manager.THEMES.keys()),
            state="readonly",
            width=25
        )
        self.combo_theme.pack(side="left", padx=10)

        self.platform_entries = {}
        platforms_config = self.app_core.config.get("platforms", {})

        for plat_name in ["twitch", "youtube", "livevk", "kick", "rutube", "goodgame"]:
            plat_cfg = platforms_config.get(plat_name, {})
            p_frame = ttk.LabelFrame(self.scrollable_frame, text=f" {plat_name.upper()} ", padding=10)
            p_frame.pack(fill="x", pady=5)

            enabled_var = tk.BooleanVar(value=plat_cfg.get("enabled", True))
            ttk.Checkbutton(p_frame, text="Включена", variable=enabled_var).grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 5)
            )

            self.platform_entries[plat_name] = {"enabled": enabled_var}

            fields = []
            if plat_name in ["twitch", "youtube", "goodgame"]:
                fields.append(("client_id", "Client ID:"))
                fields.append(("client_secret", "Client Secret:"))

            if plat_name == "livevk":
                fields.append(("owner_id", "Owner ID (ID или имя канала):"))
                fields.append(("client_id", "Client ID (Необязательно):"))
                fields.append(("client_secret", "Client Secret (Необязательно):"))
                fields.append(("token", "Токен (JSON 'auth' из LocalStorage):"))

            if plat_name == "goodgame":
                fields.append(("channel", "Имя канала (Slug/Username):"))

            if plat_name == "kick":
                fields.append(("channel", "Имя канала (Slug/Username):"))
                fields.append(("client_id", "Client ID (для Официального API):"))
                fields.append(("client_secret", "Client Secret (для Официального API):"))
                fields.append(("token", "Токен / Cookies браузера (для Неофициального):"))

            if plat_name == "rutube":
                fields.append(("channel_id", "ID Канала или имя:"))
                fields.append(("broadcast_id", "ID Стрима (из ссылки Студии) (необязательно):"))
                fields.append(("token", "Studio API Token (или куки из браузера):"))

            row = 1
            for key, label_text in fields:
                ttk.Label(p_frame, text=label_text).grid(row=row, column=0, sticky="w", pady=2)
                var = tk.StringVar(value=str(plat_cfg.get(key, "")))
                entry = ttk.Entry(p_frame, textvariable=var, width=45)
                if key in ["client_secret", "token"]:
                    entry.config(show="*")
                entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
                p_frame.columnconfigure(1, weight=1)

                self.platform_entries[plat_name][key] = var
                row += 1

        self._bind_mouse_wheel(self)

    def _on_mouse_wheel(self, event):
        if event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")

    def _bind_mouse_wheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mouse_wheel, add="+")
        widget.bind("<Button-4>", self._on_mouse_wheel, add="+")
        widget.bind("<Button-5>", self._on_mouse_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_mouse_wheel(child)

    def save_settings(self):
        self.btn_save.config(state="disabled")
        try:
            try:
                check_interval = int(self.interval_var.get().strip())
                if check_interval < 5:
                    raise ValueError()
            except Exception:
                messagebox.showerror("Ошибка", "Интервал проверки должен быть числом >= 5 сек.")
                return

            db.set_setting("hide_to_tray", self.hide_to_tray_var.get())

            new_config = dict(self.app_core.config)
            new_config["app"]["check_interval"] = check_interval
            new_config["app"]["proxy_url"] = self.proxy_var.get().strip()

            selected_theme = self.theme_var.get()
            db.set_setting("theme_name", selected_theme)

            for plat_name, vars_dict in self.platform_entries.items():
                if plat_name not in new_config["platforms"]:
                    new_config["platforms"][plat_name] = {}

                plat_cfg = new_config["platforms"][plat_name]
                plat_cfg["enabled"] = vars_dict["enabled"].get()

                for key, var in vars_dict.items():
                    if key != "enabled":
                        plat_cfg[key] = var.get().strip()

            self.app_core.update_app_config(new_config)

            from app.utils import theme_manager
            theme_manager.apply_theme(self.app_core.gui.root)
            self.app_core.gui.apply_theme_to_custom_widgets()

            messagebox.showinfo("Успех", "Настройки успешно обновлены!")
            self.app_core.event_bus.emit("plugins.loaded", {})

            if hasattr(self.app_core.gui, "tab_auth"):
                self.app_core.gui.tab_auth.update_statuses()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {e}")
        finally:
            self.btn_save.config(state="normal")
