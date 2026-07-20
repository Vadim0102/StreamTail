import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import datetime
from app.utils.logger import logger
from app.ui.desktop.main_window.theme import BRAND_COLORS


class PlatformCard(tk.LabelFrame):
    def __init__(self, parent, platform: str, app_core, *args, **kwargs):
        self.platform = platform
        self.app_core = app_core

        from app.utils import theme_manager
        theme_name = theme_manager.get_current_theme_name()
        theme_type = "light" if "Светлая" in theme_name else "dark"
        colors = theme_manager.get_theme_colors()

        self.brand = BRAND_COLORS[theme_type].get(platform.lower(), BRAND_COLORS[theme_type]["twitch"])

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

        self.apply_frame = tk.Frame(self, bg=self.brand["bg"])
        self.apply_frame.grid(row=4, column=0, columnspan=2, pady=(15, 0), sticky="ew")

        self.btn_publish = ttk.Button(
            self.apply_frame, text="📢 Опубликовать", command=self.on_publish
        )
        self.btn_stop = ttk.Button(
            self.apply_frame, text="🛑 Завершить", command=self.on_stop
        )

        if self.platform.lower() in ("youtube", "rutube"):
            self.btn_arrow = ttk.Button(
                self.apply_frame, text="▼", command=self.on_select_broadcast, width=4
            )
            self.btn_arrow.grid(row=0, column=0, sticky="w", padx=(0, 5))

            self.btn_apply = ttk.Button(
                self.apply_frame, text="Обновить платформу", command=self.on_apply
            )
            self.btn_apply.grid(row=0, column=1, sticky="ew")

            self.apply_frame.columnconfigure(0, weight=0)
            self.apply_frame.columnconfigure(1, weight=1)
        else:
            self.btn_apply = ttk.Button(
                self.apply_frame, text="Обновить платформу", command=self.on_apply
            )
            self.btn_apply.grid(row=0, column=0, columnspan=2, sticky="ew")
            self.apply_frame.columnconfigure(0, weight=1)

        self.columnconfigure(1, weight=1)

    def update_data(self, data: dict):
        is_live = data.get("is_live", False)

        status_text = data.get("custom_status")
        if not status_text:
            status_text = "🟢 В ЭФИРЕ" if is_live else "🔴 ОФФЛАЙН"

        from app.utils import theme_manager
        colors = theme_manager.get_theme_colors()

        if "В ЭФИРЕ" in status_text or "🟢" in status_text:
            color = colors["text_green"]
        elif "ПОДГОТОВКЕ" in status_text or "🟡" in status_text:
            color = colors["text_sec"]
        else:
            color = colors["text_red"]

        self.lbl_status.config(text=status_text, foreground=color)

        # Вывод просмотров + Лайков и Дизлайков (👍 / 👎) только при активном эфире
        if is_live:
            viewers_text = f"👁 Зрители: {data.get('viewers', 0)}"
            if "likes" in data or "dislikes" in data:
                likes = data.get("likes", 0)
                dislikes = data.get("dislikes", 0)
                viewers_text += f"  |  👍 {likes}  |  👎 {dislikes}"
        else:
            viewers_text = "👁 Зрители: —"

        self.lbl_viewers.config(text=viewers_text)

        if self.platform.lower() in ("youtube", "rutube", "livevk"):
            needs_publish = data.get("needs_publish", False)
            can_stop = data.get("can_stop", False)

            self.btn_publish.grid_forget()
            self.btn_stop.grid_forget()

            start_col = 1 if self.platform.lower() in ("youtube", "rutube") else 0
            col_index = start_col

            if needs_publish:
                self.btn_publish.grid(row=0, column=col_index, sticky="ew", padx=(0, 5))
                col_index += 1
            elif can_stop:
                self.btn_stop.grid(row=0, column=col_index, sticky="ew", padx=(0, 5))
                col_index += 1

            self.btn_apply.grid(row=0, column=col_index, sticky="ew")

            if start_col == 1:
                self.apply_frame.columnconfigure(0, weight=0)
            for i in range(start_col, col_index):
                self.apply_frame.columnconfigure(i, weight=0)
            self.apply_frame.columnconfigure(col_index, weight=1)

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
        self.btn_publish.config(state="disabled")
        asyncio.create_task(self._publish_async())

    async def _publish_async(self):
        try:
            res = await self.app_core.stream_service.publish_stream(self.platform)
            messagebox.showinfo(f"{self.platform} — Публикация", res)

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
        if messagebox.askyesno("Подтверждение", f"Вы уверены, что хотите завершить трансляцию на {self.platform}?"):
            self.btn_stop.config(state="disabled")
            asyncio.create_task(self._stop_async())

    async def _stop_async(self):
        try:
            res = await self.app_core.stream_service.stop_stream(self.platform)
            messagebox.showinfo(f"{self.platform} — Завершение", res)

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
        dialog = tk.Toplevel(self)
        dialog.title(f"Выбор трансляции — {self.platform.upper()}")
        dialog.geometry("520x420")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        lbl_loading = ttk.Label(dialog, text="⏳ Загрузка списка трансляций, пожалуйста подождите...",
                                font=("Segoe UI", 10))
        lbl_loading.pack(pady=10)

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

        if self.platform.lower() in ("rutube", "youtube"):
            btn_create = ttk.Button(btn_frame, text="➕ Создать стрим",
                                    command=lambda: self.on_create_stream_dialog(dialog))
            btn_create.pack(side="right", fill="x", expand=True, padx=(5, 0))

    def on_create_stream_dialog(self, parent_dialog):
        create_win = tk.Toplevel(parent_dialog)
        create_win.title(f"Создание трансляции на {self.platform.upper()}")
        create_win.geometry("450x550")
        create_win.transient(parent_dialog)
        create_win.grab_set()

        ttk.Label(create_win, text="Название нового стрима:").pack(anchor="w", padx=15, pady=(15, 2))
        title_var = tk.StringVar(value=self.title_var.get())
        ttk.Entry(create_win, textvariable=title_var, width=45).pack(fill="x", padx=15, pady=2)

        ttk.Label(create_win, text="Категория/Игра:").pack(anchor="w", padx=15, pady=(10, 2))
        game_var = tk.StringVar()

        if self.platform.lower() == "youtube":
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

        stream_id_var = tk.StringVar()
        latency_var = tk.StringVar(value="ultraLow")
        shorts_var = tk.BooleanVar(value=False)
        streams_list = []

        if self.platform.lower() == "youtube":
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

            ttk.Label(create_win, text="Задержка трансляции:").pack(anchor="w", padx=15, pady=(10, 2))
            latency_combo = ttk.Combobox(create_win, textvariable=latency_var, values=["ultraLow", "low", "normal"],
                                         state="readonly", width=42)
            latency_combo.pack(fill="x", padx=15, pady=2)
            latency_combo.current(0)

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
                selected_stream_id = None
                if self.platform.lower() == "youtube":
                    g = yt_categories.get(g, "20")
                    sel_idx = combo_stream.current()
                    if sel_idx >= 0 and sel_idx < len(streams_list):
                        selected_stream_id = streams_list[sel_idx]["id"]

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

                    tp = thumb_path_var.get().strip()
                    if tp:
                        await plugin.upload_thumbnail(tp)

                    msg = f"Трансляция успешно создана!\n\nID: {res['broadcast_id']}"
                    if res.get("perm_key"):
                        msg += f"\n\nКлюч потока (Stream Key):\n{res['perm_key']}"

                    messagebox.showinfo("Успех", msg, parent=parent_dialog)

                    create_win.destroy()
                    parent_dialog.destroy()

                    try:
                        status = await plugin.get_status()
                        status["platform"] = self.platform
                        self.app_core.event_bus.emit("stream.status_checked", status)
                    except Exception as ex:
                        logger.debug(f"Ошибка обновления статуса: {ex!r}")
                    return
                else:
                    messagebox.showerror("Ошибка", res.get("error", "Неизвестная ошибка"), parent=create_win)

            try:
                if create_win.winfo_exists():
                    btn_submit.config(state="normal")
            except Exception:
                pass

        btn_submit = ttk.Button(create_win, text="🚀 Создать трансляцию",
                                command=lambda: asyncio.create_task(do_create()))
        btn_submit.pack(pady=20, fill="x", padx=15)
