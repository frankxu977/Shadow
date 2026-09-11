"""Background-only Windows tray application."""
from datetime import datetime
import ctypes
import logging
import os
from pathlib import Path
import threading

import pystray

from .icons import make_icon
from .monitor import scan_camera, Snapshot, Tracker
from .notifier import Notifier
from .platform_windows import set_startup, startup_enabled
from .storage import Store


def message(title, body, error=False):
    flags = 0x10 if error else 0x40
    ctypes.windll.user32.MessageBoxW(None, body, title, flags)


class TrayApp:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.store = Store(self.data_dir / "history.sqlite3")
        self.tracker = Tracker()
        self.stop_event = threading.Event()
        self.paused = False
        self.status = "CHECKING / 检查中"
        self.details = "Reading Windows camera access records."
        self.muted = set(self.store.get("muted", []))
        self.notifications = self.store.get("notifications", True)
        self.icon = pystray.Icon("Shadow", make_icon(), "Shadow · Checking camera")
        self.notifier = Notifier(self.icon)
        self.icon.menu = pystray.Menu(
            pystray.MenuItem(lambda item: "Camera: " + self.status,
                             self.show_status, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open history / 查看历史", self.open_history),
            pystray.MenuItem(lambda item: "Resume / 继续" if self.paused else "Pause / 暂停",
                             self.toggle_pause),
            pystray.MenuItem("Notifications / 通知", self.toggle_notifications,
                             checked=lambda item: self.notifications),
            pystray.MenuItem("Start at login / 登录时启动", self.toggle_startup,
                             checked=lambda item: startup_enabled()),
            pystray.MenuItem("Test notification / 测试通知", self.test_notification),
            pystray.MenuItem("Open data folder / 数据目录", self.open_data),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Shadow / 退出", self.quit),
        )

    def run(self):
        self.icon.run(setup=self.monitor_loop)

    def monitor_loop(self, icon):
        icon.visible = True
        self.notifier.send("Shadow is running / 影子正在运行",
                           "Camera access monitoring is active. Right-click the shield for options.")
        try:
            while not self.stop_event.wait(1):
                if not self.paused:
                    try:
                        self.apply_snapshot(scan_camera())
                    except Exception as error:
                        logging.exception("Camera scan failed")
                        self.apply_snapshot(Snapshot(errors=[str(error)]))
                self.notifier.tick()
        finally:
            self.store.interrupt("monitor_exited")
            self.store.close()

    def apply_snapshot(self, snapshot):
        started, stopped = self.tracker.update(snapshot)
        for app in stopped:
            duration = self.store.stop(app)
            self.alert(app, "Camera stopped / 摄像头停止",
                       f"{app.name}\nObserved duration: {duration // 60}m {duration % 60}s")
        for app in started:
            self.store.start(app)
            self.alert(app, "Camera in use / 摄像头正在使用",
                       f"{app.name}\nDetected: {datetime.now():%H:%M:%S}")
        if snapshot.errors:
            self.set_status("UNKNOWN / 状态未知",
                            "Windows camera records could not be read completely.", "#f8c46a")
        elif snapshot.apps:
            names = ", ".join(app.name for app in snapshot.apps.values())
            self.set_status("IN USE / 正在使用", names, "#ff7d87")
        else:
            self.set_status("OFF / 未检测到使用",
                            "Windows reports no active camera access.", "#6ce5b1")

    def set_status(self, status, details, color):
        changed = status != self.status
        self.status, self.details = status, details
        self.icon.title = "Shadow · " + status
        if changed:
            self.icon.icon = make_icon(color)
            self.icon.update_menu()

    def alert(self, app, title, body):
        if self.notifications and app.identity not in self.muted:
            self.notifier.send(title, body)

    def show_status(self, icon=None, item=None):
        message("影子 Shadow", f"Camera: {self.status}\n\n{self.details}\n\n"
                "Shadow monitors Windows access records and does not block camera access.")

    def open_history(self, icon=None, item=None):
        try:
            target = self.data_dir / "shadow-history.csv"
            self.store.export(target)
            os.startfile(target)
        except OSError as error:
            message("Shadow", str(error), True)

    def open_data(self, icon=None, item=None):
        os.startfile(self.data_dir)

    def toggle_pause(self, icon=None, item=None):
        self.paused = not self.paused
        self.notifier.clear()
        if self.paused:
            self.store.interrupt("paused")
            self.tracker = Tracker()
            self.set_status("PAUSED / 已暂停", "Camera activity is not monitored.", "#a5b4c9")
        else:
            self.set_status("CHECKING / 检查中", "Reading Windows camera access records.", "#f8c46a")
        self.icon.update_menu()

    def toggle_notifications(self, icon=None, item=None):
        self.notifications = not self.notifications
        self.store.set("notifications", self.notifications)
        if not self.notifications:
            self.notifier.clear()
        self.icon.update_menu()

    def toggle_startup(self, icon=None, item=None):
        try:
            set_startup(not startup_enabled())
            self.icon.update_menu()
        except OSError as error:
            message("Shadow startup setting", str(error), True)

    def test_notification(self, icon=None, item=None):
        self.notifier.send("Shadow · Test notification",
                           "影子正在运行。This test does not access the camera.")

    def quit(self, icon=None, item=None):
        self.stop_event.set()
        self.icon.stop()
