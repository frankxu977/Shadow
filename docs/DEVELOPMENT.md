# Development / 开发说明

Code comments and docstrings are in English. The UI uses Chinese and English.

## Run from source

Run these commands in the Shadow project folder with Windows Python 3.11+:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe src\shadow\main.py
```

No activation or administrator rights are required. Use `pythonw.exe run_shadow.pyw`
to start without a console. Add `--background` to start hidden in the system tray.
`python src\shadow\main.py --scan` prints a read-only diagnostic scan.

## Test and build

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts\build.py
```

The executable is `dist\Shadow.exe`. It includes Python and the dependencies.
The build is unsigned. Do not promise a signed or antivirus-certified release.
Packaging reference: https://pyinstaller.org/en/stable/operating-mode.html

## Modules

- `monitor.py`: read HKCU camera metadata and calculate per-app transitions.
- `storage.py`: SQLite sessions, preferences and CSV exports.
- `app.py`: Tk dashboard and queue-based background scan worker.
- `notifier.py`: native Windows tray notifications, serialized every five seconds.
- `platform_windows.py`: named mutex and optional per-user login startup entry.
- `main.py`: CLI, local data directory, rotating logs and lifecycle.

Tk and SQLite run on the main thread. The registry worker posts snapshots through
a queue. The tray callbacks also post commands through the queue.

## Manual acceptance checks

1. Start Shadow. The dashboard and shield tray icon should appear.
2. Press Test to check a desktop notification without opening the camera.
3. Open Windows Camera manually. Expect an IN USE record within approximately
   one polling interval, plus any Windows registry/notification delay.
4. Close Camera. Expect a stopped record and observed duration.
5. Repeat with a browser camera preview. Only the browser may be identified.
6. Pause and resume. Paused sessions must not be labeled camera stopped.
7. Mute an app from history; later activity remains recorded without alerts.
8. Close the dashboard, reopen from the shield, then exit using the menu.
9. Export CSV and inspect history. Restart; the history should persist.
10. Optionally enable Start at login, then disable it again to verify removal.

Tests use synthetic registry records and do not open or record the camera.

## Boundaries

The registry heuristic is not a supported hardware monitoring API. Windows may
leave stale records, omit activity, or report it late. Missing/denied metadata
is UNKNOWN, not OFF. A readable empty store means only no reported active access.
The current Windows user's records are monitored; other accounts are not covered.
The app does not block access, identify individual browser tabs, or capture images.
Sub-second sessions can be missed by one-second polling.

The history uses observed start/end timestamps and an observed duration. Registry
start time is separately retained in Details. A crash/restart, pause, or application
exit ends observation, not necessarily camera access. These rows have explicit
statuses and no fabricated camera duration. A detected timestamp restart ends the
previous observation at the next scan; its exact hardware stop time is unknown.

Notifications use the Windows tray notification API through pystray:
https://pystray.readthedocs.io/en/latest/usage.html
Windows notification settings and Do Not Disturb can suppress banners. Notifications
are informational; the history remains the record. A queue holds at most 100 pending
alerts and displays them at least five seconds apart.

## Local data and removal

Data lives under `%LOCALAPPDATA%\Shadow`: `history.sqlite3` and rotating `shadow.log`.
No application network calls are made. Dependency installation needs Internet access.
History includes app paths, which can contain usernames; review exports before sharing.
Disable Start at login before moving or removing the executable. Exit via the tray.
Remove the app folder; optionally remove the data folder to erase local history.
Startup only writes the `ShadowCameraWatcher` value in the current user's Run key.
