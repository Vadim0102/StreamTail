import tkinter as tk
from tkinter import ttk, messagebox
import asyncio

from app.auth import twitch_auth, youtube_auth, vk_auth
from app.auth.token_store import is_token_valid
from app.utils.logger import logger


class AuthTab(ttk.Frame):
    def __init__(self, parent, app_core, *args, **kwargs):
        super().__init__(parent, padding=15, *args, **kwargs)
        self.app_core = app_core
        self._build_ui()
        self.update_statuses()

    def _build_ui(self):
        ttk.Label(self, text="🔑 Управление аккаунтами (OAuth2)", font=("Segoe UI", 14, "bold")).pack(anchor="w",
                                                                                                     pady=(0, 15))

        self.platforms = {
            "Twitch": {"id": "twitch", "module": twitch_auth},
            "YouTube": {"id": "youtube", "module": youtube_auth},
            "VK Live": {"id": "livevk", "module": vk_auth},
        }

        self.status_labels = {}

        for name, data in self.platforms.items():
            frame = ttk.LabelFrame(self, text=f" {name} ", padding=10)
            frame.pack(fill="x", pady=5)

            status_lbl = ttk.Label(frame, text="Статус: Неизвестно", font=("Segoe UI", 10))
            status_lbl.pack(side="left")
            self.status_labels[data["id"]] = status_lbl

            btn = ttk.Button(frame, text="Авторизоваться", command=lambda n=name, d=data: self.do_auth(n, d))
            btn.pack(side="right")

        ttk.Label(self, text="* Kick использует Bearer-токен, настраивается вручную в config/app.yaml",
                  font=("Segoe UI", 9, "italic"), foreground="#89b4fa").pack(anchor="w", pady=15)

    def update_statuses(self):
        for name, data in self.platforms.items():
            pid = data["id"]
            if is_token_valid(pid):
                self.status_labels[pid].config(text="✅ Авторизован (токен действителен)", foreground="#a6e3a1")
            else:
                self.status_labels[pid].config(text="❌ Не авторизован / Токен истек", foreground="#f38ba8")

    def do_auth(self, name, data):
        client_id = self.app_core.config["platforms"].get(data["id"], {}).get("client_id")
        client_secret = self.app_core.config["platforms"].get(data["id"], {}).get("client_secret", "")

        # client_id нужен ВООБЩЕ для всех (Twitch, YouTube, VK)
        if not client_id:
            messagebox.showwarning("Внимание", f"Укажите client_id для {name} в config/app.yaml!")
            return

        # client_secret обязательно нужен для обмена кода
        if not client_secret and data["id"] in ("twitch", "youtube", "livevk"):
            messagebox.showwarning("Внимание", f"Укажите client_secret для {name} в config/app.yaml!")
            return

        asyncio.create_task(self._run_auth_flow(name, data, client_id, client_secret))

    async def _run_auth_flow(self, name, data, client_id, client_secret):
        logger.info(f"Запуск авторизации для {name}...")
        self.status_labels[data["id"]].config(text="⏳ Ожидание браузера...", foreground="#fab387")

        success = await data["module"].authenticate(client_id, client_secret)

        if success:
            messagebox.showinfo("Успех", f"Авторизация {name} прошла успешно!")
            self.app_core.event_bus.emit("plugins.loaded", {})  # Перерисовываем дашборд
        else:
            messagebox.showerror("Ошибка", f"Не удалось авторизовать {name}. Проверьте логи.")

        self.update_statuses()
