"""Application entry point. All comments and docstrings are in English."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

# Also support the beginner-friendly direct-file launch command.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "shadow"


def main():
    parser = argparse.ArgumentParser(description="Shadow camera privacy monitor")
    parser.add_argument("--background", action="store_true", help="Start hidden in the system tray")
    parser.add_argument("--scan", action="store_true", help="Print one read-only registry scan and exit")
    parser.add_argument("--data-dir", type=Path, help="Override local data folder for isolated testing")
    parser.add_argument("--smoke-test", action="store_true", help="Open UI and tray, then exit after 5 seconds")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Shadow requires Windows 10 or Windows 11.")
    from .monitor import scan_camera
    if args.scan:
        from dataclasses import asdict
        print(json.dumps(asdict(scan_camera()), indent=2, ensure_ascii=True))
        return
    import tkinter as tk
    from tkinter import messagebox
    from .platform_windows import SingleInstance
    instance = SingleInstance()
    if instance.already_running:
        messagebox.showinfo("Shadow", "Shadow is already running. Open it from the system tray.\n"
                            "影子已在运行，请从系统托盘打开。")
        instance.close()
        return
    root = None
    try:
        data_dir = args.data_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Shadow"
        data_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(data_dir / "shadow.log", maxBytes=1_000_000,
                                      backupCount=3, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, handlers=[handler],
                            format="%(asctime)s %(levelname)s %(message)s", force=True)
        from .app import ShadowApp
        root = tk.Tk()
        app = ShadowApp(root, data_dir, args.background)
        def callback_error(kind, value, traceback):
            logging.error("UI callback failed", exc_info=(kind, value, traceback))
            messagebox.showerror("Shadow", str(value), parent=root)
        root.report_callback_exception = callback_error
        if args.smoke_test:
            root.after(5000, app.quit)
        root.mainloop()
    except Exception as error:
        logging.exception("Shadow could not start")
        # A native dialog still works if Tk itself fails to initialize.
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(error), "Shadow could not start", 0x10)
        raise
    finally:
        instance.close()


if __name__ == "__main__":
    main()
