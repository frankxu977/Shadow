"""Read Windows camera access metadata without opening the camera."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import ntpath
import winreg

WEBCAM_REGISTRY_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion"
    r"\CapabilityAccessManager\ConsentStore\webcam"
)
EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CameraApp:
    identity: str
    name: str
    path: str
    started: str | None


@dataclass
class Snapshot:
    apps: dict[str, CameraApp] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def reliable(self):
        return not self.errors


def filetime_to_iso(value):
    """Convert a positive Windows FILETIME into a UTC timestamp."""
    if not isinstance(value, int) or value <= 0:
        return None
    try:
        return (EPOCH + timedelta(microseconds=value // 10)).isoformat()
    except (OverflowError, ValueError):
        return None


def describe_app(identity, started):
    if identity.startswith("NonPackaged\\"):
        path = identity[len("NonPackaged\\"):].replace("#", "\\")
        name = ntpath.basename(path) or "Unknown application"
    else:
        path = identity
        package = identity.split("\\")[0]
        name = package.split("_")[0] or "Unknown application"
    return CameraApp(identity, name, path, started)


def scan_camera(reg=winreg):
    """Return active records; failed reads must never imply camera OFF."""
    result = Snapshot()

    def visit(key, path):
        try:
            start, _ = reg.QueryValueEx(key, "LastUsedTimeStart")
        except FileNotFoundError:
            start = None
        except OSError as error:
            result.errors.append(f"Cannot read start: {path}: {error}")
            start = None
        if start is not None:
            try:
                stop, _ = reg.QueryValueEx(key, "LastUsedTimeStop")
                if not isinstance(start, int) or not isinstance(stop, int):
                    result.errors.append(f"Invalid timestamp: {path}")
                elif start > 0 and stop == 0:
                    result.apps[path] = describe_app(path, filetime_to_iso(start))
            except OSError as error:
                result.errors.append(f"Cannot read stop: {path}: {error}")
        index = 0
        while True:
            try:
                name = reg.EnumKey(key, index)
            except OSError as error:
                if getattr(error, "winerror", None) != 259:
                    result.errors.append(f"Cannot enumerate: {path}: {error}")
                break
            index += 1
            child_path = f"{path}\\{name}" if path else name
            try:
                with reg.OpenKey(key, name, 0, reg.KEY_READ) as child:
                    visit(child, child_path)
            except OSError as error:
                result.errors.append(f"Cannot open: {child_path}: {error}")

    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, WEBCAM_REGISTRY_PATH,
                         0, reg.KEY_READ) as root:
            visit(root, "")
    except OSError as error:
        result.errors.append(f"Camera access records unavailable: {error}")
    return result


class Tracker:
    """Track per-app changes and keep known sessions during scan failures."""
    def __init__(self):
        self.active = {}

    def update(self, snapshot):
        previous = self.active
        current = snapshot.apps
        started, stopped = [], []
        for identity, app in current.items():
            old = previous.get(identity)
            if old is None:
                started.append(app)
            elif old.started != app.started:
                stopped.append(old)
                started.append(app)
        if snapshot.reliable:
            stopped.extend(app for key, app in previous.items() if key not in current)
            self.active = dict(current)
        else:
            self.active = {**previous, **current}
        return started, stopped
