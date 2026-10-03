"""Development launcher for the FastAPI PDF service."""

from __future__ import annotations

import subprocess
import sys


def main() -> None:
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--reload",
        ]
    )
    print("FastAPI service started at http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
