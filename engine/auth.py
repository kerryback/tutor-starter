"""Who is signed in: the shared tutors_session cookie from tutors.example.edu.

Students sign in at tutors.example.edu (the home app in home/), which sets a
signed cookie on the whole tutors.example.edu domain; see session_cookie.py.
A tutor checks the signature itself, and asks the home app once an hour
whether the account is still active, so a removed account loses access within
an hour.  If the home app does not answer, the tutor keeps its last answer (or
trusts the cookie) and asks again in a minute.

With no TUTORS_SECRET and TUTORS_LOCAL=1 (scripts/run.sh), everyone is the
local test student; app.py will not start with neither.
"""

import threading
import time
from typing import NamedTuple

import httpx

import session_cookie


class Student(NamedTuple):
    key: str        # the record's key: acct-<id>, fixed for the account's life
    username: str   # shown on the page; it can change


LOCAL = Student("local", "local")


class SessionCheck:
    def __init__(self, secret, fetch_active, clock=time.time, every=3600, retry=60):
        self.secret = secret
        self.fetch_active = fetch_active
        self.clock = clock
        self.every = every
        self.retry = retry
        self.lock = threading.Lock()
        self.checked = {}   # account id -> (time of the next check, active)

    def student(self, token):
        """The Student for this cookie, or None if it is not a good sign-in."""
        if not self.secret:
            return LOCAL
        who = session_cookie.read(self.secret, token, now=self.clock())
        if not who:
            return None
        account_id, username = who
        now = self.clock()
        with self.lock:
            seen = self.checked.get(account_id)
        if not seen or now >= seen[0]:
            active = self.fetch_active(account_id)
            if active is None:
                # The home app did not answer: keep the last answer (a new
                # account is trusted) and ask again in a minute, so a hung home
                # app does not slow every request.
                seen = (now + self.retry, seen[1] if seen else True)
            else:
                seen = (now + self.every, active)
            with self.lock:
                self.checked[account_id] = seen
        return Student(f"acct-{account_id}", username) if seen[1] else None


def home_fetcher(home, secret, timeout=3.0):
    """fetch_active(id) -> True or False from the home app, None if it does not answer."""
    def fetch_active(account_id):
        try:
            r = httpx.get(f"{home}/api/account/{account_id}", headers={"X-Tutors-Secret": secret},
                          timeout=timeout)
            if r.status_code != 200:
                return None
            return bool(r.json()["active"])
        except Exception:
            return None
    return fetch_active
