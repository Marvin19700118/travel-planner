"""Shared-password gate. Opt-in via the SHARED_SECRET env var, matching the
existing TEST_MODE/GOOGLE_MAPS_API_KEY/GEMINI_API_KEY pattern: unset means
open access (so local dev and the existing test suite need no changes),
set means every request -- API and static files alike -- needs a matching
cookie first.

A correct password sets an HttpOnly, Secure cookie (not read by JS, not
something app.js has to remember to attach to every fetch/EventSource call)
that the browser then sends automatically on every subsequent same-origin
request, including the SSE stream and static asset loads. The cookie's
value *is* the shared password, not a derived session token, so it needs
the same protection a credential would: Secure (never sent over plain
HTTP) and compared with hmac.compare_digest (constant-time) rather than
`==`. `Secure` cookies are still sent to `localhost`/`127.0.0.1` over HTTP
by every major browser (treated as a potentially-trustworthy origin), so
this doesn't complicate local dev.
"""

from __future__ import annotations

import hmac
import os

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response


# Named exactly "__session" on purpose (live-corrected 2026-07-24, first
# real deploy): Firebase Hosting's CDN strips every cookie except this one
# specially-named cookie from GET/HEAD requests before forwarding to
# Cloud Run -- confirmed live (a valid cookie named "shared_secret" reached
# Cloud Run fine on POST, which bypasses the CDN cache entirely since POST
# is never cacheable, but was silently stripped on GET, which goes through
# the cache layer). See https://firebase.google.com/docs/hosting/manage-cache.
COOKIE_NAME = "__session"
LOGIN_PATH = "/login"
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365

_LOGIN_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#ff8c66">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Travel Planner">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon-192.png">
<link rel="apple-touch-icon" href="/icon-192.png">
<title>Travel Planner &mdash; Sign in</title>
<style>
  body {{ font-family: -apple-system, "Noto Sans TC", sans-serif; background: #fffaf3; color: #3a2e2c;
          display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0;
          padding: 16px; box-sizing: border-box; }}
  form {{ background: #fff; border-radius: 16px; padding: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.08);
          width: 100%; max-width: 280px; box-sizing: border-box; }}
  input {{ width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #e5ddd4; border-radius: 10px;
           box-sizing: border-box; min-height: 44px; font-size: 1rem; }}
  button {{ width: 100%; padding: 10px; border: none; border-radius: 999px; background: #ff8c66; color: #fff;
            font-weight: 600; cursor: pointer; font-size: 1rem; min-height: 44px; }}
  p.error {{ color: #d64545; margin-top: 0; }}
</style></head>
<body>
  <form method="post" action="{login_path}">
    <h2>Enter password</h2>
    {error}
    <input type="password" name="password" placeholder="Password" autofocus required />
    <button type="submit">Continue</button>
  </form>
</body></html>
"""


def _shared_secret() -> str | None:
    """None means "not set at all" -> the gate is off (opt-in design). A
    present-but-empty value is kept distinct and deliberately NOT treated
    as "off": a misconfigured deploy that ends up with SHARED_SECRET="" (a
    broken env var substitution, say) should fail closed, not silently open
    the whole app to the public. handle_login's `if secret and ...` check
    means an empty secret can never be logged into, so this fails closed
    without any extra branching."""
    return os.environ.get("SHARED_SECRET")


def is_authorized(request: Request) -> bool:
    secret = _shared_secret()
    if secret is None:
        return True
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return False
    return hmac.compare_digest(cookie, secret)


def render_login_page(*, error: bool = False) -> HTMLResponse:
    error_html = '<p class="error">Wrong password.</p>' if error else ""
    return HTMLResponse(_LOGIN_PAGE.format(login_path=LOGIN_PATH, error=error_html), status_code=401)


async def handle_login(request: Request) -> Response:
    form = await request.form()
    secret = _shared_secret()
    submitted = form.get("password")
    if secret and isinstance(submitted, str) and hmac.compare_digest(submitted, secret):
        response: Response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            secret,
            httponly=True,
            samesite="lax",
            secure=True,
            max_age=_COOKIE_MAX_AGE_SECONDS,
        )
        return response
    return render_login_page(error=True)
