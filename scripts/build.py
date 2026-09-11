"""Build a standalone Windows executable from the project environment."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from shadow.app import make_icon


def main():
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    icon = assets / "shadow.ico"
    make_icon().save(icon, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "Shadow", "--icon", str(icon),
        "--paths", str(ROOT / "src"), "--hidden-import", "pystray._win32",
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"), str(ROOT / "run_shadow.pyw")
    ], cwd=ROOT, check=True)
    print(f"Ready: {ROOT / 'dist' / 'Shadow.exe'}")


if __name__ == "__main__":
    main()
