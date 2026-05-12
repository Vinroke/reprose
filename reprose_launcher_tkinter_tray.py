#!/usr/bin/env python3
"""
Reprose simple launcher — stdlib only.

Purpose:
- Start a local HTTP server for the folder containing Reprose HTML.
- Open Reprose in the default browser.
- Check whether Ollama is reachable and list models when possible.
- Avoid third-party GUI dependencies. Uses Tkinter from the Python standard library.

Run:
  python3 reprose_launcher_tkinter.py

Optional:
  python3 reprose_launcher_tkinter.py /path/to/reprose.html
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from urllib.error import URLError, HTTPError
from urllib.request import urlopen
import webbrowser

APP_NAME = "Reprose Launcher"
DEFAULT_PORT = 8787
OLLAMA_URL = "http://localhost:11434"
TRAY_PACKAGES = ("pystray", "pillow")
TRAY_PROMPT_SENTINEL = ".reprose_tray_prompt_seen"
HTML_PATTERNS = (
    "reprose-1_0*.html",
    "reprose-0_9b*.html",
    "reprose*.html",
    "*.html",
)
# ─────────────────────────────────────────────────────────────
# Reprose launcher self-venv bootstrap
# Creates and relaunches inside ./venv automatically
# ─────────────────────────────────────────────────────────────

import os
import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
VENV_DIR = ROOT_DIR / "venv"

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
    VENV_PIP = VENV_DIR / "Scripts" / "pip.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"
    VENV_PIP = VENV_DIR / "bin" / "pip"


def running_inside_venv():
    return (
        hasattr(sys, 'real_prefix')
        or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )


def create_venv():
    print("Creating Reprose virtual environment...")
    subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])


def install_requirements():
    requirements = ROOT_DIR / "requirements.txt"

    print("Installing launcher dependencies...")

    subprocess.check_call([
        str(VENV_PIP),
        "install",
        "--upgrade",
        "pip"
    ])

    if requirements.exists():
        subprocess.check_call([
            str(VENV_PIP),
            "install",
            "-r",
            str(requirements)
        ])
    else:
        # fallback minimal deps
        subprocess.check_call([
            str(VENV_PIP),
            "install",
            "requests"
        ])


def relaunch_inside_venv():
    print("Restarting launcher inside virtual environment...")
    os.execv(
        str(VENV_PYTHON),
        [str(VENV_PYTHON)] + sys.argv
    )


if not running_inside_venv():

    if not VENV_DIR.exists():
        create_venv()
        install_requirements()

    relaunch_inside_venv()

def resource_dir() -> Path:
    """Return the likely folder beside the script/executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_latest_html(folder: Path) -> Path | None:
    candidates: list[Path] = []
    for pattern in HTML_PATTERNS:
        candidates.extend(folder.glob(pattern))
    candidates = [p for p in set(candidates) if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def tray_prompt_marker() -> Path:
    """Return the marker file used to avoid nagging about optional tray support."""
    return resource_dir() / TRAY_PROMPT_SENTINEL


def import_tray_modules():
    """Return (pystray, Image, ImageDraw), or (None, None, None) if unavailable."""
    try:
        import pystray  # type: ignore
        from PIL import Image, ImageDraw  # type: ignore
    except Exception:
        return None, None, None
    return pystray, Image, ImageDraw


def tray_support_available() -> bool:
    pystray, Image, ImageDraw = import_tray_modules()
    return bool(pystray and Image and ImageDraw)


def install_tray_packages() -> tuple[bool, str]:
    """Install optional tray packages into the current Python environment."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", *TRAY_PACKAGES],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)

    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    if result.returncode != 0:
        return False, output or f"pip exited with code {result.returncode}"
    return True, output or "Installed pystray and pillow."


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) != 0


def pick_port(start: int = DEFAULT_PORT) -> int:
    for port in range(start, start + 50):
        if is_port_free(port):
            return port
    raise RuntimeError("No free localhost port found in launcher range.")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        # Keep launcher console clean.
        pass


def make_handler(directory: Path):
    class Handler(QuietHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def end_headers(self):
            # Helpful when the app calls local APIs during development.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    return Handler


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ReproseLauncher(tk.Tk):
    def __init__(self, initial_html: Path | None = None):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("620x420")
        self.minsize(560, 360)

        self.html_path: Path | None = initial_html
        self.server: ThreadedTCPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.port: int | None = None
        self.url: str = ""
        self.tray_icon = None
        self.tray_available = tray_support_available()
        self._really_quit = False

        self._build_ui()
        self._apply_basic_style()
        self.after(100, self.initialise)

    def _apply_basic_style(self) -> None:
        self.configure(bg="#1f1f1f")
        for widget in self.winfo_children():
            with contextlib.suppress(Exception):
                widget.configure(bg="#1f1f1f")

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)

        title = tk.Label(
            self,
            text="REPROSE",
            font=("TkDefaultFont", 18, "bold"),
            fg="#d8b45a",
            bg="#1f1f1f",
            pady=12,
        )
        title.grid(row=0, column=0, sticky="ew")

        self.file_var = tk.StringVar(value="No HTML selected yet")
        self.server_var = tk.StringVar(value="Server: not running")
        self.ollama_var = tk.StringVar(value="Ollama: not checked")
        self.model_var = tk.StringVar(value="Models: —")

        file_frame = tk.Frame(self, bg="#1f1f1f")
        file_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        file_frame.columnconfigure(0, weight=1)

        self.file_label = tk.Label(
            file_frame,
            textvariable=self.file_var,
            anchor="w",
            fg="#e8e0cf",
            bg="#2b2b2b",
            relief="sunken",
            padx=8,
            pady=6,
        )
        self.file_label.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        tk.Button(file_frame, text="Choose HTML", command=self.choose_html).grid(row=0, column=1)

        status_frame = tk.Frame(self, bg="#1f1f1f")
        status_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        status_frame.columnconfigure(0, weight=1)

        self.server_label = tk.Label(status_frame, textvariable=self.server_var, anchor="w", fg="#cfcfcf", bg="#1f1f1f")
        self.server_label.grid(row=0, column=0, sticky="ew", pady=2)
        self.ollama_label = tk.Label(status_frame, textvariable=self.ollama_var, anchor="w", fg="#cfcfcf", bg="#1f1f1f")
        self.ollama_label.grid(row=1, column=0, sticky="ew", pady=2)
        self.model_label = tk.Label(status_frame, textvariable=self.model_var, anchor="w", fg="#cfcfcf", bg="#1f1f1f")
        self.model_label.grid(row=2, column=0, sticky="ew", pady=2)

        button_frame = tk.Frame(self, bg="#1f1f1f")
        button_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=10)
        for i in range(6):
            button_frame.columnconfigure(i, weight=1)

        tk.Button(button_frame, text="Launch", command=self.launch).grid(row=0, column=0, sticky="ew", padx=3)
        tk.Button(button_frame, text="Open Browser", command=self.open_browser).grid(row=0, column=1, sticky="ew", padx=3)
        tk.Button(button_frame, text="Check Ollama", command=self.check_ollama_threaded).grid(row=0, column=2, sticky="ew", padx=3)
        tk.Button(button_frame, text="Open Folder", command=self.open_folder).grid(row=0, column=3, sticky="ew", padx=3)
        tk.Button(button_frame, text="Tray", command=self.minimise_to_tray).grid(row=0, column=4, sticky="ew", padx=3)
        tk.Button(button_frame, text="Quit", command=self.quit_app).grid(row=0, column=5, sticky="ew", padx=3)

        hint = tk.Label(
            self,
            text="Tip: place this launcher beside your Reprose HTML file. It will pick the newest reprose*.html automatically.",
            fg="#8f8f8f",
            bg="#1f1f1f",
            wraplength=560,
            justify="left",
        )
        hint.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 8))

        self.log = tk.Text(
            self,
            height=8,
            bg="#111111",
            fg="#d7d7d7",
            insertbackground="#d7d7d7",
            relief="sunken",
            wrap="word",
        )
        self.log.grid(row=5, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.log.configure(state="disabled")

    def initialise(self) -> None:
        if not self.html_path:
            self.html_path = find_latest_html(resource_dir())
        if self.html_path:
            self.file_var.set(str(self.html_path))
            self.log_line(f"Selected: {self.html_path.name}")
        else:
            self.log_line("No Reprose HTML found beside launcher. Choose the file manually.")
        self.check_ollama_threaded()
        self.after(500, self.initialise_tray_support)

    def log_line(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("[%H:%M:%S] ") + text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def choose_html(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose Reprose HTML",
            initialdir=str(resource_dir()),
            filetypes=(("HTML files", "*.html"), ("All files", "*.*")),
        )
        if path:
            self.html_path = Path(path).resolve()
            self.file_var.set(str(self.html_path))
            self.log_line(f"Selected: {self.html_path.name}")

    def ensure_server(self) -> bool:
        if not self.html_path or not self.html_path.exists():
            messagebox.showerror(APP_NAME, "Choose a Reprose HTML file first.")
            return False
        if self.server:
            return True
        try:
            self.port = pick_port(DEFAULT_PORT)
            folder = self.html_path.parent
            handler = make_handler(folder)
            self.server = ThreadedTCPServer(("0.0.0.0", self.port), handler)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            self.url = f"http://localhost:{self.port}/{self.html_path.name}"
            self.server_var.set(f"Server: running at {self.url}")
            self.log_line(f"Serving {folder} on port {self.port}")
            self.log_line(f"LAN access may work at http://<this-computer-ip>:{self.port}/{self.html_path.name}")
            return True
        except Exception as exc:
            self.server_var.set("Server: failed")
            self.log_line(f"Server failed: {exc}")
            messagebox.showerror(APP_NAME, f"Could not start local server:\n{exc}")
            return False

    def launch(self) -> None:
        if self.ensure_server():
            self.open_browser()
            self.check_ollama_threaded()

    def open_browser(self) -> None:
        if not self.ensure_server():
            return
        self.log_line(f"Opening {self.url}")
        webbrowser.open(self.url, new=2, autoraise=True)

    def open_folder(self) -> None:
        folder = self.html_path.parent if self.html_path else resource_dir()
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            self.log_line(f"Could not open folder: {exc}")

    def check_ollama_threaded(self) -> None:
        self.ollama_var.set("Ollama: checking…")
        self.model_var.set("Models: checking…")
        threading.Thread(target=self._check_ollama_worker, daemon=True).start()

    def _check_ollama_worker(self) -> None:
        try:
            with urlopen(OLLAMA_URL + "/api/tags", timeout=3) as response:
                raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            models = sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
            if models:
                text = ", ".join(models[:8]) + ("…" if len(models) > 8 else "")
                self.after(0, lambda: self.ollama_var.set("Ollama: reachable"))
                self.after(0, lambda: self.model_var.set(f"Models: {text}"))
                self.after(0, lambda: self.log_line(f"Ollama reachable, {len(models)} model(s) found."))
            else:
                self.after(0, lambda: self.ollama_var.set("Ollama: reachable"))
                self.after(0, lambda: self.model_var.set("Models: none installed"))
                self.after(0, lambda: self.log_line("Ollama reachable, but no models found."))
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            self.after(0, lambda: self.ollama_var.set("Ollama: not reachable"))
            self.after(0, lambda: self.model_var.set("Models: —"))
            self.after(0, lambda: self.log_line(f"Ollama check failed: {exc}"))

    def initialise_tray_support(self) -> None:
        if self.tray_available:
            self.start_tray_icon()
            self.log_line("Tray support enabled. Closing the window now minimises to tray.")
            return

        marker = tray_prompt_marker()
        if marker.exists():
            self.log_line("Tray support unavailable. Install pystray and pillow to enable it.")
            return

        try:
            marker.write_text("seen\n", encoding="utf-8")
        except OSError:
            pass

        install = messagebox.askyesno(
            APP_NAME,
            "System tray support requires the optional packages pystray and pillow.\n\n"
            "Install them now with pip?",
        )
        if install:
            self.install_tray_threaded()
        else:
            self.log_line("Tray support skipped. The launcher will use normal window behaviour.")

    def install_tray_threaded(self) -> None:
        self.log_line("Installing optional tray support: pystray pillow")
        threading.Thread(target=self._install_tray_worker, daemon=True).start()

    def _install_tray_worker(self) -> None:
        ok, output = install_tray_packages()
        if ok:
            self.after(0, lambda: self.log_line("Tray packages installed."))
            self.after(0, lambda: self.log_line("Attempting to enable tray support without restart."))
            self.after(0, self.enable_tray_after_install)
        else:
            self.after(0, lambda: self.log_line(f"Tray package install failed: {output}"))
            self.after(0, lambda: messagebox.showerror(APP_NAME, "Could not install tray packages.\n\n" + output[-1200:]))

    def enable_tray_after_install(self) -> None:
        self.tray_available = tray_support_available()
        if self.tray_available:
            self.start_tray_icon()
            self.log_line("Tray support enabled. Closing the window now minimises to tray.")
        else:
            self.log_line("Tray packages installed, but imports still failed. Restart the launcher.")
            messagebox.showinfo(APP_NAME, "Tray packages installed. Restart the launcher to enable tray support.")

    def create_tray_image(self):
        pystray, Image, ImageDraw = import_tray_modules()
        if not Image or not ImageDraw:
            return None

        image = Image.new("RGBA", (64, 64), (31, 31, 31, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((6, 6, 58, 58), outline=(216, 180, 90, 255), width=3)
        draw.text((20, 18), "R", fill=(216, 180, 90, 255))
        return image

    def start_tray_icon(self) -> None:
        if self.tray_icon is not None:
            return
        pystray, Image, ImageDraw = import_tray_modules()
        if not pystray:
            return

        image = self.create_tray_image()
        if image is None:
            return

        self.tray_icon = pystray.Icon(
            "reprose-launcher",
            image,
            APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem("Open Reprose", lambda icon, item: self.after(0, self.open_browser)),
                pystray.MenuItem("Show Launcher", lambda icon, item: self.after(0, self.show_window)),
                pystray.MenuItem("Check Ollama", lambda icon, item: self.after(0, self.check_ollama_threaded)),
                pystray.MenuItem("Quit", lambda icon, item: self.after(0, self.quit_app)),
            ),
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def minimise_to_tray(self) -> None:
        if self.tray_available:
            self.start_tray_icon()
            self.withdraw()
            self.log_line("Minimised to tray.")
            return

        messagebox.showinfo(
            APP_NAME,
            "Tray support is not enabled. Install pystray and pillow, then restart if needed.",
        )
        self.iconify()

    def quit_app(self) -> None:
        self._really_quit = True
        self.on_quit()

    def on_quit(self) -> None:
        if self.tray_available and not self._really_quit:
            self.minimise_to_tray()
            return

        if self.tray_icon is not None:
            with contextlib.suppress(Exception):
                self.tray_icon.stop()
            self.tray_icon = None

        if self.server:
            with contextlib.suppress(Exception):
                self.server.shutdown()
                self.server.server_close()
            self.server = None
        self.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Reprose with a stdlib-only Tkinter GUI.")
    parser.add_argument("html", nargs="?", help="Optional path to a Reprose HTML file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    initial = Path(args.html).resolve() if args.html else None
    app = ReproseLauncher(initial)
    app.protocol("WM_DELETE_WINDOW", app.on_quit)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
