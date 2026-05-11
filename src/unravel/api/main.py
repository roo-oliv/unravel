"""FastAPI entrypoint."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from unravel.api.routers import edits, walkthroughs


def create_app() -> FastAPI:
    app = FastAPI(
        title="Unravel API",
        version="0.0.0-phase0",
        docs_url="/docs",
        redoc_url=None,
    )

    # Phase 0: permissive CORS for localhost dev. Tighten in Phase 1.
    cors_origins = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS", "http://localhost:3000"
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(walkthroughs.router, tags=["walkthroughs"])
    app.include_router(edits.router, tags=["edits"])

    return app


app = create_app()
