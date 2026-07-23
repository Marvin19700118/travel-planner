"""Shared-password gate. Opt-in via the SHARED_SECRET env var, matching the
existing TEST_MODE/GOOGLE_MAPS_API_KEY/GEMINI_API_KEY pattern: unset means
open access (so local dev and the existing test suite need no changes),
set means every request -- API and static files alike -- needs a matching
cookie first.

A correct password sets an HttpOnly cookie (not read by JS, not something
app.js has to remember to attach to every fetch/EventSource call) that the
browser then sends automatically on every subsequent same-origin request,
including the SSE stream and static asset loads.
"""

from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

COOKIE_NAME = "shared_secret"
LOGIN_PATH = "/login"
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365

_LOGIN_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Travel Planner &mdash; Sign in</title>
<style>
  body {{ font-family: -apple-system, "Noto Sans TC", sans-serif; background: #fffaf3; color: #3a2e2c;
          display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
  form {{ background: #fff; border-radius: 16px; padding: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.08); width: 280px; }}
  input {{ width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #e5ddd4; border-radius: 10px; box-sizing: border-box; }}
  button {{ width: 100%; padding: 10px; border: none; border-radius: 999px; background: #ff8c66; color: #fff;
            font-weight: 600; cursor: pointer; font-size: 1rem; }}
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
    return os.environ.get("SHARED_SECRET") or None


def is_authorized(request: Request) -> bool:
    secret = _shared_secret()
    if secret is None:
        return True
    return request.cookies.get(COOKIE_NAME) == secret


def render_login_page(*, error: bool = False) -> HTMLResponse:
    error_html = '<p class="error">Wrong password.</p>' if error else ""
    return HTMLResponse(_LOGIN_PAGE.format(login_path=LOGIN_PATH, error=error_html), status_code=401)


async def handle_login(request: Request) -> Response:
    form = await request.form()
    secret = _shared_secret()
    if secret and form.get("password") == secret:
        response: Response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            COOKIE_NAME, secret, httponly=True, samesite="lax", max_age=_COOKIE_MAX_AGE_SECONDS
        )
        return response
    return render_login_page(error=True)
