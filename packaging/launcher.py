"""Windows launcher for the frozen HCMUS Hub dashboard."""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from hcmus_hub.web_server import serve_dashboard


HOST = "127.0.0.1"
PORT = 8787
URL = f"http://{HOST}:{PORT}/"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "HCMUS Hub"
DATABASE_NAME = "hcmus_hub.sqlite3"


def _load_env(path: Path) -> None:
    """Load simple KEY=VALUE entries without requiring python-dotenv."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value


def _legacy_database_candidates() -> list[Path]:
    candidates = [Path.cwd() / "data" / DATABASE_NAME]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "data" / DATABASE_NAME)
    return candidates


def _prepare_database() -> Path:
    data_dir = APP_DATA_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / DATABASE_NAME
    if target.exists():
        return target
    for source in _legacy_database_candidates():
        source = source.resolve()
        if source == target or not source.is_file():
            continue
        shutil.copy2(source, target)
        break
    if not target.exists():
        raise FileNotFoundError(
            f"Không tìm thấy CSDL. Đặt {DATABASE_NAME} vào {data_dir} "
            "hoặc chạy bản phát triển để tạo CSDL trước."
        )
    return target


def _is_server_ready() -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=0.8) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def main() -> int:
    if _is_server_ready():
        webbrowser.open(URL)
        return 0

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _load_env(APP_DATA_DIR / ".env")
    database = _prepare_database()
    failure: list[BaseException] = []

    def run_server() -> None:
        try:
            serve_dashboard(database, HOST, PORT)
        except BaseException as exc:
            failure.append(exc)

    thread = threading.Thread(target=run_server, name="hcmus-hub-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _is_server_ready():
            webbrowser.open(URL)
            thread.join()
            return 0
        if failure:
            raise RuntimeError("Không thể khởi động HCMUS Hub") from failure[0]
        time.sleep(0.25)
    raise TimeoutError(f"Server không sẵn sàng sau 30 giây: {URL}")


if __name__ == "__main__":
    raise SystemExit(main())
