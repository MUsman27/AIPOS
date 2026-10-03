"""FastAPI service entry point for the PDF backend."""

from __future__ import annotations

import uvicorn

from app.server import app


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
