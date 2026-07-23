import os

os.environ["TEST_MODE"] = "true"

from fastapi.testclient import TestClient

import main


def test_everything_is_open_when_shared_secret_is_unset(monkeypatch):
    monkeypatch.delenv("SHARED_SECRET", raising=False)
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/config").status_code == 200


def test_api_request_without_the_cookie_is_rejected(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET", "correct-password")
    with TestClient(main.app) as client:
        response = client.get("/api/config")
        assert response.status_code == 401


def test_static_page_without_the_cookie_gets_a_login_form_not_the_app(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET", "correct-password")
    with TestClient(main.app) as client:
        response = client.get("/")
        assert response.status_code == 401
        assert "password" in response.text.lower()
        assert "Plan a trip" not in response.text


def test_wrong_password_is_rejected_and_sets_no_cookie(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET", "correct-password")
    with TestClient(main.app) as client:
        response = client.post("/login", data={"password": "wrong"})
        assert response.status_code == 401
        assert "shared_secret" not in response.cookies


def test_correct_password_sets_a_cookie_that_then_unlocks_everything(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET", "correct-password")
    with TestClient(main.app) as client:
        login_response = client.post("/login", data={"password": "correct-password"})
        assert login_response.history  # followed the redirect back to "/"
        assert login_response.status_code == 200

        # The same client (same cookie jar) doesn't get re-prompted.
        assert client.get("/").status_code == 200
        assert client.get("/api/config").status_code == 200


def test_a_fresh_browser_with_no_cookie_is_still_blocked_after_someone_else_logged_in(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET", "correct-password")
    with TestClient(main.app) as authorized_client:
        authorized_client.post("/login", data={"password": "correct-password"})
        assert authorized_client.get("/").status_code == 200

    with TestClient(main.app) as fresh_client:
        assert fresh_client.get("/").status_code == 401
