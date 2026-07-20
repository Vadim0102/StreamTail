## `app/ui/desktop/main_window.py`
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import sv_ttk
from datetime import datetime
from PIL import Image, ImageDraw, ImageTk
from app.utils.logger import logger
from app.ui.desktop.auth_tab import AuthTab
from app.ui.desktop.settings_tab import SettingsTab
from app.utils import db
from app.core import __version__

try:
    import pystray
    TRAY_SUPPORTED = True
except ImportError:
    TRAY_SUPPORTED = False
    logger.warning("pystray не установлен. Функции системного трея отключены.")

# Мягкие, пастельные брендовые цвета для темной и светлой темы (невырвиглазные)
BRAND_COLORS = {
    "dark": {
        "twitch": {"bg": "#1f182d", "accent": "#a28cf2"},
        "youtube": {"bg": "#2b1819", "accent": "#f28c8c"},
        "livevk": {"bg": "#181f2d", "accent": "#8caef2"},
        "kick": {"bg": "#182d19", "accent": "#8cf290"},
        "goodgame": {"bg": "#2b2118", "accent": "#f2b58c"},
        "rutube": {"bg": "#18272d", "accent": "#8ce2f2"},
    },
    "light": {
        "twitch": {"bg": "#f5effa", "accent": "#6441a5"},
        "youtube": {"bg": "#fbebeb", "accent": "#ff0000"},
        "livevk": {"bg": "#ebf1fb", "accent": "#0077ff"},
        "kick": {"bg": "#ebfbeb", "accent": "#53fc18"},
        "goodgame": {"bg": "#faf2eb", "accent": "#ff7300"},
        "rutube": {"bg": "#ebf6fa", "accent": "#00b2ff"},
    }
}


