"""Auto-restart the POS app when Python files under app/ change."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

ROOT = Path(__file__).resolve().parent
WATCH_DIR = ROOT / "app"
DEBOUNCE_SEC = 0.6


class RestartHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._pending = False
        self._last_change = 0.0

    def start_app(self) -> None:
        self.stop_app()
        print("\n[dev] starting POS …", flush=True)
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "app.main"],
            cwd=ROOT,
        )

    def stop_app(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=3)
        self._proc = None

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.suffix != ".py":
            return
        if "__pycache__" in path.parts:
            return
        self._pending = True
        self._last_change = time.monotonic()
        print(f"[dev] change: {path.relative_to(ROOT)}", flush=True)

    def maybe_restart(self) -> None:
        if not self._pending:
            return
        if time.monotonic() - self._last_change < DEBOUNCE_SEC:
            return
        self._pending = False
        print("[dev] restarting …", flush=True)
        self.start_app()


def main() -> None:
    if not WATCH_DIR.is_dir():
        raise SystemExit(f"Watch directory missing: {WATCH_DIR}")

    handler = RestartHandler()
    handler.start_app()

    observer = Observer()
    observer.schedule(handler, str(WATCH_DIR), recursive=True)
    observer.start()
    print(f"[dev] watching {WATCH_DIR} — Ctrl+C to stop", flush=True)

    try:
        while True:
            handler.maybe_restart()
            time.sleep(0.2)
            if handler._proc is not None and handler._proc.poll() is not None:
                code = handler._proc.returncode
                if code not in (0, None) and not handler._pending:
                    print(f"[dev] app exited with code {code}", flush=True)
                    handler._proc = None
    except KeyboardInterrupt:
        print("\n[dev] stopping …", flush=True)
    finally:
        observer.stop()
        observer.join(timeout=3)
        handler.stop_app()


if __name__ == "__main__":
    main()
