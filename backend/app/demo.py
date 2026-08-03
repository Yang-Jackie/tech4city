"""Backend application entry point with the local chat demo mounted."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .main import create_app

FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_demo_app(
    *,
    frontend_dist_dir: str | Path | None = None,
    **backend_options: Any,
) -> FastAPI:
    """Create the backend and mount the built same-origin React frontend."""
    application = create_app(**backend_options)
    static_dir = (
        Path(frontend_dist_dir)
        if frontend_dist_dir is not None
        else FRONTEND_DIST_DIR
    )

    @application.get("/", include_in_schema=False)
    async def redirect_to_demo() -> RedirectResponse:
        return RedirectResponse(url="/demo/")

    if static_dir.is_dir() and (static_dir / "index.html").is_file():
        application.mount(
            "/demo",
            StaticFiles(directory=static_dir, html=True),
            name="demo",
        )
    else:

        @application.get("/demo", include_in_schema=False)
        @application.get("/demo/", include_in_schema=False)
        async def frontend_build_required() -> HTMLResponse:
            return HTMLResponse(
                """
                <!doctype html>
                <html lang="en">
                  <head>
                    <meta charset="utf-8">
                    <title>Frontend build required</title>
                  </head>
                  <body>
                    <main>
                      <h1>Frontend build required</h1>
                      <p>Run <code>npm ci</code> and <code>npm run build</code>
                      from the <code>frontend</code> directory.</p>
                    </main>
                  </body>
                </html>
                """,
                status_code=503,
            )
    return application


app = create_demo_app()
