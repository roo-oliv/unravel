"""FastAPI entrypoint."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from unravel.api.routers import auth, edits, github, viewed_hunks, walkthroughs


def create_app() -> FastAPI:
    app = FastAPI(
        title="Unravel API",
        version="0.0.1-phase1",
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

    # Authlib stashes the OAuth state CSRF token in request.session, so we
    # need Starlette's signed-cookie session for the OAuth handshake itself
    # — this is separate from our DB-backed user session.
    session_secret = os.environ.get("SESSION_SECRET", "dev-only-change-me")
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        session_cookie="unravel_oauth_state",
        max_age=600,  # OAuth dance has ~5min; 10min covers slow auth providers
        same_site="lax",
        https_only=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(auth.router, tags=["auth"])
    app.include_router(walkthroughs.router, tags=["walkthroughs"])
    app.include_router(edits.router, tags=["edits"])
    app.include_router(github.router, tags=["github"])
    app.include_router(viewed_hunks.router, tags=["viewed-hunks"])

    return app


app = create_app()
