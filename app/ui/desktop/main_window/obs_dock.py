import tkinter as tk
import sys
from PIL import Image

from app.utils.logger import logger
from app.ui.desktop.main_window.theme import BRAND_COLORS


class OBSDockWindow(tk.Toplevel):
    """Минималистичное открепляемое окно мониторинга статусов (OBS-док)."""

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

        self._set_window_icon()

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

        self.app_core.event_bus.subscribe("stream.status_checked", self.on_status_update)
        self.app_core.event_bus.subscribe("plugins.loaded", self.on_plugins_loaded)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _set_window_icon(self):
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

                indicator = tk.Frame(row, bg=brand["accent"], width=4)
                indicator.pack(side="left", fill="y", padx=(0, 8))

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

                lbl_likes = tk.Label(
                    status_container,
                    text="",
                    font=("Segoe UI", 8),
                    bg=self.colors["field_bg"],
                    fg=self.colors["text_green"]
                )
                lbl_likes.pack(side="left", padx=2)

                lbl_viewers = tk.Label(
                    status_container,
                    text="👁 —",
                    font=("Segoe UI", 8),
                    bg=self.colors["field_bg"],
                    fg=self.colors["fg"]
                )
                lbl_viewers.pack(side="left", padx=5)

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

                if name in self.gui.cards:
                    card = self.gui.cards[name]
                    self._update_row_ui(name, card.lbl_status.cget("text"), card.lbl_viewers.cget("text"))

    def _update_row_ui(self, platform, status_text, viewers_text):
        widgets = self.platform_widgets.get(platform)
        if not widgets:
            return

        if "В ЭФИРЕ" in status_text or "🟢" in status_text:
            widgets["lbl_status"].config(text="🟢", fg=self.colors["text_green"])
        elif "ПОДГОТОВКЕ" in status_text or "🟡" in status_text:
            widgets["lbl_status"].config(text="🟡", fg=self.colors["text_sec"])
        else:
            widgets["lbl_status"].config(text="🔴", fg=self.colors["text_red"])

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
        self.app_core.event_bus.unsubscribe("stream.status_checked", self.on_status_update)
        self.app_core.event_bus.unsubscribe("plugins.loaded", self.on_plugins_loaded)
        self.destroy()
