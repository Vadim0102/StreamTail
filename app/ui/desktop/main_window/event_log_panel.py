import tkinter as tk
from tkinter import ttk
from datetime import datetime


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
