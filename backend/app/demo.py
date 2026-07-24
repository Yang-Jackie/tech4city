"""Backend application entry point with the local chat demo mounted."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .main import create_app

STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_demo_app(**backend_options: Any) -> FastAPI:
    """Create the backend and mount its same-origin demo frontend."""
    application = create_app(**backend_options)

    @application.get("/", include_in_schema=False)
    async def redirect_to_demo() -> RedirectResponse:
        return RedirectResponse(url="/demo/")

    application.mount(
        "/demo",
        StaticFiles(directory=STATIC_DIR, html=True),
        name="demo",
    )
    return application


app = create_demo_app()
