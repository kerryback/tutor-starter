"""The sign-in cookie shared by tutors.example.edu and every tutor.

The home app sets it on the domain tutors.example.edu when a student signs
in, so the browser sends it to every tutor too.  It holds the account id, the
username and the expiry, signed with HMAC-SHA256 and TUTORS_SECRET; a tutor
checks the signature itself.  Standard library only: the home app's image
copies this one file.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlsplit

COOKIE = "tutors_session"
MAX_AGE = 120 * 86400
DOMAIN = os.environ.get("TUTORS_COOKIE_DOMAIN", "tutors.example.edu")


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret, payload):
    return _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def make(secret, account_id, username, now=None):
    now = time.time() if now is None else now
    payload = _b64(json.dumps({"id": account_id, "u": username, "exp": int(now + MAX_AGE)},
                              separators=(",", ":")).encode())
    return payload + "." + _sign(secret, payload)


def read(secret, token, now=None):
    """(account id, username) for a good, unexpired token; None for anything else."""
    try:
        payload, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(secret, payload)):
            return None
        data = json.loads(_unb64(payload))
        if data["exp"] < (time.time() if now is None else now):
            return None
        return int(data["id"]), str(data["u"])
    except Exception:
        return None


def safe_next(url, dev):
    """The address to go to after sign-in, if it is one of the tutors; else None."""
    if not url:
        return None
    try:
        p = urlsplit(url)
        host = p.hostname or ""
    except ValueError:
        return None
    if p.username is not None or p.password is not None or "\\" in url:
        return None
    if p.scheme == "https" and (host == DOMAIN or host.endswith("." + DOMAIN)):
        return url
    if dev and p.scheme == "http" and host == "localhost":
        return url
    return None


def cookie_args(dev, domain):
    """Keyword arguments for Response.set_cookie and delete_cookie."""
    args = {"httponly": True, "samesite": "lax", "path": "/", "secure": not dev}
    if domain and not dev:
        args["domain"] = domain
    return args
