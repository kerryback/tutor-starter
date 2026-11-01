import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HOME = Path(__file__).parent.parent
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME.parent / "engine"))
from accounts import FAIL, LINK_GONE  # noqa: E402
from session_cookie import COOKIE  # noqa: E402

REPLY = "If that address can be used, we sent a link. Check your inbox and junk folder."


class Outbox:
    def __init__(self):
        self.sent = []

    def __call__(self, to, subject, body):
        self.sent.append((to, subject, body))

    def link(self):
        body = self.sent[-1][2]
        url = next(w for w in body.split() if "/link?t=" in w)
        return url.split("t=")[1].split("&")[0]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TUTORS_DEV", "1")
    monkeypatch.setenv("TUTORS_SECRET", "s")
    monkeypatch.setenv("TUTORS_HOME", "http://localhost:8060")
    spec = importlib.util.spec_from_file_location("home_app", HOME / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    box = Outbox()
    mod.send = box
    return mod, TestClient(mod.app), box, tmp_path


@pytest.fixture
def client(env):
    return env[1]


@pytest.fixture
def outbox(env):
    return env[2]


def create(client, outbox, email="jdoe@example.edu", username="jdoe", code="1234"):
    assert client.post("/api/email", json={"email": email, "kind": "create"}).json()["message"] == REPLY
    r = client.post("/api/finish", json={"token": outbox.link(), "username": username,
                                         "code": code, "code2": code})
    assert r.status_code == 200, r.text


def test_full_create_and_sign_in(client, outbox):
    create(client, outbox)
    r = client.post("/api/signin", json={"username": "jdoe", "code": "1234"})
    assert r.status_code == 200 and r.json() == {"go": "/"}
    assert COOKIE in r.cookies
    assert client.get("/api/me").json() == {"username": "jdoe"}


def test_email_link_goes_to_home_with_next(client, outbox):
    client.post("/api/email", json={"email": "jdoe@example.edu", "kind": "create",
                                    "next": "http://localhost:8010/"})
    body = outbox.sent[-1][2]
    assert "http://localhost:8060/link?t=" in body and "next=http%3A%2F%2Flocalhost%3A8010%2F" in body
    client.post("/api/email", json={"email": "j2@example.edu", "kind": "create", "next": "https://evil.com/"})
    assert "evil" not in outbox.sent[-1][2]


def test_email_reply_is_the_same_every_way(env):
    mod, client, outbox, _ = env
    create(client, outbox)
    replies = set()
    for i, (email, kind) in enumerate([("new@example.edu", "create"), ("jdoe@example.edu", "create"),
                                       ("new2@example.edu", "forgot"), ("jdoe@example.edu", "forgot")]):
        mod.accounts.sends.clear()
        replies.add(client.post("/api/email", json={"email": email, "kind": kind}).text)
    assert replies == {'{"message":"' + REPLY + '"}'}


def test_email_bad_address(client):
    r = client.post("/api/email", json={"email": "jdoe@gmail.com", "kind": "create"})
    assert r.status_code == 400 and r.json()["detail"] == "Enter your @example.edu email address."


def test_email_send_failure(env):
    mod, client, _, _ = env

    def broken(*a):
        raise OSError("down")
    mod.send = broken
    r = client.post("/api/email", json={"email": "jdoe@example.edu", "kind": "create"})
    assert r.status_code == 502
    mod.send = lambda *a: None
    assert client.post("/api/email", json={"email": "jdoe@example.edu", "kind": "create"}).status_code == 200


def test_signin_bad_shapes_are_plain_failures(client, outbox):
    create(client, outbox)
    for body in ({"username": "jdoe", "code": "12 34"}, {"username": "", "code": ""}, {},
                 {"username": "jdoe", "code": 4321}, {"username": None, "code": None}):
        r = client.post("/api/signin", json=body)
        assert r.status_code == 401 and r.json()["detail"] == FAIL, body


def test_link_used_twice(client, outbox):
    create(client, outbox)
    token = outbox.link()
    r = client.post("/api/finish", json={"token": token, "username": "x" * 5, "code": "1111", "code2": "1111"})
    assert r.status_code == 400 and r.json()["detail"] == LINK_GONE
    assert client.get("/api/link", params={"t": token}).status_code == 400


def test_link_info(client, outbox):
    client.post("/api/email", json={"email": "jdoe@example.edu", "kind": "create"})
    assert client.get("/api/link", params={"t": outbox.link()}).json() == {"kind": "create", "username": None}


def test_next_rejects_other_sites(client, outbox):
    create(client, outbox)
    r = client.post("/api/signin", json={"username": "jdoe", "code": "1234", "next": "https://evil.com"})
    assert r.json() == {"go": "/"}
    r = client.post("/api/signin", json={"username": "jdoe", "code": "1234", "next": "http://localhost:8010/"})
    assert r.json() == {"go": "http://localhost:8010/"}


def test_signout_clears_cookie(client, outbox):
    create(client, outbox)
    client.post("/api/signin", json={"username": "jdoe", "code": "1234"})
    client.post("/api/signout")
    assert client.get("/api/me").status_code == 401


def test_account_check_needs_secret(env):
    mod, client, outbox, tmp_path = env
    create(client, outbox)
    assert client.get("/api/account/1").status_code == 403
    assert client.get("/api/account/1", headers={"X-Tutors-Secret": "wrong"}).status_code == 403
    assert client.get("/api/account/1", headers={"X-Tutors-Secret": "s"}).json() == {"active": True}
    db = sqlite3.connect(tmp_path / "accounts.db")
    db.execute("UPDATE account SET disabled=1")
    db.commit()
    assert client.get("/api/account/1", headers={"X-Tutors-Secret": "s"}).json() == {"active": False}


def test_ip_from_cloudflare_header(env):
    mod, client, outbox, _ = env
    create(client, outbox)
    for i in range(20):
        client.post("/api/signin", json={"username": f"u{i}", "code": "0000"},
                    headers={"CF-Connecting-IP": "1.2.3.4"})
    blocked = client.post("/api/signin", json={"username": "jdoe", "code": "1234"},
                          headers={"CF-Connecting-IP": "1.2.3.4"})
    assert blocked.status_code == 401
    ok = client.post("/api/signin", json={"username": "jdoe", "code": "1234"},
                     headers={"CF-Connecting-IP": "5.6.7.8"})
    assert ok.status_code == 200


def test_root_serves_signin_or_landing(client, outbox):
    assert 'id="signin"' in client.get("/").text
    create(client, outbox)
    client.post("/api/signin", json={"username": "jdoe", "code": "1234"})
    assert 'id="landing"' in client.get("/").text


def test_other_pages(client):
    assert client.get("/email?kind=create").status_code == 200
    assert client.get("/link?t=x").status_code == 200


def test_tutors_list(client):
    names = [t["name"] for t in client.get("/api/tutors").json()]
    assert names == ["binomial"]


def test_pages_have_no_header(client, outbox):
    pages = [client.get(p).text for p in ("/", "/email?kind=create", "/link?t=x")]
    create(client, outbox)
    client.post("/api/signin", json={"username": "jdoe", "code": "1234"})
    pages.append(client.get("/").text)
    for page in pages:
        assert "<header" not in page
        assert "<title>" in page and 'name="viewport"' in page


def test_static_images_served(client):
    for name in ("tree.svg", "home.css", "home.js"):
        assert client.get(f"/static/{name}").status_code == 200, name


def test_ip_limit_is_logged(client, outbox, capsys):
    for i in range(21):
        client.post("/api/signin", json={"username": f"u{i}", "code": "0000"},
                    headers={"CF-Connecting-IP": "9.9.9.9"})
    assert "ip limit: 9.9.9.9" in capsys.readouterr().out


def test_ip_check_shows_headers_to_the_secret_holder(client):
    h = {"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "5.6.7.8, 10.0.0.1"}
    assert client.get("/api/ip-check", headers=h).status_code == 403
    r = client.get("/api/ip-check", headers={**h, "X-Tutors-Secret": "s"}).json()
    assert r["ip"] == "1.2.3.4"
    assert r["cf-connecting-ip"] == "1.2.3.4" and r["x-forwarded-for"] == "5.6.7.8, 10.0.0.1"
