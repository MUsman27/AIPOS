import os

import uvicorn

from app.server import app


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("AIPOS_PORT", "8000")),
        log_level="warning",
        access_log=False,
    )