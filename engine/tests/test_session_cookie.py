import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from session_cookie import MAX_AGE, cookie_args, make, read, safe_next  # noqa: E402


def test_round_trip():
    t = make("s", 42, "jdoe", now=1000)
    assert read("s", t, now=1001) == (42, "jdoe")


def test_rejects_wrong_secret_tamper_expiry_and_junk():
    t = make("s", 42, "jdoe", now=1000)
    assert read("other", t, now=1001) is None
    payload, sig = t.split(".")
    forged = make("s", 1, "admin", now=1000).split(".")[0] + "." + sig
    assert read("s", forged, now=1001) is None
    assert read("s", t, now=1000 + MAX_AGE + 1) is None
    for junk in (None, "", "x", "a.b.c", "!!!.???", "e30.AAAA"):
        assert read("s", junk) is None


def test_next_rejects_other_sites():
    for bad in ("https://tutors.example.edu.evil.com/", "//evil.com", "javascript:alert(1)",
                "https://evil.com", "http://binomial.tutors.example.edu/", None, "",
                "https://evil.com\\@tutors.example.edu/", "https://user@evil.com/"):
        assert safe_next(bad, dev=False) is None
    assert safe_next("http://localhost:8010/", dev=False) is None


def test_next_accepts_tutors():
    for ok in ("https://tutors.example.edu/", "https://binomial.tutors.example.edu/"):
        assert safe_next(ok, dev=False) == ok
    assert safe_next("http://localhost:8010/", dev=True) == "http://localhost:8010/"


def test_cookie_args():
    assert cookie_args(False, "tutors.example.edu")["domain"] == "tutors.example.edu"
    assert cookie_args(False, "tutors.example.edu")["secure"] is True
    assert "domain" not in cookie_args(True, "tutors.example.edu")
    assert cookie_args(True, None)["secure"] is False
