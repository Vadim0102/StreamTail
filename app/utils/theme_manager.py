import sv_ttk
from tkinter import ttk
from app.utils import db

# Две основные, пиксельно-выверенные темы оформления с поддержкой контрастных текстов
THEMES = {
    "Темная (Catppuccin)": {
        "sv_theme": "dark",
        "bg": "#1c1c1c",
        "fg": "#f9f9f9",
        "field_bg": "#2d2d2d",
        "select_bg": "#414141",
        "text_sec": "#89b4fa",
        "text_green": "#a6e3a1",  # Мягкий зеленый для темного фона
        "text_red": "#f38ba8",  # Мягкий красный для темного фона
        "text_blue": "#89b4fa"  # Мягкий синий для темного фона
    },
    "Светлая (Sun Valley)": {
        "sv_theme": "light",
        "bg": "#fafafa",
        "fg": "#1c1c1c",
        "field_bg": "#ffffff",
        "select_bg": "#e5e5e5",
        "text_sec": "#005fb8",
        "text_green": "#1a7f37",  # Глубокий лесной зеленый (высокий контраст на белом)
        "text_red": "#cf222e",  # Насыщенный темно-красный (высокий контраст на белом)
        "text_blue": "#0969da"  # Темно-синий королевский (высокий контраст на белом)
    }
}


def get_current_theme_name() -> str:
    return db.get_setting("theme_name", "Темная (Catppuccin)")


def get_theme_colors() -> dict:
    name = get_current_theme_name()
    return THEMES.get(name, THEMES["Темная (Catppuccin)"])


def apply_theme(root) -> dict:
    colors = get_theme_colors()

    try:
        sv_ttk.set_theme(colors["sv_theme"])
    except Exception:
        pass

    root.configure(background=colors["bg"])

    style = ttk.Style()
    style.configure("TFrame", background=colors["bg"])
    style.configure("TLabel", background=colors["bg"], foreground=colors["fg"])
    style.configure("TLabelframe", background=colors["bg"], foreground=colors["fg"])
    style.configure("TLabelframe.Label", background=colors["bg"], foreground=colors["fg"])
    style.configure("TNotebook", background=colors["bg"])
    style.configure("TNotebook.Tab", foreground=colors["fg"])

    return colors
