"""`make prod-smoke` (M10): checks a running deployment from outside, stdlib only.

Always: /api/healthz, the issuer file, and /admin answering 200 without a redirect (it is a
static shell; the sign-in guard runs in the browser against /api/session).

Sign-in, the part that broke on http://localhost (browsers refused __Host-session over http
and every guarded page bounced to /login), with one of:
  SMOKE_COOKIE="name=value"            a session cookie copied from the browser, or
  SMOKE_EMAIL=… SMOKE_CODE=123456      a sign-in code from the inbox (uses it up).
With a code, the Set-Cookie header is checked against the browser rules for the base URL's
scheme. Either way /api/session must then say authenticated. Values are never printed.
"""

import json
import os
import sys
import urllib.request
from http.cookies import SimpleCookie

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000").rstrip("/")
https = base.startswith("https://")
failed = False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


opener = urllib.request.build_opener(NoRedirect)


def call(path: str, *, cookie: str = "", body: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    headers = {"Cookie": cookie} if cookie else {}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers)
    try:
        return opener.open(request, timeout=20)
    except urllib.error.HTTPError as exc:
        return exc


def check(ok: bool, what: str) -> None:
    global failed
    failed |= not ok
    print(f"{'ok  ' if ok else 'FAIL'} {what}")


r = call("/api/healthz")
check(r.status == 200 and json.load(r).get("ok") is True, "GET /api/healthz")
r = call("/.well-known/ai-passport-issuer.json")
issuer = json.load(r) if r.status == 200 else {}
check(bool(issuer.get("contract_address")), f"issuer file (chain {issuer.get('chain_id')})")
r = call("/admin")
check(r.status == 200 and not r.headers.get("Location"), f"GET /admin → {r.status}, no redirect")

cookie = os.environ.get("SMOKE_COOKIE", "")
if os.environ.get("SMOKE_EMAIL") and os.environ.get("SMOKE_CODE"):
    r = call("/auth/verify-code",
             body={"email": os.environ["SMOKE_EMAIL"], "code": os.environ["SMOKE_CODE"]})  # fmt: skip
    check(r.status == 200, f"POST /auth/verify-code → {r.status}")
    for header in r.headers.get_all("Set-Cookie") or []:
        jar = SimpleCookie(header)
        for name, morsel in jar.items():
            if name == "csrf_token":
                continue
            secure = bool(morsel["secure"])
            prefixed = name.startswith(("__Host-", "__Secure-"))
            localhost = base.split("//", 1)[1].split(":")[0].split("/")[0] in ("localhost", "127.0.0.1")
            check(not (prefixed and not https),
                  f"session cookie {name}: name is accepted over {base.split(':')[0]}")  # fmt: skip
            check(not secure or https or localhost,
                  f"session cookie {name}: Secure is accepted at {base}")  # fmt: skip
            check(morsel["httponly"] is True, f"session cookie {name}: HttpOnly")
            cookie = f"{name}={morsel.value}"
if cookie:
    r = call("/api/session", cookie=cookie)
    info = json.load(r) if r.status == 200 else {}
    check(info.get("authenticated") is True,
          f"GET /api/session with the cookie → authenticated ({info.get('role')})")  # fmt: skip
    r = call("/admin", cookie=cookie)
    check(r.status == 200 and not r.headers.get("Location"), "GET /admin with the cookie → 200")
else:
    print("skip sign-in checks (set SMOKE_COOKIE, or SMOKE_EMAIL and SMOKE_CODE)")

sys.exit(1 if failed else 0)
