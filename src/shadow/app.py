"""Tk dashboard with a Windows tray and a read-only registry worker."""
from datetime import datetime
import logging
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw
import pystray

from .monitor import scan_camera, Snapshot, Tracker
from .notifier import Notifier
from .platform_windows import set_startup, startup_enabled
from .storage import Store


def make_icon(color="#5d75ff"):
    """Draw a small shield without external image assets."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon([(32, 3), (57, 13), (53, 42), (44, 53), (32, 61),
                  (20, 53), (11, 42), (7, 13)], fill=color)
    draw.ellipse((19, 22, 45, 44), fill="white")
    draw.ellipse((26, 27, 38, 39), fill=color)
    return image


def local_time(value):
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%m-%d %H:%M:%S")
    except ValueError:
        return value


class ShadowApp:
    def __init__(self, root, data_dir, background=False):
        self.root = root
        self.data_dir = Path(data_dir)
        self.store = Store(self.data_dir / "history.sqlite3")
        self.tracker = Tracker()
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.scan_enabled = threading.Event()
        self.scan_enabled.set()
        self.generation = 0
        self.closing = False
        self.paused = False
        self.status = "CHECKING"
        self.last_error = None
        self.muted = set(self.store.get("muted", []))
        self.notify_enabled = tk.BooleanVar(value=self.store.get("notifications", True))
        self.startup = tk.BooleanVar(value=startup_enabled())
        self.build_ui()
        self.icon = pystray.Icon("Shadow", make_icon(), "Shadow · Checking camera", menu=pystray.Menu(
            pystray.MenuItem("Open Shadow / 打开", lambda: self.events.put(("show", None)), default=True),
            pystray.MenuItem(lambda item: "Camera: " + self.status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: "Resume / 继续" if self.paused else "Pause / 暂停",
                            lambda: self.events.put(("pause", None))),
            pystray.MenuItem("Test notification / 测试通知", lambda: self.events.put(("test", None))),
            pystray.MenuItem("Exit / 退出", lambda: self.events.put(("quit", None))),
        ))
        self.notifier = Notifier(self.icon)
        self.tray_thread = threading.Thread(target=self.run_tray, daemon=True)
        self.tray_thread.start()
        self.worker = threading.Thread(target=self.monitor_loop, daemon=True)
        self.worker.start()
        self.refresh_history()
        if background:
            root.withdraw()
        root.after(150, self.pump)

    def build_ui(self):
        root = self.root
        root.title("影子 Shadow — Camera Privacy")
        root.geometry("1000x700")
        root.minsize(850, 580)
        root.configure(bg="#101827")
        root.protocol("WM_DELETE_WINDOW", self.hide)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        self.heading = tk.Label(root, text="影子  SHADOW", font=("Segoe UI", 23, "bold"),
                                fg="white", bg="#101827")
        self.heading.pack(anchor="w", padx=26, pady=(22, 3))
        tk.Label(root, text="Camera privacy, made visible.  ·  摄像头访问，本地可见",
                 fg="#a5b4c9", bg="#101827", font=("Segoe UI", 11)).pack(anchor="w", padx=28)
        self.status_label = tk.Label(root, text="● CHECKING / 检查中", bg="#101827",
                                     fg="#f8c46a", font=("Segoe UI", 20, "bold"))
        self.status_label.pack(anchor="w", padx=27, pady=(20, 4))
        self.detail = tk.Label(root, text="Reading Windows camera access records…",
                               bg="#101827", fg="#c3ccdc", anchor="w", justify="left",
                               wraplength=920, font=("Segoe UI", 10))
        self.detail.pack(anchor="w", padx=28, pady=(0, 16))
        options = ttk.Frame(root, padding=10)
        options.pack(fill="x", padx=26)
        ttk.Checkbutton(options, text="Notifications / 通知", variable=self.notify_enabled,
                        command=self.save_notifications).pack(side="left", padx=5)
        ttk.Checkbutton(options, text="Start at login / 登录时启动", variable=self.startup,
                        command=self.change_startup).pack(side="left", padx=14)
        self.pause_button = ttk.Button(options, text="Pause / 暂停", command=self.toggle_pause)
        self.pause_button.pack(side="right", padx=5)
        ttk.Button(options, text="Test / 测试通知", command=self.test_notification).pack(side="right", padx=5)
        panel = ttk.Frame(root, padding=12)
        panel.pack(fill="both", expand=True, padx=26, pady=14)
        ttk.Label(panel, text="Access history / 访问历史 · latest 500 records",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        table = ttk.Frame(panel)
        table.pack(fill="both", expand=True)
        columns = ("app", "start", "end", "duration", "state", "alert")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        for name, title, width in zip(columns,
                ("Application / 应用", "Observed / 发现时间", "Last event / 结束", "Duration", "Status", "Alerts"),
                (190, 140, 140, 80, 125, 60)):
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, minwidth=55)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda event: self.show_details())
        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(10, 0))
        for title, command in (("Details / 详情", self.show_details),
                               ("Mute / 取消静音", self.toggle_mute),
                               ("Export CSV / 导出", self.export),
                               ("Data folder / 数据目录", self.open_data)):
            ttk.Button(actions, text=title, command=command).pack(side="left", padx=(0, 7))
        footer = tk.Frame(root, bg="#101827")
        footer.pack(fill="x", padx=26, pady=(0, 18))
        tk.Label(footer, text="Local only · No camera footage · Alerts do not block access\n"
                 "仅监控 Windows 访问记录；无法识别具体网页。关闭窗口后继续在托盘运行。",
                 fg="#a5b4c9", bg="#101827", justify="left", font=("Segoe UI", 9)).pack(side="left")
        ttk.Button(footer, text="Exit / 退出", command=self.quit).pack(side="right")

    def run_tray(self):
        try:
            self.icon.run()
        except Exception as error:
            logging.exception("Tray failed")
            self.events.put(("tray_error", str(error)))

    def monitor_loop(self):
        while not self.stop_event.is_set():
            if self.scan_enabled.is_set():
                generation = self.generation
                try:
                    snapshot = scan_camera()
                except Exception as error:
                    logging.exception("Camera scan failed")
                    snapshot = Snapshot(errors=[str(error)])
                self.events.put(("snapshot", (generation, snapshot)))
            self.stop_event.wait(1)

    def pump(self):
        try:
            for _ in range(50):
                try:
                    kind, value = self.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "snapshot":
                    generation, snapshot = value
                    if not self.paused and generation == self.generation:
                        self.apply_snapshot(snapshot)
                elif kind == "show":
                    self.show()
                elif kind == "pause":
                    self.toggle_pause()
                elif kind == "test":
                    self.test_notification()
                elif kind == "quit":
                    self.quit()
                    return
                elif kind == "tray_error":
                    self.show()
                    messagebox.showerror("Shadow tray error", value, parent=self.root)
            self.notifier.tick()
        except Exception as error:
            logging.exception("Application event failed")
            self.set_status("ERROR", "操作失败 / Operation failed: " + str(error), "#f8c46a")
        if not self.closing:
            self.root.after(150, self.pump)

    def apply_snapshot(self, snapshot):
        started, stopped = self.tracker.update(snapshot)
        for app in stopped:
            duration = self.store.stop(app)
            self.alert(app, "Camera stopped / 摄像头停止", f"{app.name}\nObserved duration: {duration // 60}m {duration % 60}s")
        for app in started:
            self.store.start(app)
            self.alert(app, "Camera in use / 摄像头正在使用", f"{app.name}\nDetected: {datetime.now():%H:%M:%S}")
        if snapshot.errors:
            detail = "Windows records could not be read completely. Status is uncertain.\n" + snapshot.errors[0]
            self.set_status("UNKNOWN / 状态未知", detail, "#f8c46a")
            if self.last_error is None:
                logging.warning("Incomplete camera scan: %s", snapshot.errors)
                if self.notify_enabled.get():
                    self.notifier.send("Shadow · Monitoring unavailable", "Camera state is unknown. Open Shadow for details.")
            self.last_error = snapshot.errors[0]
        else:
            self.last_error = None
            if snapshot.apps:
                names = ", ".join(app.name for app in snapshot.apps.values())
                self.set_status("IN USE / 正在使用", names, "#ff7d87")
            else:
                self.set_status("OFF / 未检测到使用", "No active camera access reported by Windows.", "#6ce5b1")
        if started or stopped:
            self.refresh_history()

    def set_status(self, status, detail, color):
        changed = self.status != status
        self.status = status
        self.status_label.configure(text="● " + status, fg=color)
        self.detail.configure(text=detail[:600])
        self.icon.title = "Shadow · " + status
        if changed:
            self.icon.icon = make_icon(color)
            self.icon.update_menu()

    def alert(self, app, title, message):
        if self.notify_enabled.get() and app.identity not in self.muted:
            self.notifier.send(title, message)

    def save_notifications(self):
        self.store.set("notifications", self.notify_enabled.get())
        if not self.notify_enabled.get():
            self.notifier.clear()

    def change_startup(self):
        try:
            set_startup(self.startup.get())
        except OSError as error:
            self.startup.set(not self.startup.get())
            messagebox.showerror("Startup setting", str(error), parent=self.root)

    def toggle_pause(self):
        self.paused = not self.paused
        self.generation += 1
        self.notifier.clear()
        if self.paused:
            self.scan_enabled.clear()
            self.store.interrupt("paused")
            self.tracker = Tracker()
            self.set_status("PAUSED / 已暂停", "Camera activity is not monitored while paused.", "#a5b4c9")
        else:
            self.scan_enabled.set()
            self.set_status("CHECKING / 检查中", "Reading Windows camera access records…", "#f8c46a")
        self.pause_button.configure(text="Resume / 继续" if self.paused else "Pause / 暂停")
        self.icon.update_menu()
        self.refresh_history()

    def refresh_history(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.history = {str(row["id"]): row for row in self.store.rows()}
        for key, row in self.history.items():
            seconds = row["duration_seconds"]
            duration = "—" if seconds is None else f"{seconds // 60}m {seconds % 60}s"
            self.tree.insert("", "end", iid=key, values=(row["name"], local_time(row["observed_start"]),
                local_time(row["observed_end"]), duration, row["status"],
                "Muted" if row["identity"] in self.muted else "On"))
        if selected and selected[0] in self.history:
            self.tree.selection_set(selected[0])

    def selected_row(self):
        selection = self.tree.selection()
        if selection:
            return self.history.get(selection[0])
        messagebox.showinfo("Shadow", "Select a history entry first. / 请先选择一条记录。", parent=self.root)

    def show_details(self):
        row = self.selected_row()
        if row is not None:
            messagebox.showinfo("Access details / 访问详情", "\n\n".join(
                f"{key}: {value if value is not None else 'Unknown'}" for key, value in dict(row).items()), parent=self.root)

    def toggle_mute(self):
        row = self.selected_row()
        if row is not None:
            key = row["identity"]
            if key in self.muted:
                self.muted.remove(key)
            else:
                self.muted.add(key)
            self.store.set("muted", sorted(self.muted))
            self.notifier.clear()
            self.refresh_history()

    def export(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv",
            initialfile="shadow-history.csv", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                self.store.export(path)
                messagebox.showinfo("Shadow", "History exported. / 已导出访问记录。", parent=self.root)
            except OSError as error:
                messagebox.showerror("Export failed", str(error), parent=self.root)

    def open_data(self):
        os.startfile(self.data_dir)

    def test_notification(self):
        self.notifier.send("Shadow · Test notification", "影子正在运行。This is a test; it does not access the camera.")

    def hide(self):
        if self.icon.visible:
            self.root.withdraw()
            self.notifier.send("Shadow · Running in background", "Right-click the shield in the system tray to open or exit.")
        else:
            messagebox.showinfo("Shadow", "The tray is not ready. Please keep this window open.", parent=self.root)

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def quit(self):
        if self.closing:
            return
        self.closing = True
        self.stop_event.set()
        self.worker.join(timeout=3)
        try:
            self.store.interrupt("monitor_exited")
            self.store.close()
        finally:
            self.icon.stop()
            self.root.destroy()
