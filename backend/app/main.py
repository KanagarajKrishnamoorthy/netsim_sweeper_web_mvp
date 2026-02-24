from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.services.runtime_guard import runtime_guard


app = FastAPI(
    title="NetSim Multi-Parameter Sweeper",
    version="0.1.0",
    description="Web API for NetSim multi-parameter sweep planning and execution.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

frontend_dist = settings.resolved_frontend_dist_dir()
if frontend_dist and (frontend_dist / "index.html").exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(str(frontend_dist / "index.html"))


@app.on_event("startup")
def app_startup() -> None:
    runtime_guard.start()


@app.on_event("shutdown")
def app_shutdown() -> None:
    runtime_guard.stop()
