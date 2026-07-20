import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import asyncio

from app.utils.logger import logger


class ChatPanelMixin:
    """Примесь логики вкладки Мультичата для основного GUI."""

    def _build_chat_tab(self):
        frame = self.tab_chat

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

        self.chat_text.tag_configure("time", foreground="#6c7086")
        self.chat_text.tag_configure("twitch_name", foreground="#cba6f7", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("youtube_name", foreground="#f28c8c", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("kick_name", foreground="#8cf290", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("other_name", foreground="#89b4fa", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("msg_text", foreground="#cdd6f4")
        self.chat_text.tag_configure("platform_tag", foreground="#f9e2af", font=("Segoe UI", 9, "bold"))
        self.chat_text.tag_configure("system", foreground="#fab387", font=("Segoe UI", 9, "italic"))

        self.chat_text.bind("<Button-3>", self.show_chat_context_menu)
        self.chat_text.bind("<Button-2>", self.show_chat_context_menu)

        bottom_container = ttk.Frame(frame, padding=(0, 10, 0, 0))
        bottom_container.pack(fill=tk.X, side=tk.BOTTOM)

        self.reply_indicator_frame = ttk.Frame(bottom_container, padding=(5, 2, 5, 2))
        self.reply_label = ttk.Label(self.reply_indicator_frame, text="", font=("Segoe UI", 9, "italic"), foreground="#a6e3a1")
        self.reply_label.pack(side=tk.LEFT)
        ttk.Button(self.reply_indicator_frame, text="✕", command=self.cancel_reply, width=3).pack(side=tk.RIGHT)

        input_frame = ttk.Frame(bottom_container)
        input_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(2, 0))

        self.chat_target_var = tk.StringVar(value="Все активные")
        self.chat_target_combo = ttk.Combobox(
            input_frame,
            textvariable=self.chat_target_var,
            values=["Все активные", "Twitch", "YouTube", "Kick", "LiveVK", "GoodGame"],
            state="readonly",
            width=15
        )
        self.chat_target_combo.pack(side=tk.LEFT, padx=(0, 5))

        self.chat_pin_var = tk.BooleanVar(value=False)
        self.cb_pin = ttk.Checkbutton(input_frame, text="📌", variable=self.chat_pin_var)
        self.cb_pin.pack(side=tk.LEFT, padx=(0, 5))

        self.chat_input_var = tk.StringVar()
        self.chat_entry = ttk.Entry(input_frame, textvariable=self.chat_input_var)
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.chat_entry.bind("<Return>", lambda e: self.send_chat_message_gui())

        self.btn_send_chat = ttk.Button(input_frame, text="Отправить", command=self.send_chat_message_gui)
        self.btn_send_chat.pack(side=tk.RIGHT)

        self.reply_parent_id = None
        self.reply_parent_author = None
        self.reply_platform = None

    def start_reply(self, platform, author_name, msg_id):
        for val in self.chat_target_combo['values']:
            if val.lower() == platform.lower():
                self.chat_target_var.set(val)
                break

        self.reply_parent_id = msg_id
        self.reply_parent_author = author_name
        self.reply_platform = platform

        self.reply_label.config(text=f"↳ Отвечаете @{author_name} на сообщение...")
        self.reply_indicator_frame.pack(fill=tk.X, side=tk.TOP, before=self.chat_entry.master, pady=(0, 2))

    def cancel_reply(self):
        self.reply_parent_id = None
        self.reply_parent_author = None
        self.reply_platform = None
        self.reply_indicator_frame.pack_forget()

    def send_chat_message_gui(self):
        text = self.chat_input_var.get().strip()
        if not text:
            return

        target = self.chat_target_var.get()
        self.chat_input_var.set("")

        reply_id = self.reply_parent_id
        self.cancel_reply()

        if reply_id:
            self.chat_target_var.set("Все активные")

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

        platform = data.get("platform", "sys").lower()
        author_name = data.get("author", {}).get("name", "User")
        author_id = data.get("author", {}).get("id", "")
        text = data.get("text", "")
        msg_id = data.get("id", "")

        self.root.after(0, self._append_chat_message_gui, platform, author_name, text, msg_id, author_id)

    def _append_chat_message_gui(self, platform, author, text, msg_id, author_id):
        platform = platform.lower()

        if msg_id:
            target_prefix = f"meta|{platform}|{msg_id}|"
            for tag in self.chat_text.tag_names():
                if tag.startswith(target_prefix):
                    return

        self.chat_text.config(state=tk.NORMAL)
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
        platform = data.get("platform", "").lower()
        old_id = data.get("old_id")
        new_id = data.get("new_id")

        self.root.after(0, self._update_message_id_gui, platform, old_id, new_id)

        if getattr(self, "_pin_next_sent_message", False):
            self._pin_next_sent_message = False
            asyncio.create_task(self.app_core.chat_service.pin_message(platform, new_id))
            self._append_chat_message_gui("sys", "Система", "Сообщение успешно отправлено и закреплено на Twitch!", "", "")

    def _update_message_id_gui(self, platform, old_id, new_id):
        self.chat_text.config(state=tk.NORMAL)
        old_prefix = f"meta|{platform}|{old_id}|"

        for tag in self.chat_text.tag_names():
            if tag.startswith(old_prefix):
                parts = tag.split("|")
                author = parts[3]
                author_id = parts[4]

                safe_author = author.replace("|", "%7C")
                safe_new_id = str(new_id).replace("|", "%7C")
                safe_author_id = author_id.replace("|", "%7C")
                new_tag = f"meta|{platform}|{safe_new_id}|{safe_author}|{safe_author_id}"

                ranges = self.chat_text.tag_ranges(tag)
                if ranges:
                    start, end = ranges[0], ranges[1]
                    self.chat_text.tag_delete(tag)
                    self.chat_text.tag_add(new_tag, start, end)
                break
        self.chat_text.config(state=tk.DISABLED)

    def _on_chat_user_banned(self, data: dict):
        if not hasattr(self, "chat_text") or not self.chat_text.winfo_exists():
            return
        platform = data.get("platform", "").lower()
        username = data.get("username")

        self.root.after(0, self._ban_chat_user_gui, platform, username)

    def _ban_chat_user_gui(self, platform, username):
        self.chat_text.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")

        target_prefix = f"meta|{platform}|"
        for tag in self.chat_text.tag_names():
            if tag.startswith(target_prefix):
                parts = tag.split("|")
                author = parts[3].replace("%7C", "|")

                if author.lower() == username.lower():
                    ranges = self.chat_text.tag_ranges(tag)
                    if ranges:
                        start, end = ranges[0], ranges[1]
                        self.chat_text.delete(start, end)
                        self.chat_text.insert(start,
                                              f"[{ts}] [{platform.upper()}] {author}: <сообщение удалено модератором>\n",
                                              "system")

        self.chat_text.config(state=tk.DISABLED)

    def show_chat_context_menu(self, event):
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

        ranges = self.chat_text.tag_ranges(meta_tag)
        text_content = ""
        if ranges:
            whole_line = self.chat_text.get(ranges[0], ranges[1])
            if ": " in whole_line:
                text_content = whole_line.split(": ", 1)[1].strip()
            else:
                text_content = whole_line.strip()

        menu = tk.Menu(self.root, tearoff=0)

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

        can_moderate_msg = not msg_id.startswith("echo_")

        if can_moderate_msg:
            menu.add_separator()
            menu.add_command(
                label="🗑 Удалить сообщение",
                command=lambda: asyncio.create_task(self._moderate_delete(platform, msg_id))
            )
            menu.add_command(
                label="📌 Закрепить сообщение",
                command=lambda: asyncio.create_task(self._moderate_pin(platform, msg_id))
            )

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

    async def _moderate_pin(self, platform, msg_id):
        res = await self.app_core.chat_service.pin_message(platform, msg_id)
        if res:
            self._append_chat_message_gui("sys", "Система", "Сообщение успешно закреплено на Twitch.", "", "")
        else:
            self._append_chat_message_gui("sys", "Система", "Не удалось закрепить сообщение.", "", "")

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
