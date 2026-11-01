"""The accounts: one per email, with a username and a 4-digit passcode.

One SQLite file holds three tables: account, link (the emailed create and
reset links, stored only as hashes) and failure (wrong passcodes per username,
for the lockout; unknown usernames count too, so a lock never shows that a
username exists).  Failures by IP address are kept in memory.

The app runs as one instance, so one lock around the database is enough.
"""

import os
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

LINK_TTL = 30 * 60           # seconds an emailed link works
RESEND_GAP = 30              # seconds between emails to one address
SENDS_PER_HOUR = 5           # emails per address per hour
GLOBAL_SENDS_PER_HOUR = 300  # emails per hour across all addresses
FAILS_BEFORE_LOCK = 5
LOCK_FIRST = 15 * 60         # the first lock; each later one in a row doubles
LOCK_MAX = 86400
IP_FAILS_PER_HOUR = 20

FAIL = ("That username and passcode do not match. After several wrong tries a username "
        "is locked for a while; use Forgot username or passcode to unlock it now.")
LINK_GONE = "This link has expired or was already used. Ask for a new one."
BAD_USERNAME = "A username is 3 to 20 letters, digits, dots, dashes or underscores."
BAD_CODE = "The passcode is 4 digits."

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE COLLATE NOCASE,
  email TEXT UNIQUE, salt BLOB, hash BLOB, created REAL, last_signin REAL,
  disabled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS link (
  token_hash TEXT PRIMARY KEY, email TEXT, kind TEXT, expires REAL, used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS failure (
  username TEXT PRIMARY KEY COLLATE NOCASE, fails INTEGER, locks INTEGER, locked_until REAL);
"""


class AccountError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# Only addresses at this domain can make accounts.  Empty allows any address.
EMAIL_DOMAIN = os.environ.get("TUTORS_EMAIL_DOMAIN", "example.edu")


def normalize_email(email, domain=None):
    domain = EMAIL_DOMAIN if domain is None else domain
    email = (email or "").strip().lower()
    local, _, dom = email.rpartition("@")
    bad_domain = dom != domain if domain else "." not in dom
    if bad_domain or not re.fullmatch(r"[a-z0-9._+-]{1,64}", local):
        where = f"@{domain} " if domain else ""
        raise AccountError(400, f"Enter your {where}email address.")
    return email


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, path, pepper, clock=time.time):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.pepper = pepper.encode()
        self.clock = clock
        self.lock = threading.Lock()
        self.sends = {}       # email -> [send times]
        self.all_sends = []
        self.ip_fails = {}    # ip -> [failure times]

    def _hash(self, code, salt):
        return hashlib.scrypt(code.encode(), salt=salt + self.pepper, n=2**14, r=8, p=1, dklen=32)

    def _account_by_email(self, email):
        return self.db.execute("SELECT id, username FROM account WHERE email=?", (email,)).fetchone()

    # --- links ---------------------------------------------------------------

    def request_link(self, email, wanted):
        """A new link for this address: (token, kind, username).  The kind is
        "reset" when the address has an account and "create" otherwise,
        whichever page the student came from."""
        email = normalize_email(email)
        now = self.clock()
        with self.lock:
            hour_ago = now - 3600
            mine = [t for t in self.sends.get(email, []) if t > hour_ago]
            self.all_sends = [t for t in self.all_sends if t > hour_ago]
            if mine and now - mine[-1] < RESEND_GAP:
                raise AccountError(429, "A link was just sent. Wait a few seconds before asking again.")
            if len(mine) >= SENDS_PER_HOUR:
                raise AccountError(429, "Too many emails for this address. Try again in an hour.")
            if len(self.all_sends) >= GLOBAL_SENDS_PER_HOUR:
                raise AccountError(429, "Sign-in is busy. Try again in a few minutes.")
            self.sends[email] = mine + [now]
            self.all_sends.append(now)
            row = self._account_by_email(email)
            kind = "reset" if row else "create"
            token = secrets.token_urlsafe(32)
            self.db.execute("INSERT INTO link (token_hash, email, kind, expires) VALUES (?,?,?,?)",
                            (_token_hash(token), email, kind, now + LINK_TTL))
            self.db.commit()
        return token, kind, (row[1] if row else None)

    def forget_send(self, email):
        """A failed send does not count against the address's limits."""
        email = normalize_email(email)
        with self.lock:
            if self.sends.get(email):
                t = self.sends[email].pop()
                if t in self.all_sends:
                    self.all_sends.remove(t)

    def _link(self, token):
        row = self.db.execute("SELECT email, kind, expires, used FROM link WHERE token_hash=?",
                              (_token_hash(token or ""),)).fetchone()
        if not row or row[3] or row[2] < self.clock():
            raise AccountError(400, LINK_GONE)
        return row[0], row[1]

    def open_link(self, token):
        with self.lock:
            email, kind = self._link(token)
            row = self._account_by_email(email)
        if kind == "reset" and row:
            return {"kind": "reset", "username": row[1]}
        return {"kind": "create", "username": None}

    def finish(self, token, username, code, code2):
        """Use a link: create the account, or change its username, passcode or
        both.  Returns the username."""
        with self.lock:
            email, _ = self._link(token)
            row = self._account_by_email(email)
            if username is not None or row is None:
                username = (username or "").strip()
                if not re.fullmatch(r"[A-Za-z0-9._-]{3,20}", username):
                    raise AccountError(400, BAD_USERNAME)
                taken = self.db.execute("SELECT id FROM account WHERE username=?", (username,)).fetchone()
                if taken and (row is None or taken[0] != row[0]):
                    raise AccountError(400, "That username is taken.")
            if code is not None or row is None:
                if not re.fullmatch(r"\d{4}", code or ""):
                    raise AccountError(400, BAD_CODE)
                if code != code2:
                    raise AccountError(400, "The two passcodes do not match.")
            if row is not None and username is None and code is None:
                raise AccountError(400, "Type a new username or a new passcode.")
            now = self.clock()
            if row is None:
                salt = secrets.token_bytes(16)
                self.db.execute("INSERT INTO account (username, email, salt, hash, created) "
                                "VALUES (?,?,?,?,?)", (username, email, salt, self._hash(code, salt), now))
            else:
                if username is not None:
                    self.db.execute("UPDATE account SET username=? WHERE id=?", (username, row[0]))
                if code is not None:
                    salt = secrets.token_bytes(16)
                    self.db.execute("UPDATE account SET salt=?, hash=? WHERE id=?",
                                    (salt, self._hash(code, salt), row[0]))
            final = username if username is not None else row[1]
            self.db.execute("UPDATE link SET used=1 WHERE token_hash=?", (_token_hash(token),))
            self.db.execute("DELETE FROM failure WHERE username IN (?, ?)",
                            (final, row[1] if row else final))
            self.db.commit()
        return final

    # --- signing in ------------------------------------------------------------

    def sign_in(self, username, code, ip):
        """(account id, username) for a right username and passcode; otherwise
        AccountError(401, FAIL), whatever was wrong."""
        username = (username or "").strip()
        code = code or ""
        now = self.clock()
        with self.lock:
            fails = [t for t in self.ip_fails.get(ip, []) if t > now - 3600]
            self.ip_fails[ip] = fails
            if len(fails) >= IP_FAILS_PER_HOUR:
                print(f"accounts: ip limit: {ip} has {len(fails)} failed sign-ins in the last hour", flush=True)
                raise AccountError(401, FAIL)
            f = self.db.execute("SELECT fails, locks, locked_until FROM failure WHERE username=?",
                                (username,)).fetchone()
            if f and f[2] and f[2] > now:
                raise AccountError(401, FAIL)
            row = self.db.execute("SELECT id, username, salt, hash, disabled FROM account "
                                  "WHERE username=?", (username,)).fetchone()
            # One scrypt whatever the username, so the time taken tells nothing.
            got = self._hash(code, row[2] if row else b"\0" * 16)
            if row and not row[4] and hmac.compare_digest(got, row[3]):
                self.db.execute("DELETE FROM failure WHERE username=?", (username,))
                self.db.execute("UPDATE account SET last_signin=? WHERE id=?", (now, row[0]))
                self.db.commit()
                return row[0], row[1]
            fails.append(now)
            n, locks = (f[0], f[1]) if f else (0, 0)
            n += 1
            until = None
            if n >= FAILS_BEFORE_LOCK:
                until = now + min(LOCK_FIRST * 2 ** locks, LOCK_MAX)
                n, locks = 0, locks + 1
            self.db.execute("INSERT OR REPLACE INTO failure (username, fails, locks, locked_until) "
                            "VALUES (?,?,?,?)", (username, n, locks, until))
            self.db.commit()
        raise AccountError(401, FAIL)

    def active(self, account_id):
        with self.lock:
            row = self.db.execute("SELECT disabled FROM account WHERE id=?", (account_id,)).fetchone()
        return bool(row) and not row[0]
