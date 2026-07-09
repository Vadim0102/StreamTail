import tkinter as tk
from tkinter import ttk, messagebox
from app.utils import db
from app.utils.config import save_config


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

        instructions = (
            "🔑 ОБЩИЙ REDIRECT URI для всех платформ: http://localhost:19234/callback\n\n"
            "🎮 1. TWITCH:\n"
            "   • Перейдите на: https://dev.twitch.tv/console\n"
            "   • Зарегистрируйте приложение. В поле 'OAuth Redirect URL' укажите: http://localhost:19234/callback\n"
            "   • Скопируйте 'Client ID' и сгенерируйте 'Client Secret'.\n\n"
            "🎥 2. YOUTUBE (Google Cloud):\n"
            "   • Перейдите на: https://console.cloud.google.com/\n"
            "   • Создайте проект, перейдите в Библиотеку API и включите 'YouTube Data API v3'.\n"
            "   • В разделе 'Учетные данные' создайте 'Идентификатор клиента OAuth 2.0' (Веб-приложение).\n"
            "   • Введите разрешенный URI перенаправления: http://localhost:19234/callback\n"
            "   • Заберите ваши 'Client ID' и 'Client Secret'.\n\n"
            "🌐 3. VK LIVE (Авторизация в обход ограничений сторонних приложений):\n"
            "   • Owner ID: Введите имя вашего канала в VK (то, что написано в конце ссылки, например, 'vadimzaa' или цифровой ID блога).\n"
            "   • Скопируйте официальный токен сайта (Client ID/Secret заполнять не требуется!):\n"
            "     1. Откройте сайт https://live.vkvideo.ru в вашем обычном браузере, где выполнен вход.\n"
            "     2. Нажмите F12 (или Ctrl+Shift+I) и перейдите во вкладку Application (Приложение / Хранилище).\n"
            "     3. Слева раскройте ветку 'Local Storage' (Локальное хранилище) и выберите адрес 'https://live.vkvideo.ru'.\n"
            "     4. Справа найдите ключ с именем 'auth' и скопируйте всю его длинную JSON-строку (она начинается с {\"accessToken\": ...}).\n"
            "     5. Вставьте эту скопированную строку целиком в поле 'Токен' для VK LIVE ниже. Плагин сам её расшифрует!\n\n"
            "🏆 4. GOODGAME:\n"
            "   • Перейдите в настройки своего профиля GoodGame -> вкладка OAuth / Разработчикам.\n"
            "   • Зарегистрируйте приложение, указав Redirect URI: http://localhost:19234/callback\n"
            "   • Скопируйте Client ID и Client Secret. Внимание: scope указывать не нужно.\n\n"
            "🇷🇺 5. RUTUBE (Обход блокировок QRATOR):\n"
            "   • ID Канала: Достаточно указать имя канала (публично) для чтения онлайна.\n"
            "   • ID Стрима: Скопируйте уникальный ID из адресной страницы страницы трансляции в Студии (например, 'f290551824869de96ec29760e731385d' из ссылки https://studio.rutube.ru/stream/f290551824869de96ec29760e731385d).\n"
            "   • Токен: Выгрузите куки RUTUBE через Cookie Quick Manager (JSON) или Get cookies.txt LOCALLY (Netscape) и вставьте весь скопированный текст целиком в поле Токен. Плагин автоматически обнаружит куки, вытащит необходимые CSRF-токены защиты и сможет менять заголовки в обход Cloudflare!\n\n"
            "💚 6. KICK:\n"
            "   • Имя канала: введите имя. Если случайно ввели ссылку, плагин очистит её сам.\n"
            "   • Токен (Два метода на выбор):\n"
            "     а) ОФИЦИАЛЬНЫЙ API (Рекомендуется): Зарегистрируйте приложение в кабинете разработчика https://kick.com/settings/developer , скопируйте выданный Bearer Token и вставьте его сюда. Этот метод работает на 100% надежно и никогда не блокируется Cloudflare. URL перенаправления: http://localhost:19234/callback\n"
            "     б) НЕОФИЦИАЛЬНЫЙ API (Через Cookies браузера): Откройте сайт Kick.com в режиме инкогнито или в обычном браузере, где вы авторизованы. Нажмите F12 -> перейдите во вкладку Network (Сеть). Обновите страницу или отправьте тестовое сообщение в чат. Найдите любой уходящий запрос к сайту, скопируйте всю длинную строку из заголовка 'Cookie' (в ней содержатся session_token, cf_clearance и XSRF-TOKEN) и вставьте её целиком сюда. Плагин автоматически обнаружит куки, вытащит необходимые CSRF-токены защиты и сможет менять заголовки в обход Cloudflare!"
        )
        self.text_widget.insert("1.0", instructions)
        self.text_widget.config(state="disabled")

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
        # 1. Закрепленный нижний бар (Bottom Bar) для кнопки Сохранить (она всегда прижата к низу)
        bottom_bar = ttk.Frame(self, padding=(0, 10, 0, 0))
        bottom_bar.pack(side="bottom", fill="x")

        self.btn_save = ttk.Button(bottom_bar, text="💾 Сохранить настройки", command=self.save_settings)
        self.btn_save.pack(fill="x")

        # 2. Создаем независимую скроллируемую область для полей настроек (без жесткого цвета фона)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas, padding=10)

        # Регулируем размер прокрутки
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        # Сохраняем окно холста
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # УЛУЧШЕНИЕ: Растягиваем внутренний фрейм настроек на ВСЮ ширину при изменении размера окна!
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

        # Развертываемая инструкция
        self.instructions = CollapsibleInstruction(self.scrollable_frame)
        self.instructions.pack(fill="x", pady=(0, 15))

        # --- Основные настройки ---
        app_frame = ttk.LabelFrame(self.scrollable_frame, text=" Основные настройки ", padding=10)
        app_frame.pack(fill="x", pady=5)

        self.hide_to_tray_var = tk.BooleanVar(value=db.get_setting("hide_to_tray", True))
        self.cb_tray = ttk.Checkbutton(
            app_frame,
            text="Сворачивать в трей при закрытии приложения (крестик)",
            variable=self.hide_to_tray_var
        )
        self.cb_tray.pack(anchor="w", pady=5)

        # Интервал проверки
        check_frame = ttk.Frame(app_frame)
        check_frame.pack(fill="x", pady=5)
        ttk.Label(check_frame, text="Интервал проверки статуса (сек):").pack(side="left")
        self.interval_var = tk.StringVar(value=str(self.app_core.config["app"].get("check_interval", 15)))
        self.entry_interval = ttk.Entry(check_frame, textvariable=self.interval_var, width=10)
        self.entry_interval.pack(side="left", padx=10)

        # Поле ввода Прокси
        proxy_frame = ttk.Frame(app_frame)
        proxy_frame.pack(fill="x", pady=5)
        ttk.Label(proxy_frame, text="Глобальный прокси-сервер (http/socks5):").pack(side="left")
        self.proxy_var = tk.StringVar(value=str(self.app_core.config["app"].get("proxy_url", "")))
        self.entry_proxy = ttk.Entry(proxy_frame, textvariable=self.proxy_var, width=35)
        self.entry_proxy.pack(side="left", padx=10)

        # Выбор темы оформления
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

        # --- Настройки платформ ---
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

        # КЛЮЧЕВОЕ УЛУЧШЕНИЕ: Рекурсивно привязываем прокрутку колесика мыши ко всем элементам!
        self._bind_mouse_wheel(self)

    def _on_mouse_wheel(self, event):
        """Кроссплатформенный обработчик прокрутки колесика мыши."""
        if event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")

    def _bind_mouse_wheel(self, widget):
        """Рекурсивно биндит события прокрутки мыши на все вложенные элементы формы."""
        widget.bind("<MouseWheel>", self._on_mouse_wheel, add="+")
        widget.bind("<Button-4>", self._on_mouse_wheel, add="+")
        widget.bind("<Button-5>", self._on_mouse_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_mouse_wheel(child)

    def save_settings(self):
        # Блокируем кнопку сохранения для защиты от дребезга и двойных кликов!
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

            # СОХРАНЯЕМ ТЕМУ ОФОРМЛЕНИЯ
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

            # Динамически применяем тему ко всем открытым окнам на лету!
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
