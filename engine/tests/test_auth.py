"""A tutor's sign-in: the shared tutors_session cookie from tutors.example.edu,
checked here, with an hourly check that the account is still active."""

import importlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from auth import LOCAL, SessionCheck, Student, home_fetcher  # noqa: E402
from session_cookie import COOKIE, MAX_AGE, make  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class Fetcher:
    def __init__(self, answer=True):
        self.answer = answer
        self.calls = []

    def __call__(self, account_id):
        self.calls.append(account_id)
        return self.answer


@pytest.fixture
def clock():
    return Clock()


def test_no_secret_is_local_student():
    assert SessionCheck(None, Fetcher()).student(None) == LOCAL
    assert SessionCheck("", Fetcher()).student("anything") == LOCAL


def test_valid_cookie(clock):
    check = SessionCheck("s", Fetcher(), clock=clock)
    assert check.student(make("s", 7, "jdoe", now=clock.t)) == Student("acct-7", "jdoe")


def test_bad_cookies(clock):
    check = SessionCheck("s", Fetcher(), clock=clock)
    assert check.student(None) is None
    assert check.student("junk") is None
    assert check.student(make("other", 7, "jdoe", now=clock.t)) is None
    old = make("s", 7, "jdoe", now=clock.t)
    clock.t += MAX_AGE + 1
    assert check.student(old) is None


def test_checks_home_once_an_hour(clock):
    fetch = Fetcher()
    check = SessionCheck("s", fetch, clock=clock)
    token = make("s", 7, "jdoe", now=clock.t)
    check.student(token)
    check.student(token)
    assert fetch.calls == [7]
    clock.t += 3601
    check.student(token)
    assert fetch.calls == [7, 7]


def test_removed_account_signed_out(clock):
    fetch = Fetcher(False)
    check = SessionCheck("s", fetch, clock=clock)
    token = make("s", 7, "jdoe", now=clock.t)
    assert check.student(token) is None
    assert check.student(token) is None
    assert fetch.calls == [7]          # the answer is remembered for the hour


def test_home_down_trusts_cookie(clock):
    fetch = Fetcher(None)
    check = SessionCheck("s", fetch, clock=clock)
    token = make("s", 7, "jdoe", now=clock.t)
    assert check.student(token) == Student("acct-7", "jdoe")
    assert check.student(token) == Student("acct-7", "jdoe")
    assert fetch.calls == [7]          # asks again in a minute, not on every request


def test_home_fetcher_unreachable_is_none():
    assert home_fetcher("http://127.0.0.1:9", "s", timeout=0.5)(7) is None


# --- the routes --------------------------------------------------------------

def _app(tmp_path, monkeypatch, secret):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY") or "test")
    monkeypatch.setenv("TUTORS_HOME", "https://tutors.example.edu")
    monkeypatch.setenv("TUTORS_COOKIE_DOMAIN", "tutors.example.edu")
    monkeypatch.delenv("TUTORS_DEV", raising=False)
    if secret:
        monkeypatch.setenv("TUTORS_SECRET", secret)
        monkeypatch.delenv("TUTORS_LOCAL", raising=False)
    else:
        monkeypatch.delenv("TUTORS_SECRET", raising=False)
        monkeypatch.setenv("TUTORS_LOCAL", "1")
    import app as app_mod
    app_mod = importlib.reload(app_mod)
    app_mod.check.fetch_active = lambda account_id: True
    return app_mod, TestClient(app_mod.app, base_url="https://binomial.tutors.example.edu")


@pytest.fixture
def client(tmp_path, monkeypatch):
    return _app(tmp_path, monkeypatch, "s")[1]


@pytest.fixture
def local_client(tmp_path, monkeypatch):
    return _app(tmp_path, monkeypatch, None)[1]


def test_routes_need_a_session(client):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/new").status_code == 401
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401


def test_bad_cookie_redirects(client):
    for token in (None, "junk", make("other", 7, "jdoe"), make("s", 7, "jdoe", now=0)):
        client.cookies.clear()
        if token:
            client.cookies.set(COOKIE, token)
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 303
        go = urlsplit(r.headers["location"])
        assert (go.scheme, go.netloc, go.path) == ("https", "tutors.example.edu", "/")
        assert parse_qs(go.query)["next"] == ["https://binomial.tutors.example.edu/"]
        assert client.get("/api/me").status_code == 401


