import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import accounts as accounts_mod  # noqa: E402
from accounts import FAIL, LINK_GONE, AccountError, Accounts, normalize_email  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def a(tmp_path, clock):
    return Accounts(tmp_path / "a.db", "pepper", clock=clock)


def make_account(a, email, username, code):
    token, kind, _ = a.request_link(email, "create")
    assert kind == "create"
    a.finish(token, username, code, code)


def err(fn, *args):
    with pytest.raises(AccountError) as e:
        fn(*args)
    return e.value.status, e.value.message


def test_create_then_sign_in(a):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    account_id, username = a.sign_in("jdoe", "1234", "ip")
    assert username == "jdoe" and isinstance(account_id, int)


def test_username_any_case(a):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    assert a.sign_in("JDoe", "1234", "ip")[1] == "jdoe"


def test_username_taken_any_case(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    token, _, _ = a.request_link("other@example.edu", "create")
    assert err(a.finish, token, "JDOE", "1111", "1111") == (400, "That username is taken.")


def test_username_and_code_rules(a):
    for i, bad in enumerate(["ab", "a" * 21, "a b", "a/b", "", None]):
        token, _, _ = a.request_link(f"u{i}@example.edu", "create")
        status, message = err(a.finish, token, bad, "1234", "1234")
        assert status == 400 and message.startswith("A username is 3 to 20")
    for i, bad in enumerate(["123", "12345", "12a4", "12 34", "", None]):
        token, _, _ = a.request_link(f"c{i}@example.edu", "create")
        assert err(a.finish, token, "okname", bad, bad) == (400, "The passcode is 4 digits.")
    token, _, _ = a.request_link("m@example.edu", "create")
    assert err(a.finish, token, "okname", "1234", "1235") == (400, "The two passcodes do not match.")


def test_create_with_existing_email_gives_reset(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    clock.t += 31
    assert a.request_link("JDoe@Example.edu", "create")[1:] == ("reset", "jdoe")


def test_forgot_without_account_gives_create(a):
    assert a.request_link("new@example.edu", "forgot")[1:] == ("create", None)


def test_open_link(a, clock):
    token, _, _ = a.request_link("jdoe@example.edu", "create")
    assert a.open_link(token) == {"kind": "create", "username": None}
    a.finish(token, "jdoe", "1234", "1234")
    clock.t += 31
    token, _, _ = a.request_link("jdoe@example.edu", "forgot")
    assert a.open_link(token) == {"kind": "reset", "username": "jdoe"}


def test_link_once_and_expiry(a, clock):
    token, _, _ = a.request_link("jdoe@example.edu", "create")
    a.finish(token, "jdoe", "1234", "1234")
    assert err(a.finish, token, "jdoe2", "1234", "1234") == (400, LINK_GONE)
    assert err(a.open_link, token) == (400, LINK_GONE)
    clock.t += 31
    token, _, _ = a.request_link("jdoe@example.edu", "forgot")
    clock.t += 1801
    assert err(a.open_link, token) == (400, LINK_GONE)
    assert err(a.finish, token, None, "1111", "1111") == (400, LINK_GONE)
    assert err(a.open_link, "nonsense") == (400, LINK_GONE)


def test_reset_username_keeps_id(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    before = a.sign_in("jdoe", "1234", "ip")[0]
    clock.t += 31
    token, kind, _ = a.request_link("jdoe@example.edu", "forgot")
    assert kind == "reset"
    assert a.finish(token, "jd2", None, None) == "jd2"
    assert a.sign_in("jd2", "1234", "ip")[0] == before
    assert err(a.sign_in, "jdoe", "1234", "ip") == (401, FAIL)


def test_reset_passcode(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    clock.t += 31
    token, _, _ = a.request_link("jdoe@example.edu", "forgot")
    a.finish(token, None, "9876", "9876")
    assert a.sign_in("jdoe", "9876", "ip")[1] == "jdoe"
    assert err(a.sign_in, "jdoe", "1234", "ip") == (401, FAIL)


def test_reset_with_nothing_to_change(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    clock.t += 31
    token, _, _ = a.request_link("jdoe@example.edu", "forgot")
    status, _ = err(a.finish, token, None, None, None)
    assert status == 400
    a.finish(token, None, "1111", "1111")   # the link still works after the refusal


def test_wrong_code_same_message_as_unknown_user(a):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    assert err(a.sign_in, "jdoe", "0000", "ip") == (401, FAIL)
    assert err(a.sign_in, "ghost", "0000", "ip") == (401, FAIL)
    assert err(a.sign_in, "", "", "ip") == (401, FAIL)


def test_lockout_schedule(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    for _ in range(5):
        err(a.sign_in, "jdoe", "0000", f"ip{_}")
    assert err(a.sign_in, "jdoe", "1234", "x") == (401, FAIL)
    clock.t += 899
    assert err(a.sign_in, "jdoe", "1234", "x") == (401, FAIL)
    clock.t += 2
    a.sign_in("jdoe", "1234", "x")
    # A correct passcode clears the count but the lock history doubles only
    # while failures keep coming; after a success the next lock is 15 minutes again.
    for _ in range(5):
        err(a.sign_in, "jdoe", "0000", f"ip{_}")
    clock.t += 901
    for _ in range(5):
        err(a.sign_in, "jdoe", "0000", f"jp{_}")   # a second lock in a row: 30 minutes
    clock.t += 1799
    assert err(a.sign_in, "jdoe", "1234", "x") == (401, FAIL)
    clock.t += 2
    a.sign_in("jdoe", "1234", "x")


def test_lockout_cap(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    for n in range(10):
        for i in range(5):
            err(a.sign_in, "jdoe", "0000", f"ip{n}-{i}")
        clock.t += min(900 * 2 ** n, 86400) + 1
    for i in range(5):
        err(a.sign_in, "jdoe", "0000", f"last{i}")
    clock.t += 86399
    assert err(a.sign_in, "jdoe", "1234", "x") == (401, FAIL)
    clock.t += 2
    a.sign_in("jdoe", "1234", "x")


def test_unknown_username_locks_too(a, clock):
    for i in range(5):
        err(a.sign_in, "ghost", "0000", f"ip{i}")
    token, _, _ = a.request_link("ghost@example.edu", "create")
    a.finish(token, "ghost", "1234", "1234")   # creating the account clears the lock
    assert a.sign_in("ghost", "1234", "x")[1] == "ghost"


def test_reset_link_unlocks(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    for i in range(5):
        err(a.sign_in, "jdoe", "0000", f"ip{i}")
    clock.t += 31
    token, _, _ = a.request_link("jdoe@example.edu", "forgot")
    a.finish(token, None, "1234", "1234")
    a.sign_in("jdoe", "1234", "x")


def test_ip_limit(a, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    for i in range(20):
        err(a.sign_in, f"user{i}", "0000", "1.2.3.4")
    assert err(a.sign_in, "jdoe", "1234", "1.2.3.4") == (401, FAIL)
    assert a.sign_in("jdoe", "1234", "5.6.7.8")[1] == "jdoe"
    clock.t += 3601
    assert a.sign_in("jdoe", "1234", "1.2.3.4")[1] == "jdoe"


def test_email_limits(a, clock):
    a.request_link("jdoe@example.edu", "create")
    status, _ = err(a.request_link, "jdoe@example.edu", "create")
    assert status == 429
    for bad in ["jdoe@gmail.com", "", "jdoe@example.edu.evil.com", "a b@example.edu"]:
        assert err(a.request_link, bad, "create") == (400, "Enter your @example.edu email address.")
    for _ in range(4):
        clock.t += 31
        a.request_link("jdoe@example.edu", "create")
    clock.t += 31
    assert err(a.request_link, "jdoe@example.edu", "create")[0] == 429


def test_email_global_limit(a, clock, monkeypatch):
    monkeypatch.setattr(accounts_mod, "GLOBAL_SENDS_PER_HOUR", 3)
    for i in range(3):
        a.request_link(f"u{i}@example.edu", "create")
    assert err(a.request_link, "u9@example.edu", "create")[0] == 429


def test_stored_hash_is_not_the_code(a, tmp_path, clock):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    rows = sqlite3.connect(tmp_path / "a.db").execute("SELECT salt, hash FROM account").fetchall()
    assert all(b"1234" not in bytes(v) for row in rows for v in row)
    other = Accounts(tmp_path / "a.db", "another pepper", clock=clock)
    assert err(other.sign_in, "jdoe", "1234", "ip") == (401, FAIL)


def test_active(a, tmp_path):
    make_account(a, "jdoe@example.edu", "jdoe", "1234")
    account_id = a.sign_in("jdoe", "1234", "ip")[0]
    assert a.active(account_id) is True
    assert a.active(999) is False
    db = sqlite3.connect(tmp_path / "a.db")
    db.execute("UPDATE account SET disabled=1")
    db.commit()
    assert a.active(account_id) is False
    assert err(a.sign_in, "jdoe", "1234", "ip2") == (401, FAIL)


def test_an_empty_email_domain_allows_any_address():
    assert normalize_email("JDoe@School.org", domain="") == "jdoe@school.org"
    for bad in ["jdoe@localhost", "", "a b@school.org"]:
        with pytest.raises(AccountError):
            normalize_email(bad, domain="")
