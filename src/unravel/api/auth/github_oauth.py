"""GitHub OAuth client (user-level access).

Wraps Authlib's StarletteOAuth2App. The OAuth App is registered once per
deployment (env: ``GITHUB_OAUTH_CLIENT_ID`` + ``GITHUB_OAUTH_CLIENT_SECRET``);
the callback URL must match what's configured on github.com — typically
``http://localhost:8000/auth/callback`` for dev.

Authlib stores the state CSRF token in ``request.session``, which means the
app **must** install ``starlette.middleware.sessions.SessionMiddleware`` (see
``main.create_app``).
"""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com/"

# Scopes: ``repo`` is required to write comments to private PRs. Public-only
# instances can drop it back to ``public_repo`` by overriding the env var.
DEFAULT_SCOPE = "read:user user:email repo"


class OAuthNotConfiguredError(RuntimeError):
    """Raised when /auth/github is hit without OAuth credentials configured."""


_oauth: OAuth | None = None


def get_oauth() -> OAuth:
    """Return a lazily-constructed Authlib registry.

    Lazy on purpose: we don't want the FastAPI app to refuse to boot when an
    operator hasn't configured OAuth yet (Phase 0 dev-auth path should still
    work). The registration only fails when ``/auth/github`` is actually hit.
    """
    global _oauth
    if _oauth is not None:
        return _oauth

    client_id = os.environ.get("GITHUB_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "").strip()
    if not (client_id and client_secret):
        raise OAuthNotConfiguredError(
            "GITHUB_OAUTH_CLIENT_ID / GITHUB_OAUTH_CLIENT_SECRET are not set. "
            "Register an OAuth App at https://github.com/settings/applications/new "
            "and fill them into your .env."
        )

    scope = os.environ.get("GITHUB_OAUTH_SCOPE", DEFAULT_SCOPE)

    oauth = OAuth()
    oauth.register(
        name="github",
        client_id=client_id,
        client_secret=client_secret,
        authorize_url=GITHUB_AUTHORIZE_URL,
        access_token_url=GITHUB_TOKEN_URL,
        api_base_url=GITHUB_API_BASE,
        client_kwargs={
            "scope": scope,
            # GitHub returns ``application/x-www-form-urlencoded`` by default;
            # asking for JSON keeps Authlib's parsing path happy.
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    _oauth = oauth
    return oauth


def github_client() -> StarletteOAuth2App:
    """Convenience accessor for the ``github`` registration."""
    return get_oauth().create_client("github")  # type: ignore[return-value]


__all__ = [
    "DEFAULT_SCOPE",
    "OAuthNotConfiguredError",
    "get_oauth",
    "github_client",
]