def test_signed_in(client):
    client.cookies.set(COOKIE, make("s", 7, "jdoe"))
    assert client.get("/", follow_redirects=False).status_code == 200
    assert client.get("/api/me").json() == {"name": "jdoe", "display": [], "fresh": True}


def test_record_keyed_by_account_not_name(client, tmp_path):
    client.cookies.set(COOKIE, make("s", 7, "jdoe"))
    client.get("/api/me")
    client.cookies.set(COOKIE, make("s", 7, "jd2"))
    assert client.get("/api/me").json()["name"] == "jd2"
    files = [p.name for p in tmp_path.glob("*.json")]
    assert files == ["acct-7.json"]
    assert json.loads((tmp_path / "acct-7.json").read_text())["name"] == "jd2"
    assert "@" not in (tmp_path / "acct-7.json").read_text()


def test_removed_account_is_signed_out(tmp_path, monkeypatch):
    app_mod, client = _app(tmp_path, monkeypatch, "s")
    app_mod.check.fetch_active = lambda account_id: False
    client.cookies.set(COOKIE, make("s", 7, "jdoe"))
    assert client.get("/api/me").status_code == 401


def test_logout_clears_shared_cookie(client):
    client.cookies.set(COOKIE, make("s", 7, "jdoe"))
    r = client.post("/api/logout")
    assert r.json() == {"go": "https://tutors.example.edu"}
    set_cookie = r.headers["set-cookie"].lower()
    assert set_cookie.startswith(COOKIE + "=") and "max-age=0" in set_cookie
    assert "domain=tutors.example.edu" in set_cookie


def test_old_sign_in_routes_gone(client):
    assert client.post("/api/auth/start", json={"email": "jdoe@example.edu"}).status_code in (404, 405)
    assert client.post("/api/auth/verify", json={"email": "jdoe@example.edu", "code": "1"}).status_code in (404, 405)


def test_no_secret_signs_in_the_local_student(local_client, tmp_path):
    assert local_client.get("/", follow_redirects=False).status_code == 200
    assert local_client.get("/api/me").json()["name"] == "local"
    assert [p.name for p in tmp_path.glob("*.json")] == ["local.json"]


def test_tutor_page_has_no_header_or_signin(local_client):
    page = local_client.get("/").text
    assert "<header" not in page and 'id="signin"' not in page
    assert 'id="who"' in page and "All tutors" in page
    assert "https://tutors.example.edu" in page


# --- fixes from the final review ---------------------------------------------

def test_home_down_keeps_last_answer_and_waits_a_minute(clock):
    fetch = Fetcher(True)
    check = SessionCheck("s", fetch, clock=clock)
    token = make("s", 7, "jdoe", now=clock.t)
    check.student(token)
    fetch.answer = None
    clock.t += 3601
    assert check.student(token) == Student("acct-7", "jdoe")   # home down: last answer stands
    assert check.student(token) == Student("acct-7", "jdoe")
    assert fetch.calls == [7, 7]                               # and no re-ask for a minute
    clock.t += 61
    check.student(token)
    assert fetch.calls == [7, 7, 7]


def test_home_down_keeps_a_removal(clock):
    fetch = Fetcher(False)
    check = SessionCheck("s", fetch, clock=clock)
    token = make("s", 7, "jdoe", now=clock.t)
    assert check.student(token) is None
    fetch.answer = None
    clock.t += 3601
    assert check.student(token) is None


def test_tutor_refuses_to_start_without_secret_or_local(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.delenv("TUTORS_SECRET", raising=False)
    monkeypatch.delenv("TUTORS_LOCAL", raising=False)
    import app as app_mod
    with pytest.raises(RuntimeError, match="TUTORS_SECRET"):
        importlib.reload(app_mod)


def test_redirect_back_is_https_without_forwarded_proto(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    app_mod, _ = _app(tmp_path, monkeypatch, "s")
    client = TestClient(app_mod.app, base_url="http://binomial.tutors.example.edu")
    r = client.get("/", follow_redirects=False)
    assert parse_qs(urlsplit(r.headers["location"]).query)["next"] == ["https://binomial.tutors.example.edu/"]
