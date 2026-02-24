from __future__ import annotations

import uvicorn

from app.main import app
from app.core.config import settings


def main() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
