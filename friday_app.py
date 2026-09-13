#!/usr/bin/env python3
"""
FRIDAY — Age-of-Ultron style desktop command center for Linux.

Wraps friday_web.py + friday_ui.html in a WebKitGTK window and runs the
offline wake-word engine (friday_voice.py, Vosk + arecord) in the
background. No Electron: just Python + GTK + Vosk.

Requires (installed by install.sh):
    sudo apt install python3-gi gir1.2-webkit2-4.1 alsa-utils
    pip3 install --user openai vosk pyttsx3
    + Vosk model at ~/.local/share/friday/model
"""

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "friday_web.py")
VOICE_SCRIPT = os.path.join(HERE, "friday_voice.py")

APP_ID = "io.github.friday.app"
APP_NAME = "FRIDAY"
PORT = 8300


# ---------------------------------------------------------------------------
# Embedded server
# ---------------------------------------------------------------------------

def find_free_port(start=PORT):
    for port in range(start, start + 64):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return PORT


class ServerHandle:
    def __init__(self):
        self.port = find_free_port()
        self.proc = None

    def start(self):
        if self.proc and self.proc.poll() is None:
            return True
        env = dict(os.environ)
        env["FRIDAY_PORT"] = str(self.port)
        self.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT, "--host", "127.0.0.1",
             "--port", str(self.port)],
            cwd=HERE, env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/api/stats",
                        timeout=1) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
            if self.proc.poll() is not None:
                return False
            time.sleep(0.15)
        return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Wake-word voice engine (subprocess, auto-resurrected)
# ---------------------------------------------------------------------------

class VoiceEngine:
    def __init__(self, port):
        self.port = port
        self.proc = None
        self.stop_flag = threading.Event()

    def _spawn(self):
        if self.stop_flag.is_set():
            return
        env = dict(os.environ)
        env["FRIDAY_VSERVER"] = f"http://127.0.0.1:{self.port}"
        try:
            self.proc = subprocess.Popen(
                [sys.executable, VOICE_SCRIPT],
                cwd=HERE, env=env, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except Exception as e:
            print("FRIDAY voice spawn failed:", e)

    def run(self):
        self._spawn()
        while not self.stop_flag.wait(5):
            if self.proc and self.proc.poll() is not None:
                # crashed — give the server a moment, then resurrect
                time.sleep(2)
                self._spawn()

    def stop(self):
        self.stop_flag.set()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# WebKitGTK fallbacks (4.1 then 4.0, GTK3)
# ---------------------------------------------------------------------------

def _import_webkit():
    import gi
    gi.require_version("Gtk", "3.0")
    try:
        gi.require_version("WebKit2", "4.1")
    except ValueError:
        gi.require_version("WebKit2", "4.0")
    from gi.repository import Gtk, WebKit2, GLib
    return Gtk, WebKit2, GLib


def run_gui(server, voice):
    Gtk, WebKit2, GLib = _import_webkit()

    app = Gtk.Application.new(APP_ID, 0)
    win = None

    def on_activate(a):
        nonlocal win
        if win is not None:
            win.present()
            return
        win = Gtk.ApplicationWindow(application=a, title=APP_NAME)
        win.set_default_size(1240, 800)
        win.set_position(Gtk.WindowPosition.CENTER)

        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(b"""
                window { background:#070311; }
                webview { background:#070311; }
            """)
            Gtk.StyleContext.add_provider_for_screen(
                Gtk.Screen.get_default(), provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:
            pass

        web = WebKit2.WebView()
        settings = web.get_settings()
        settings.set_enable_developer_extras(True)
        settings.set_enable_media_stream(True)  # voice-in (push-to-talk)
        if hasattr(settings, "set_media_content_types_requiring_hardware_acceleration"):
            try:
                settings.set_media_content_types_requiring_hardware_acceleration(b"")
            except Exception:
                pass

        win.add(web)
        win.show_all()

        def load():
            web.load_uri(f"http://127.0.0.1:{server.port}/")

        threading.Thread(target=_wait_then,
                         args=(server, voice, GLib, load),
                         daemon=True).start()

    app.connect("activate", on_activate)
    try:
        exit_status = app.run([])
    finally:
        voice.stop()
        server.stop()
    return exit_status


def _wait_then(server, voice, glib, fn):
    if server.start():
        threading.Thread(target=voice.run, daemon=True).start()
        glib.idle_add(fn)
    def _watch():
        while True:
            time.sleep(6)
            if server.proc and server.proc.poll() is not None:
                if server.start():
                    glib.idle_add(fn)
    threading.Thread(target=_watch, daemon=True).start()


# ---------------------------------------------------------------------------
# CLI / launcher
# ---------------------------------------------------------------------------

def main():
    for f in (SERVER_SCRIPT,):
        if not os.path.exists(f):
            print(f"ERROR: expected {f} — keep friday_app.py and its server files together.")
            sys.exit(1)

    server = ServerHandle()
    voice = VoiceEngine(server.port)

    try:
        run_gui(server, voice)
    except (ImportError, ValueError) as e:
        print("FRIDAY needs the WebKitGTK bridge. Install with:\n"
              "  sudo apt install python3-gi gir1.2-webkit2-4.1")
        print(f"({e})")
        server.stop()
        voice.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()