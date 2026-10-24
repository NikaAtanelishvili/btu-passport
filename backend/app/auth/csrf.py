"""Double-submit CSRF protection (BE-13).

At sign-in a readable `csrf_token` cookie is set to the session's token; the web client
echoes it in `X-CSRF-Token`. A cross-site page can make the browser send cookies but can't
read them, so it can't produce the header.
"""

import hmac

from fastapi import Request

from app.auth.deps import CurrentUser
from app.errors import AppError

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _protected(path: str) -> bool:
    if path.startswith("/api/verify/"):
        return False  # public, no session
    return path.startswith("/api/") or path == "/auth/logout"


def csrf_protect(request: Request, principal: CurrentUser) -> None:
    """App-wide dependency. Without a live session there is nothing to forge; the route's
    guard decides (usually 401)."""
    if request.method not in UNSAFE_METHODS or not _protected(request.url.path):
        return
    if principal is None:
        return
    sent = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(sent.encode(), principal.session.csrf_token.encode()):
        raise AppError(
            "csrf_failed", "Your session check failed. Reload the page and try again.", 403
        )