class PlatformCard(tk.LabelFrame):
    def __init__(self, parent, platform: str, app_core, *args, **kwargs):
        self.platform = platform
        self.app_core = app_core

        # Определение текущей цветовой палитры в зависимости от темы
        from app.utils import theme_manager
        theme_name = theme_manager.get_current_theme_name()
        theme_type = "light" if "Светлая" in theme_name else "dark"
        colors = theme_manager.get_theme_colors()

        self.brand = BRAND_COLORS[theme_type].get(platform.lower(), BRAND_COLORS[theme_type]["twitch"])

        # Нативный контейнер позволяет беспрепятственно управлять фоном карточки
        super().__init__(
            parent,
            text=f"  {platform.upper()}  ",
            font=("Segoe UI", 10, "bold"),
            bg=self.brand["bg"],
            fg=self.brand["accent"],
            relief=tk.SOLID,
            bd=0,
            padx=12,
            pady=12,
            *args, **kwargs
        )
        self.configure(
            highlightbackground=self.brand["accent"],
            highlightcolor=self.brand["accent"],
            highlightthickness=1
        )

        # Статус теперь занимает обе колонки сверху
        self.lbl_status = tk.Label(
            self,
            text="Ожидание...",
            font=("Segoe UI", 11, "bold"),
            bg=self.brand["bg"],
            fg=colors["fg"]
        )
        self.lbl_status.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        self.lbl_viewers = tk.Label(
            self,
            text="👁 Зрители: —",
            font=("Segoe UI", 10),
            bg=self.brand["bg"],
            fg=colors["fg"]
        )
        self.lbl_viewers.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 15))

        tk.Label(
            self,
            text="Название:",
            font=("Segoe UI", 9),
            bg=self.brand["bg"],
            fg=colors["fg"]
        ).grid(row=2, column=0, sticky="w")

        self.title_var = tk.StringVar()
        self.entry_title = ttk.Entry(self, textvariable=self.title_var, width=28)
        self.entry_title.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        tk.Label(
            self,
            text="Категория:",
            font=("Segoe UI", 9),
            bg=self.brand["bg"],
            fg=colors["fg"]
        ).grid(row=3, column=0, sticky="w")

        self.game_var = tk.StringVar()
        self.combo_game = ttk.Combobox(
            self,
            textvariable=self.game_var,
            values=self.app_core.game_service.get_favorites(),
            width=26,
        )
        self.combo_game.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

        # Контейнер для кнопок управления на пятой строке
        self.apply_frame = tk.Frame(self, bg=self.brand["bg"])
        self.apply_frame.grid(row=4, column=0, columnspan=2, pady=(15, 0), sticky="ew")

        # Создаем дополнительные кнопки управления заранее, но не размещаем в сетке [2.1]
        self.btn_publish = ttk.Button(
            self.apply_frame, text="📢 Опубликовать", command=self.on_publish
        )
        self.btn_stop = ttk.Button(
            self.apply_frame, text="🛑 Завершить", command=self.on_stop
        )

        if self.platform.lower() in ("youtube", "rutube"):
            # Кнопка-стрелка выбора трансляции (всегда слева, фиксированная) [2.1]
            self.btn_arrow = ttk.Button(
                self.apply_frame, text="▼", command=self.on_select_broadcast, width=4
            )
            self.btn_arrow.grid(row=0, column=0, sticky="w", padx=(0, 5))

            # Кнопка обновления по умолчанию в колонке 1 (так как кнопка превью 🖼 удалена) [2.1]
            self.btn_apply = ttk.Button(
                self.apply_frame, text="Обновить платформу", command=self.on_apply
            )
            self.btn_apply.grid(row=0, column=1, sticky="ew")

            self.apply_frame.columnconfigure(0, weight=0)
            self.apply_frame.columnconfigure(1, weight=1)
        else:
            # Для остальных платформ кнопка занимает всю ширину строки
            self.btn_apply = ttk.Button(
                self.apply_frame, text="Обновить платформу", command=self.on_apply
            )
            self.btn_apply.grid(row=0, column=0, columnspan=2, sticky="ew")
            self.apply_frame.columnconfigure(0, weight=1)

        self.columnconfigure(1, weight=1)

    def update_data(self, data: dict):
        is_live = data.get("is_live", False)

        # 1. Читаем кастомный статус (например, 🟡 НА ПОДГОТОВКЕ), если его прислал плагин [2.1]
        status_text = data.get("custom_status")
        if not status_text:
            status_text = "🟢 В ЭФИРЕ" if is_live else "🔴 ОФФЛАЙН"

        # Получаем контрастные цвета из Theme Manager
        from app.utils import theme_manager
        colors = theme_manager.get_theme_colors()

        # Назначаем цвет статуса в зависимости от его содержимого [2.1]
        if "В ЭФИРЕ" in status_text or "🟢" in status_text:
            color = colors["text_green"]
        elif "ПОДГОТОВКЕ" in status_text or "🟡" in status_text:
            color = colors["text_sec"]  # Акцентный синий/желтый цвет
        else:
            color = colors["text_red"]

        self.lbl_status.config(text=status_text, foreground=color)

        # 2. Вывод просмотров + Лайков и Дизлайков (👍 / 👎) [2.1]
        viewers_text = f"👁 Зрители: {data.get('viewers', 0)}"
        if "likes" in data or "dislikes" in data:
            likes = data.get("likes", 0)
            dislikes = data.get("dislikes", 0)
            viewers_text += f"  |  👍 {likes}  |  👎 {dislikes}"
        self.lbl_viewers.config(text=viewers_text)

        # 3. Динамическое управление кнопками Опубликовать / Завершить (поддерживает YouTube, Rutube, VK Live) [2.1]
        if self.platform.lower() in ("youtube", "rutube", "livevk"):
            needs_publish = data.get("needs_publish", False)
            can_stop = data.get("can_stop", False)

            # Очищаем сетку от возможных старых размещений
            self.btn_publish.grid_forget()
            self.btn_stop.grid_forget()

            # Начальная колонка размещения кнопок зависит от наличия стрелочки ▼
            start_col = 1 if self.platform.lower() in ("youtube", "rutube") else 0
            col_index = start_col

            if needs_publish:
                # Помещаем кнопку публикации
                self.btn_publish.grid(row=0, column=col_index, sticky="ew", padx=(0, 5))
                col_index += 1
            elif can_stop:
                # Помещаем кнопку завершения
                self.btn_stop.grid(row=0, column=col_index, sticky="ew", padx=(0, 5))
                col_index += 1

            # Размещаем кнопку обновления в финальной (самой правой) колонке
            self.btn_apply.grid(row=0, column=col_index, sticky="ew")

            # Перенастраиваем веса колонок внутри apply_frame на лету
            if start_col == 1:
                self.apply_frame.columnconfigure(0, weight=0)  # Стрелочка всегда фиксированная
            for i in range(start_col, col_index):
                self.apply_frame.columnconfigure(i, weight=0)  # Доп. кнопки фиксированные
            self.apply_frame.columnconfigure(col_index, weight=1)  # Кнопка Обновить растягивается

        # Автозаполнение названия и категории (если фокус не на полях)
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

    def on_publish(self):
        """Обработчик кнопки публикации [2.1]."""
        self.btn_publish.config(state="disabled")
        asyncio.create_task(self._publish_async())

    async def _publish_async(self):
        try:
            res = await self.app_core.stream_service.publish_stream(self.platform)
            messagebox.showinfo(f"{self.platform} — Публикация", res)

            # Принудительно запрашиваем обновление статуса после публикации
            plugin = self.app_core.plugin_manager.get(self.platform)
            if plugin:
                status = await plugin.get_status()
                status["platform"] = self.platform
                self.app_core.event_bus.emit("stream.status_checked", status)
        except Exception as e:
            logger.error(f"UI: ошибка публикации {self.platform}: {e}")
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.btn_publish.config(state="normal")

    def on_stop(self):
        """Обработчик кнопки завершения трансляции [2.1]."""
        if messagebox.askyesno("Подтверждение", f"Вы уверены, что хотите завершить трансляцию на {self.platform}?"):
            self.btn_stop.config(state="disabled")
            asyncio.create_task(self._stop_async())

    async def _stop_async(self):
        try:
            res = await self.app_core.stream_service.stop_stream(self.platform)
            messagebox.showinfo(f"{self.platform} — Завершение", res)

            # Принудительно запрашиваем обновление статуса после завершения
            plugin = self.app_core.plugin_manager.get(self.platform)
            if plugin:
                status = await plugin.get_status()
                status["platform"] = self.platform
                self.app_core.event_bus.emit("stream.status_checked", status)
        except Exception as e:
            logger.error(f"UI: ошибка завершения трансляции {self.platform}: {e}")
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.btn_stop.config(state="normal")

    def on_select_broadcast(self):
        """Всплывающее окно асинхронного выбора трансляций с поддержкой тем."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Выбор трансляции — {self.platform.upper()}")
        dialog.geometry("520x420")  # Увеличена высота под дополнительные элементы
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        lbl_loading = ttk.Label(dialog, text="⏳ Загрузка списка трансляций, пожалуйста подождите...",
                                font=("Segoe UI", 10))
        lbl_loading.pack(pady=10)

        # Стилизуем Listbox в соответствии с текущей темой
        from app.utils import theme_manager
        colors = theme_manager.get_theme_colors()

        listbox = tk.Listbox(
            dialog,
            font=("Consolas", 10),
            background=colors["field_bg"],
            foreground=colors["fg"],
            selectbackground=colors["select_bg"],
            selectforeground=colors["fg"],
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=0
        )
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

                    # ИСПРАВЛЕНО: приведение self.platform к .lower() для надежной записи в конфиги
                    if self.platform.lower() == "youtube":
                        from app.auth.token_store import get_token, set_token
                        tok = get_token("youtube") or {}
                        tok["broadcast_id"] = selected["id"]
                        set_token("youtube", tok)
                    elif self.platform.lower() == "rutube":
                        platform_cfg = config["platforms"].setdefault("rutube", {})
                        platform_cfg["broadcast_id"] = selected["id"]
                        self.app_core.update_app_config(config)

                    messagebox.showinfo("Успех", f"Успешно привязана трансляция:\n{selected['title']}", parent=dialog)
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

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill="x", padx=15, pady=10)

        btn_select = ttk.Button(btn_frame, text="✅ Выбрать трансляцию", command=save_selection)
        btn_select.pack(side="left", fill="x", expand=True, padx=(0, 5))

        # Кнопка быстрого создания нового стрима (поддерживает RUTUBE и YOUTUBE) [2.1]
        if self.platform.lower() in ("rutube", "youtube"):
            btn_create = ttk.Button(btn_frame, text="➕ Создать стрим",
                                    command=lambda: self.on_create_stream_dialog(dialog))
            btn_create.pack(side="right", fill="x", expand=True, padx=(5, 0))

    def on_create_stream_dialog(self, parent_dialog):
        """Всплывающее окно быстрого создания стрима с выбором обложки, ключей и режима Shorts [2.1]."""
        create_win = tk.Toplevel(parent_dialog)
        create_win.title(f"Создание трансляции на {self.platform.upper()}")
        create_win.geometry("450x550")  # Слегка увеличили ширину под новые элементы выбора
        create_win.transient(parent_dialog)
        create_win.grab_set()

        # Поля ввода
        ttk.Label(create_win, text="Название нового стрима:").pack(anchor="w", padx=15, pady=(15, 2))
        title_var = tk.StringVar(value=self.title_var.get())
        ttk.Entry(create_win, textvariable=title_var, width=45).pack(fill="x", padx=15, pady=2)

        # Категория/Игра
        ttk.Label(create_win, text="Категория/Игра:").pack(anchor="w", padx=15, pady=(10, 2))
        game_var = tk.StringVar()

        if self.platform.lower() == "youtube":
            # Для YouTube создаем выпадающий список популярных категорий [2.1]
            yt_categories = {
                "Игры (Gaming)": "20",
                "Люди и Блоги (People & Blogs)": "22",
                "Развлечения (Entertainment)": "24",
                "Музыка (Music)": "10",
                "Образование (Education)": "27",
                "Наука и Технологии (Science & Tech)": "28"
            }
            combo_game_yt = ttk.Combobox(create_win, textvariable=game_var, values=list(yt_categories.keys()),
                                         state="readonly", width=42)
            combo_game_yt.pack(fill="x", padx=15, pady=2)
            combo_game_yt.current(0)
        else:
            combo_game_other = ttk.Combobox(create_win, textvariable=game_var,
                                            values=self.app_core.game_service.get_favorites(), width=42)
            combo_game_other.pack(fill="x", padx=15, pady=2)
            game_var.set(self.game_var.get() or "Видеоигры")

        ttk.Label(create_win, text="Описание (необязательно):").pack(anchor="w", padx=15, pady=(10, 2))
        desc_var = tk.StringVar(value="Запланированная трансляция создана через StreamTail")
        ttk.Entry(create_win, textvariable=desc_var, width=45).pack(fill="x", padx=15, pady=2)

        # Выбор обложки/превью прямо в диалоге создания [2.1]
        ttk.Label(create_win, text="Превью/Обложка (необязательно):").pack(anchor="w", padx=15, pady=(10, 2))
        thumb_path_var = tk.StringVar()
        thumb_frame = ttk.Frame(create_win)
        thumb_frame.pack(fill="x", padx=15, pady=2)

        ttk.Entry(thumb_frame, textvariable=thumb_path_var, width=32).pack(side="left", fill="x", expand=True)

        def choose_thumb():
            from tkinter import filedialog
            p = filedialog.askopenfilename(
                title="Выберите обложку (JPG/PNG)",
                filetypes=[("Изображения", "*.jpg *.jpeg *.png")]
            )
            if p:
                thumb_path_var.set(p)

        ttk.Button(thumb_frame, text="📁 Обзор", command=choose_thumb, width=8).pack(side="right", padx=(5, 0))

        # Переменные конфигурации для YouTube
        stream_id_var = tk.StringVar()
        latency_var = tk.StringVar(value="ultraLow")
        shorts_var = tk.BooleanVar(value=False)
        streams_list = []

        if self.platform.lower() == "youtube":
            # 1. Выбор ключа потока из нескольких доступных [2.1]
            ttk.Label(create_win, text="Ключ потока (liveStream):").pack(anchor="w", padx=15, pady=(10, 2))
            combo_stream = ttk.Combobox(create_win, textvariable=stream_id_var, state="readonly", width=42)
            combo_stream.pack(fill="x", padx=15, pady=2)
            combo_stream.set("⏳ Загрузка потоков...")

            async def load_streams():
                nonlocal streams_list
                plugin = self.app_core.plugin_manager.get(self.platform)
                if plugin:
                    streams_list = await plugin.get_live_streams()
                    if streams_list:
                        combo_stream['values'] = [f"{s['title']} (Ключ: {s['stream_key'][:8]}...)" for s in
                                                  streams_list]
                        combo_stream.current(0)
                    else:
                        combo_stream.set("Потоки не найдены (создадим новый)")

            asyncio.create_task(load_streams())

            # 2. Выбор задержки (по умолчанию ultraLow)
            ttk.Label(create_win, text="Задержка трансляции:").pack(anchor="w", padx=15, pady=(10, 2))
            latency_combo = ttk.Combobox(create_win, textvariable=latency_var, values=["ultraLow", "low", "normal"],
                                         state="readonly", width=42)
            latency_combo.pack(fill="x", padx=15, pady=2)
            latency_combo.current(0)

            # 3. Чекбокс двойного стрима / Shorts формата
            ttk.Checkbutton(create_win, text="Включить двойной стрим (Шортс формат)", variable=shorts_var).pack(
                anchor="w", padx=15, pady=(12, 2))

        async def do_create():
            t = title_var.get().strip()
            g = game_var.get().strip()
            d = desc_var.get().strip()

            if not t:
                messagebox.showwarning("Внимание", "Название не может быть пустым!", parent=create_win)
                return

            btn_submit.config(state="disabled")
            plugin = self.app_core.plugin_manager.get(self.platform)
            if plugin:
                # Извлекаем ID потока и категорию для YouTube
                selected_stream_id = None
                if self.platform.lower() == "youtube":
                    g = yt_categories.get(g, "20")  # Конвертируем имя категории в ID категории
                    sel_idx = combo_stream.current()
                    if sel_idx >= 0 and sel_idx < len(streams_list):
                        selected_stream_id = streams_list[sel_idx]["id"]

                # Вызываем создание
                if self.platform.lower() == "youtube":
                    res = await plugin.create_stream(
                        title=t,
                        game=g,
                        description=d,
                        stream_id=selected_stream_id,
                        latency=latency_var.get(),
                        is_shorts=shorts_var.get()
                    )
                else:
                    res = await plugin.create_stream(title=t, game=g, description=d)

                if res.get("success"):
                    # Сохраняем новую трансляцию
                    config = self.app_core.config
                    if self.platform.lower() == "youtube":
                        from app.auth.token_store import get_token, set_token
                        tok = get_token("youtube") or {}
                        tok["broadcast_id"] = res["broadcast_id"]
                        set_token("youtube", tok)
                    elif self.platform.lower() == "rutube":
                        platform_cfg = config["platforms"].setdefault("rutube", {})
                        platform_cfg["broadcast_id"] = res["broadcast_id"]
                        self.app_core.update_app_config(config)

                    # Загрузка выбранной обложки, если путь указан [2.1]
                    tp = thumb_path_var.get().strip()
                    if tp:
                        await plugin.upload_thumbnail(tp)

                    msg = f"Трансляция успешно создана!\n\nID: {res['broadcast_id']}"
                    if res.get("perm_key"):
                        msg += f"\n\nКлюч потока (Stream Key):\n{res['perm_key']}"

                    messagebox.showinfo("Успех", msg, parent=parent_dialog)

                    # Закрываем окна БЕЗ вызова config на уничтоженном виджете (исправление TclError) [2.1]
                    create_win.destroy()
                    parent_dialog.destroy()

                    # Мгновенно обновляем интерфейс данными нового стрима
                    try:
                        status = await plugin.get_status()
                        status["platform"] = self.platform
                        self.app_core.event_bus.emit("stream.status_checked", status)
                    except Exception as ex:
                        logger.debug(f"Ошибка обновления статуса: {ex!r}")
                    return
                else:
                    messagebox.showerror("Ошибка", res.get("error", "Неизвестная ошибка"), parent=create_win)

            # Возвращаем активность кнопке, если создание не удалось (с проверкой на существование окна)
            try:
                if create_win.winfo_exists():
                    btn_submit.config(state="normal")
            except Exception:
                pass

        btn_submit = ttk.Button(create_win, text="🚀 Создать трансляцию",
                                command=lambda: asyncio.create_task(do_create()))
        btn_submit.pack(pady=20, fill="x", padx=15)


class OBSDockWindow(tk.Toplevel):
    """Минималистичное открепляемое окно мониторинга статусов, идеально подходящее как OBS-док."""

    def __init__(self, parent, app_core, gui):
        super().__init__(parent)
        self.app_core = app_core
        self.gui = gui
        self.title("Live Monitor")
        self.geometry("260x340")
        self.attributes("-topmost", True)
        self.resizable(True, True)

        from app.utils import theme_manager
        self.colors = theme_manager.get_theme_colors()
        self.configure(bg=self.colors["bg"])

        # Установка иконки для вспомогательного окна
        self._set_window_icon()

        # Заголовок дока
        header = tk.Label(
            self,
            text="📊 СТРИМ-МОНИТОР",
            font=("Segoe UI", 9, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_sec"],
            pady=8
        )
        header.pack(fill="x")

        self.rows_frame = tk.Frame(self, bg=self.colors["bg"])
        self.rows_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.platform_widgets = {}
        self._build_rows()

        # Подписка на обновление данных в реальном времени
        self.app_core.event_bus.subscribe("stream.status_checked", self.on_status_update)
        self.app_core.event_bus.subscribe("plugins.loaded", self.on_plugins_loaded)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _set_window_icon(self):
        """Устанавливает иконку для окна OBS Дока."""
        from app.utils.paths import get_asset_path
        icon_path = get_asset_path("icon.ico")
        if icon_path.exists():
            try:
                if sys.platform == "win32":
                    self.iconbitmap(str(icon_path))
                else:
                    from PIL import ImageTk
                    img = Image.open(icon_path)
                    photo = ImageTk.PhotoImage(img)
                    self.iconphoto(True, photo)
                    self._icon_ref = photo
            except Exception as e:
                logger.debug(f"Ошибка установки иконки OBS Дока: {e}")

    def _build_rows(self):
        # Удаляем старые виджеты перед перерисовкой (например, при смене темы или списка плагинов)
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.platform_widgets.clear()

        from app.utils import theme_manager
        theme_name = theme_manager.get_current_theme_name()
        theme_type = "light" if "Светлая" in theme_name else "dark"

        for name, plugin in self.app_core.plugin_manager.all().items():
            if plugin.enabled:
                brand = BRAND_COLORS[theme_type].get(name.lower(), BRAND_COLORS[theme_type]["twitch"])

                row = tk.Frame(self.rows_frame, bg=self.colors["field_bg"], pady=6, padx=8)
                row.pack(fill="x", pady=2)

                # Вертикальный цветной бренд-индикатор слева от строки
                indicator = tk.Frame(row, bg=brand["accent"], width=4)
                indicator.pack(side="left", fill="y", padx=(0, 8))

                # Метка названия платформы
                lbl_name = tk.Label(
                    row,
                    text=name.upper(),
                    font=("Segoe UI", 8, "bold"),
                    bg=self.colors["field_bg"],
                    fg=self.colors["fg"]
                )
                lbl_name.pack(side="left")

                status_container = tk.Frame(row, bg=self.colors["field_bg"])
                status_container.pack(side="right")

                # Метка лайков
                lbl_likes = tk.Label(
                    status_container,
                    text="",
                    font=("Segoe UI", 8),
                    bg=self.colors["field_bg"],
                    fg=self.colors["text_green"]
                )
                lbl_likes.pack(side="left", padx=2)

                # Метка зрителей
                lbl_viewers = tk.Label(
                    status_container,
                    text="👁 —",
                    font=("Segoe UI", 8),
                    bg=self.colors["field_bg"],
                    fg=self.colors["fg"]
                )
                lbl_viewers.pack(side="left", padx=5)

                # Точечный индикатор статуса
                lbl_status = tk.Label(
                    status_container,
                    text="🔴",
                    font=("Segoe UI", 8),
                    bg=self.colors["field_bg"]
                )
                lbl_status.pack(side="left", padx=(5, 0))

                self.platform_widgets[name] = {
                    "row": row,
                    "lbl_viewers": lbl_viewers,
                    "lbl_likes": lbl_likes,
                    "lbl_status": lbl_status
                }

                # Заполнение стартовыми данными из уже отрисованных карточек (без повторных запросов)
                if name in self.gui.cards:
                    card = self.gui.cards[name]
                    self._update_row_ui(name, card.lbl_status.cget("text"), card.lbl_viewers.cget("text"))

    def _update_row_ui(self, platform, status_text, viewers_text):
        widgets = self.platform_widgets.get(platform)
        if not widgets:
            return

        # Парсинг индикатора жизни
        if "В ЭФИРЕ" in status_text or "🟢" in status_text:
            widgets["lbl_status"].config(text="🟢", fg=self.colors["text_green"])
        elif "ПОДГОТОВКЕ" in status_text or "🟡" in status_text:
            widgets["lbl_status"].config(text="🟡", fg=self.colors["text_sec"])
        else:
            widgets["lbl_status"].config(text="🔴", fg=self.colors["text_red"])

        # Вытаскиваем зрителей и лайки
        if "|" in viewers_text:
            parts = viewers_text.split("|")
            v_val = parts[0].replace("👁 Зрители:", "").strip()
            widgets["lbl_viewers"].config(text=f"👁 {v_val}")
            likes_val = " ".join([p.strip() for p in parts[1:]])
            widgets["lbl_likes"].config(text=likes_val)
        else:
            v_val = viewers_text.replace("👁 Зрители:", "").strip()
            widgets["lbl_viewers"].config(text=f"👁 {v_val}")
            widgets["lbl_likes"].config(text="")

    def on_status_update(self, data):
        platform = data.get("platform")
        if platform in self.platform_widgets:
            is_live = data.get("is_live", False)
            status_text = data.get("custom_status") or ("🟢 В ЭФИРЕ" if is_live else "🔴 ОФФЛАЙН")
            viewers_text = f"👁 Зрители: {data.get('viewers', 0)}"
            if "likes" in data or "dislikes" in data:
                viewers_text += f" | 👍 {data.get('likes', 0)} | 👎 {data.get('dislikes', 0)}"

            self.after(0, self._update_row_ui, platform, status_text, viewers_text)

    def on_plugins_loaded(self, data):
        from app.utils import theme_manager
        self.colors = theme_manager.get_theme_colors()
        self.configure(bg=self.colors["bg"])
        self.after(0, self._build_rows)

    def on_close(self):
        # Отписываемся от событий, чтобы избежать утечек памяти
        self.app_core.event_bus.unsubscribe("stream.status_checked", self.on_status_update)
        self.app_core.event_bus.unsubscribe("plugins.loaded", self.on_plugins_loaded)
        self.destroy()


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
        self.root.geometry("1000x750")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._set_theme()
        self._set_window_icon()  # Установка иконки главного окна
        self._build_ui()
        self._subscribe_events()

        self.tray_icon = None
        self.obs_dock = None

    def _set_theme(self):
        # Применяем сохраненную тему из Theme Manager
        from app.utils import theme_manager
        theme_manager.apply_theme(self.root)

    def _set_window_icon(self):
        """Устанавливает иконку главного окна из assets/icon.ico."""
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
                    # default=True применит иконку ко всем дочерним окнам по умолчанию
                    self.root.iconphoto(True, photo)
                    self._icon_ref = photo  # Защита от Garbage Collector
            except Exception as e:
                logger.debug(f"Ошибка установки иконки главного окна: {e}")

    def _create_tray_image(self):
        """Загружает изображение иконки для системного трея."""
        from app.utils.paths import get_asset_path
        icon_path = get_asset_path("icon.ico")
        try:
            if icon_path.exists():
                return Image.open(icon_path).convert("RGBA")
        except Exception as e:
            logger.debug(f"Не удалось загрузить иконку для трея из {icon_path}: {e}")

        # Резервный вариант, если файла нет
        image = Image.new('RGB', (64, 64), color=(14, 14, 26))
        dc = ImageDraw.Draw(image)
        dc.ellipse((16, 16, 48, 48), fill=(166, 227, 161))
        return image

    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

        # Вкладка 1: Дашборд
        self.tab_dashboard = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_dashboard, text=" 📺  Дашборд ")

        # --- Массовое управление ---
        master_frame = ttk.LabelFrame(self.tab_dashboard, text=" ⚡ Массовое управление ", padding=15)
        master_frame.pack(fill=tk.X, pady=(0, 12))  # Растягиваем фрейм на всю ширину вровень с карточками

        # Поля ввода
        ttk.Label(master_frame, text="Общее название:").grid(row=0, column=0, sticky="w")
        self.master_title = tk.StringVar()
        ttk.Entry(master_frame, textvariable=self.master_title).grid(row=0, column=1, sticky="ew", padx=10, pady=5)

        ttk.Label(master_frame, text="Общая категория:").grid(row=1, column=0, sticky="w")
        self.master_game = tk.StringVar()
        ttk.Combobox(
            master_frame, textvariable=self.master_game, values=self.app_core.game_service.get_favorites()
        ).grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # Кнопка ПРИМЕНИТЬ КО ВСЕМ
        self.btn_apply_all = ttk.Button(master_frame, text="⚡ ПРИМЕНИТЬ КО ВСЕМ", command=self.on_apply_all)
        self.btn_apply_all.grid(row=0, column=2, columnspan=3, sticky="ew", padx=5, pady=5)

        # Кнопка добавления в избранное (Колонка 2)
        ttk.Button(master_frame, text="💾 В избранное", command=self.save_game_to_favorites).grid(row=1, column=2,
                                                                                                 padx=5, pady=5,
                                                                                                 sticky="ew")

        # Кнопка ПОИСКА (Колонка 3)
        ttk.Button(master_frame, text="🔍 Найти игру", command=self.open_search_dialog).grid(row=1, column=3, padx=5,
                                                                                            pady=5, sticky="ew")

        # Кнопка ОБНОВИТЬ СТАТУСЫ (Колонка 4)
        self.btn_refresh_now = ttk.Button(master_frame, text="🔁 Обновить статусы", command=self.on_force_refresh)
        self.btn_refresh_now.grid(row=1, column=4, padx=5, pady=5, sticky="ew")

        # Указываем вес колонке с полями ввода, чтобы она занимала все свободное пространство
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

        # НОВАЯ Вкладка 4: Мультичат
        self.tab_chat = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_chat, text=" 💬  Мультичат ")
        self._build_chat_tab()

        # Вкладка 5: Лог
        self.tab_log = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_log, text=" 📋  Лог событий ")
        self.log_panel = EventLogPanel(self.tab_log)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        # Нижний статус-бар
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=4)

        self.status_label = ttk.Label(status_frame, text=" Готов к работе")
        self.status_label.pack(side=tk.LEFT)

        # Кнопка открытия минималистичного OBS Дока в статус-баре справа
        self.btn_obs_dock = ttk.Button(
            status_frame,
            text="📊 OBS Док",
            command=self.open_obs_dock,
            width=12
        )
        self.btn_obs_dock.pack(side=tk.RIGHT)

        # Применяем кастомные цвета темы к текстовым полям логов и инструкций
        self.apply_theme_to_custom_widgets()

    def _build_chat_tab(self):
        frame = self.tab_chat

        # Область вывода чата
        chat_frame = ttk.Frame(frame)
        chat_frame.pack(fill=tk.BOTH, expand=True)

        self.chat_text = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            state=tk.DISABLED,
            background="#1e1e2e",
            foreground="#cdd6f4",
            insertbackground="#cdd6f4",
            selectbackground="#313244",
            relief=tk.FLAT,
            padx=10,
            pady=10
        )
        scrollbar = ttk.Scrollbar(chat_frame, command=self.chat_text.yview)
        self.chat_text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        # Стилизация элементов чата
        self.chat_text.tag_configure("time", foreground="#6c7086")
        self.chat_text.tag_configure("twitch_name", foreground="#cba6f7", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("youtube_name", foreground="#f28c8c", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("kick_name", foreground="#8cf290", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("other_name", foreground="#89b4fa", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("msg_text", foreground="#cdd6f4")
        self.chat_text.tag_configure("platform_tag", foreground="#f9e2af", font=("Segoe UI", 9, "bold"))
        self.chat_text.tag_configure("system", foreground="#fab387", font=("Segoe UI", 9, "italic"))

        # Клик правой кнопкой мыши для модерации
        self.chat_text.bind("<Button-3>", self.show_chat_context_menu)
        self.chat_text.bind("<Button-2>", self.show_chat_context_menu)

        # ── НИЖНЯЯ ПАНЕЛЬ С ДВУМЯ СТРОКАМИ (ИНДИКАТОР + ВВОД) ──
        bottom_container = ttk.Frame(frame, padding=(0, 10, 0, 0))
        bottom_container.pack(fill=tk.X, side=tk.BOTTOM)

        # Панель индикатора ответа (по умолчанию скрыта)
        self.reply_indicator_frame = ttk.Frame(bottom_container, padding=(5, 2, 5, 2))
        self.reply_label = ttk.Label(self.reply_indicator_frame, text="", font=("Segoe UI", 9, "italic"), foreground="#a6e3a1")
        self.reply_label.pack(side=tk.LEFT)
        ttk.Button(self.reply_indicator_frame, text="✕", command=self.cancel_reply, width=3).pack(side=tk.RIGHT)

        # Панель ввода
        input_frame = ttk.Frame(bottom_container)
        input_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(2, 0))

        # Выбор целевой платформы (лейбл "Отправить в:" удален для экономии места)
        self.chat_target_var = tk.StringVar(value="Все активные")
        self.chat_target_combo = ttk.Combobox(
            input_frame,
            textvariable=self.chat_target_var,
            values=["Все активные", "Twitch", "YouTube", "Kick", "LiveVK", "GoodGame"],
            state="readonly",
            width=15
        )
        self.chat_target_combo.pack(side=tk.LEFT, padx=(0, 5))

        # Чекбокс автозакрепа (сокращен до одной иконки 📌)
        self.chat_pin_var = tk.BooleanVar(value=False)
        self.cb_pin = ttk.Checkbutton(input_frame, text="📌", variable=self.chat_pin_var)
        self.cb_pin.pack(side=tk.LEFT, padx=(0, 5))

        self.chat_input_var = tk.StringVar()
        self.chat_entry = ttk.Entry(input_frame, textvariable=self.chat_input_var)
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.chat_entry.bind("<Return>", lambda e: self.send_chat_message_gui())

        self.btn_send_chat = ttk.Button(input_frame, text="Отправить", command=self.send_chat_message_gui)
        self.btn_send_chat.pack(side=tk.RIGHT)

        # Состояния ответа
        self.reply_parent_id = None
        self.reply_parent_author = None
        self.reply_platform = None

    def start_reply(self, platform, author_name, msg_id):
        """Активирует режим ответа на конкретное сообщение."""
        # Переключаем цель чата на платформу сообщения
        for val in self.chat_target_combo['values']:
            if val.lower() == platform.lower():
                self.chat_target_var.set(val)
                break

        self.reply_parent_id = msg_id
        self.reply_parent_author = author_name
        self.reply_platform = platform

        # Отображаем панель индикатора
        self.reply_label.config(text=f"↳ Отвечаете @{author_name} на сообщение...")
        self.reply_indicator_frame.pack(fill=tk.X, side=tk.TOP, before=self.chat_entry.master, pady=(0, 2))

    def cancel_reply(self):
        """Сбрасывает режим ответа."""
        self.reply_parent_id = None
        self.reply_parent_author = None
        self.reply_platform = None
        self.reply_indicator_frame.pack_forget()

    def send_chat_message_gui(self):
        text = self.chat_input_var.get().strip()
        if not text:
            return

        target = self.chat_target_var.get()
        self.chat_input_var.set("")  # Очищаем поле ввода для удобства

        # Снимаем состояние ответа
        reply_id = self.reply_parent_id
        self.cancel_reply()

        # Возвращаем "Все активные" после отправки ответа на одно сообщение
        if reply_id:
            self.chat_target_var.set("Все активные")

        # Если включен чекбокс "Закрепить", взводим триггер автозакрепа при получении ID от Twitch
        if self.chat_pin_var.get():
            self._pin_next_sent_message = True
            self.chat_pin_var.set(False)

        async def do_send():
            chat_service = self.app_core.chat_service
            if target == "Все активные":
                await chat_service.send_global_message(text)
            else:
                await chat_service.send_message(target.lower(), text, reply_parent_id=reply_id)

        asyncio.create_task(do_send())

    def _on_chat_message_received(self, data: dict):
        if not hasattr(self, "chat_text") or not self.chat_text.winfo_exists():
            return

        platform = data.get("platform", "sys").lower()  # В нижний регистр
        author_name = data.get("author", {}).get("name", "User")
        author_id = data.get("author", {}).get("id", "")
        text = data.get("text", "")
        msg_id = data.get("id", "")

        self.root.after(0, self._append_chat_message_gui, platform, author_name, text, msg_id, author_id)

    def _append_chat_message_gui(self, platform, author, text, msg_id, author_id):
        platform = platform.lower()  # В нижний регистр

        # ЗАЩИТА ОТ ДУБЛИРОВАНИЯ
        if msg_id:
            target_prefix = f"meta|{platform}|{msg_id}|"
            for tag in self.chat_text.tag_names():
                if tag.startswith(target_prefix):
                    return

        self.chat_text.config(state=tk.NORMAL)
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")

        start_index = self.chat_text.index("end-1c")

        self.chat_text.insert(tk.END, f"[{ts}] ", "time")
        self.chat_text.insert(tk.END, f"[{platform.upper()}] ", "platform_tag")

        name_tag = "other_name"
        if platform == "twitch":
            name_tag = "twitch_name"
        elif platform == "youtube":
            name_tag = "youtube_name"
        elif platform == "kick":
            name_tag = "kick_name"

        self.chat_text.insert(tk.END, f"{author}: ", name_tag)
        self.chat_text.insert(tk.END, f"{text}\n", "msg_text")

        end_index = self.chat_text.index("end-1c")

        safe_author = str(author).replace("|", "%7C")
        safe_msg_id = str(msg_id).replace("|", "%7C")
        safe_author_id = str(author_id).replace("|", "%7C")
        meta_tag = f"meta|{platform}|{safe_msg_id}|{safe_author}|{safe_author_id}"

        self.chat_text.tag_add(meta_tag, start_index, end_index)

        line_count = int(self.chat_text.index(tk.END).split(".")[0])
        if line_count > 300:
            self.chat_text.delete("1.0", f"{line_count - 300}.0")

        self.chat_text.see(tk.END)
        self.chat_text.config(state=tk.DISABLED)

    def _on_chat_message_id_updated(self, data: dict):
        if not hasattr(self, "chat_text") or not self.chat_text.winfo_exists():
            return
        platform = data.get("platform", "").lower()  # В нижний регистр
        old_id = data.get("old_id")
        new_id = data.get("new_id")

        self.root.after(0, self._update_message_id_gui, platform, old_id, new_id)

    def _on_chat_user_banned(self, data: dict):
        if not hasattr(self, "chat_text") or not self.chat_text.winfo_exists():
            return
        platform = data.get("platform", "").lower()  # В нижний регистр
        username = data.get("username")

        self.root.after(0, self._ban_chat_user_gui, platform, username)

    def show_chat_context_menu(self, event):
        """Определяет строку сообщения под курсором и открывает меню действий/модерации."""
        click_index = self.chat_text.index(f"@{event.x},{event.y}")
        tags = self.chat_text.tag_names(click_index)

        meta_tag = None
        for tag in tags:
            if tag.startswith("meta|"):
                meta_tag = tag
                break

        if not meta_tag:
            return

        parts = meta_tag.split("|")
        if len(parts) < 5:
            return

        _, platform, msg_id, author_name, author_id = parts
        platform = platform.strip()
        msg_id = msg_id.replace("%7C", "|").strip()
        author_name = author_name.replace("%7C", "|").strip()
        author_id = author_id.replace("%7C", "|").strip()

        if platform == "sys" or not msg_id:
            return

        # Извлекаем чистый текст самого сообщения для копирования
        ranges = self.chat_text.tag_ranges(meta_tag)
        text_content = ""
        if ranges:
            whole_line = self.chat_text.get(ranges[0], ranges[1])
            if ": " in whole_line:
                text_content = whole_line.split(": ", 1)[1].strip()
            else:
                text_content = whole_line.strip()

        menu = tk.Menu(self.root, tearoff=0)

        # Свои сообщения не тегаем кнопкой ответить в текстовом виде (но даем реальный thread-reply)
        is_self = author_name.lower() in ("вы", "broadcaster")
        twitch_plugin = self.app_core.plugin_manager.get("twitch")
        if twitch_plugin and twitch_plugin.enabled:
            broadcaster_login = twitch_plugin.token_data.get("broadcaster_login", "")
            if broadcaster_login and author_name.lower() == broadcaster_login.lower():
                is_self = True

        if is_self:
            menu.add_command(
                label="📋 Копировать никнейм",
                command=lambda: self.root.clipboard_clear() or self.root.clipboard_append(author_name)
            )
        else:
            menu.add_command(
                label=f"💬 Ответить @{author_name} (в тред)",
                command=lambda: self.start_reply(platform, author_name, msg_id)
            )
            menu.add_separator()
            menu.add_command(
                label="📋 Копировать никнейм",
                command=lambda: self.root.clipboard_clear() or self.root.clipboard_append(author_name)
            )

        if text_content:
            menu.add_command(
                label="📝 Копировать текст сообщения",
                command=lambda: self.root.clipboard_clear() or self.root.clipboard_append(text_content)
            )

        # Сообщение можно удалить или закрепить, если оно имеет реальный Twitch ID
        can_moderate_msg = not msg_id.startswith("echo_")

        if can_moderate_msg:
            menu.add_separator()
            menu.add_command(
                label="🗑 Удалить сообщение",
                command=lambda: asyncio.create_task(self._moderate_delete(platform, msg_id))
            )
            # РАЗРЕШАЕМ ЗАКРЕПЛЯТЬ ЛЮБЫЕ РЕАЛЬНЫЕ СООБЩЕНИЯ (И свои, и чужие!)
            menu.add_command(
                label="📌 Закрепить сообщение",
                command=lambda: asyncio.create_task(self._moderate_pin(platform, msg_id))
            )

        # Опции таймаута и бана показываем только для ДРУГИХ пользователей
        if not is_self and not msg_id.startswith("echo_"):
            menu.add_command(
                label=f"⏳ Таймаут {author_name} (10 мин)",
                command=lambda: asyncio.create_task(self._moderate_timeout(platform, author_name, author_id, 600))
            )
            menu.add_command(
                label=f"🚫 Забанить {author_name}",
                command=lambda: asyncio.create_task(self._moderate_ban(platform, author_name, author_id))
            )

        menu.post(event.x_root, event.y_root)

    # Метод обработки обновления ID в GUI
    def _on_chat_message_id_updated(self, data: dict):
        if not hasattr(self, "chat_text") or not self.chat_text.winfo_exists():
            return
        platform = data.get("platform", "").lower()
        old_id = data.get("old_id")
        new_id = data.get("new_id")

        self.root.after(0, self._update_message_id_gui, platform, old_id, new_id)

        # Если пользователем было запланировано автоматическое закрепление отправляемого сообщения
        if getattr(self, "_pin_next_sent_message", False):
            self._pin_next_sent_message = False
            asyncio.create_task(self.app_core.chat_service.pin_message(platform, new_id))
            self._append_chat_message_gui("sys", "Система", "Сообщение успешно отправлено и закреплено на Twitch!",
                                          "", "")

    # Вспомогательный метод закрепа сообщения через ПКМ
    async def _moderate_pin(self, platform, msg_id):
        res = await self.app_core.chat_service.pin_message(platform, msg_id)
        if res:
            self._append_chat_message_gui("sys", "Система", f"Сообщение успешно закреплено на Twitch.", "", "")
        else:
            self._append_chat_message_gui("sys", "Система", f"Не удалось закрепить сообщение.", "", "")

    def _update_message_id_gui(self, platform, old_id, new_id):
        self.chat_text.config(state=tk.NORMAL)
        old_prefix = f"meta|{platform}|{old_id}|"

        for tag in self.chat_text.tag_names():
            if tag.startswith(old_prefix):
                parts = tag.split("|")
                author = parts[3]
                author_id = parts[4]

                # Создаем новый мета-тег с настоящим Twitch ID сообщения
                safe_author = author.replace("|", "%7C")
                safe_new_id = str(new_id).replace("|", "%7C")
                safe_author_id = author_id.replace("|", "%7C")
                new_tag = f"meta|{platform}|{safe_new_id}|{safe_author}|{safe_author_id}"

                ranges = self.chat_text.tag_ranges(tag)
                if ranges:
                    start, end = ranges[0], ranges[1]
                    self.chat_text.tag_delete(tag)  # Удаляем старый мета-тег
                    self.chat_text.tag_add(new_tag, start, end)  # Вешаем новый
                break
        self.chat_text.config(state=tk.DISABLED)

    def _on_chat_user_banned(self, data: dict):
        if not hasattr(self, "chat_text") or not self.chat_text.winfo_exists():
            return
        platform = data.get("platform")
        username = data.get("username")

        self.root.after(0, self._ban_chat_user_gui, platform, username)

    def _ban_chat_user_gui(self, platform, username):
        self.chat_text.config(state=tk.NORMAL)
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")

        target_prefix = f"meta|{platform}|"
        for tag in self.chat_text.tag_names():
            if tag.startswith(target_prefix):
                parts = tag.split("|")
                author = parts[3].replace("%7C", "|")

                # Если автором сообщения является забаненный юзер
                if author.lower() == username.lower():
                    ranges = self.chat_text.tag_ranges(tag)
                    if ranges:
                        start, end = ranges[0], ranges[1]
                        self.chat_text.delete(start, end)
                        self.chat_text.insert(start,
                                              f"[{ts}] [{platform.upper()}] {author}: <сообщение удалено модератором>\n",
                                              "system")

        self.chat_text.config(state=tk.DISABLED)

    # Вспомогательные методы отправки модераторских запросов

    async def _moderate_delete(self, platform, msg_id):
        res = await self.app_core.chat_service.delete_message(platform, msg_id)
        if not res:
            self._append_chat_message_gui("sys", "Система", f"Не удалось отправить запрос удаления на {platform}.", "", "")

    async def _moderate_timeout(self, platform, username, author_id, duration):
        res = await self.app_core.chat_service.ban_user(platform, author_id, reason="Нарушение правил", duration=duration)
        if res:
            self._append_chat_message_gui("sys", "Система", f"Пользователю {username} выдан таймаут на {duration} сек.", "", "")
        else:
            self._append_chat_message_gui("sys", "Система", f"Не удалось выдать таймаут на {platform}.", "", "")

    async def _moderate_ban(self, platform, username, author_id):
        if messagebox.askyesno("Подтверждение бана", f"Вы уверены, что хотите навсегда забанить {username} на {platform.upper()}?"):
            res = await self.app_core.chat_service.ban_user(platform, author_id, reason="Нарушение правил")
            if res:
                self._append_chat_message_gui("sys", "Система", f"Пользователь {username} навсегда заблокирован на {platform}.", "", "")
            else:
                self._append_chat_message_gui("sys", "Система", f"Не удалось забанить пользователя на {platform}.", "", "")

    def _on_chat_message_deleted(self, data: dict):
        if not hasattr(self, "chat_text") or not self.chat_text.winfo_exists():
            return
        platform = data.get("platform")
        msg_id = data.get("msg_id")

        self.root.after(0, self._delete_chat_message_gui, platform, msg_id)

    def _delete_chat_message_gui(self, platform, msg_id):
        self.chat_text.config(state=tk.NORMAL)
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")

        target_prefix = f"meta|{platform}|{msg_id}|"
        for tag in self.chat_text.tag_names():
            if tag.startswith(target_prefix):
                parts = tag.split("|")
                author = parts[3].replace("%7C", "|")

                ranges = self.chat_text.tag_ranges(tag)
                if ranges:
                    start, end = ranges[0], ranges[1]
                    self.chat_text.delete(start, end)
                    self.chat_text.insert(start,
                                          f"[{ts}] [{platform.upper()}] {author}: <сообщение удалено модератором>\n",
                                          "system")
                break
        self.chat_text.config(state=tk.DISABLED)

    def apply_theme_to_custom_widgets(self):
        """Обновляет цвета кастомных виджетов (Text, Canvas) при смене темы."""
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
        """Запускает или выводит на передний план компактное окно мониторинга."""
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
            self.log_panel.append("Платформы не загружены", "warn")
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

                self.log_panel.append(f"Категория '{new_game}' сохранена в избранное.", "info")
            else:
                self.log_panel.append(f"Категория '{new_game}' уже есть в списке.", "info")

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

    def on_force_refresh(self):
        """Обработчик нажатия на кнопку ручного обновления."""
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
