"""tutors.example.edu: the accounts, the sign-in pages and the landing page.

    uvicorn app:app --port 8020

Signing in sets the cookie tutors_session on the domain tutors.example.edu,
so every tutor gets it too (see engine/session_cookie.py).  The tutors ask
GET /api/account/<id> once an hour whether an account is still active.
"""

import hmac
import os
import sys
import tomllib
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).parent
for p in (HERE, HERE.parent / "engine"):   # in the image, session_cookie.py sits beside this file
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import mail  # noqa: E402
import session_cookie as sc  # noqa: E402
from accounts import AccountError, Accounts  # noqa: E402

DEV = os.environ.get("TUTORS_DEV") == "1"
SECRET = os.environ.get("TUTORS_SECRET") or ("dev" if DEV else "")
PEPPER = os.environ.get("TUTORS_PEPPER") or ("dev" if DEV else "")
if not SECRET or not PEPPER:
    raise RuntimeError("Set TUTORS_SECRET and TUTORS_PEPPER (or TUTORS_DEV=1 for local work).")
HOME = os.environ.get("TUTORS_HOME", "https://tutors.example.edu").rstrip("/")
COOKIE_DOMAIN = os.environ.get("TUTORS_COOKIE_DOMAIN")
DATA_DIR = Path(os.environ.get("HOME_DATA_DIR", HERE / "data"))
REPLY = "If that address can be used, we sent a link. Check your inbox and junk folder."
TUTORS = tomllib.loads((HERE / "tutors.toml").read_text())["tutor"]
for _t in TUTORS:
    _t.setdefault("url", f"https://{_t['name']}.{COOKIE_DOMAIN or sc.DOMAIN}/")

accounts = Accounts(DATA_DIR / "accounts.db", PEPPER)
send = mail.make_sender()
app = FastAPI(title="Tutors")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.middleware("http")
async def _revalidate(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/static/") or request.url.path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(AccountError)
def _account_error(request, e):
    return JSONResponse({"detail": e.message}, status_code=e.status)


class SignIn(BaseModel):
    username: str | int | None = None
    code: str | int | None = None
    next: str | None = None


class EmailReq(BaseModel):
    email: str | None = None
    kind: str = "create"
    next: str | None = None


class Finish(BaseModel):
    token: str = ""
    username: str | None = None
    code: str | None = None
    code2: str | None = None


def _signed_in(request):
    return sc.read(SECRET, request.cookies.get(sc.COOKIE))


def _ip(request):
    # Koyeb sits behind Cloudflare, which puts the visitor's address in
    # CF-Connecting-IP; the first X-Forwarded-For entry is whatever the client sent.
    forwarded = request.headers.get("x-forwarded-for", "")
    return (request.headers.get("cf-connecting-ip")
            or (forwarded.split(",")[-1].strip() if forwarded else "")
            or (request.client.host if request.client else "?"))


def _page(name):
    return FileResponse(HERE / "static" / name, media_type="text/html")


@app.get("/")
def index(request: Request):
    return _page("landing.html" if _signed_in(request) else "signin.html")


@app.get("/email")
def email_page():
    return _page("email.html")


@app.get("/link")
def link_page():
    return _page("link.html")


@app.post("/api/signin")
def signin(req: SignIn, request: Request, response: Response):
    # A plain def: scrypt runs in a thread, not on the event loop.
    account_id, username = accounts.sign_in(str(req.username or ""), str(req.code or ""), _ip(request))
    response.set_cookie(sc.COOKIE, sc.make(SECRET, account_id, username), max_age=sc.MAX_AGE,
                        **sc.cookie_args(DEV, COOKIE_DOMAIN))
    return {"go": sc.safe_next(req.next, DEV) or "/"}


@app.post("/api/email")
def email(req: EmailReq):
    token, kind, username = accounts.request_link(req.email, req.kind)
    url = f"{HOME}/link?t={token}"
    nxt = sc.safe_next(req.next, DEV)
    if nxt:
        url += "&next=" + quote(nxt, safe="")
    try:
        send(req.email.strip().lower(), *mail.link_email(kind, url, username))
    except Exception as e:
        accounts.forget_send(req.email)
        print(f"home: could not send to {req.email}: {type(e).__name__}: {e}", flush=True)
        raise HTTPException(502, "Could not send the email. Try again in a minute.")
    return {"message": REPLY}


@app.get("/api/link")
def link_info(t: str = ""):
    return accounts.open_link(t)


@app.post("/api/finish")
def finish(req: Finish):
    return {"username": accounts.finish(req.token, req.username, req.code, req.code2)}


@app.post("/api/signout")
def signout(response: Response):
    response.delete_cookie(sc.COOKIE, **sc.cookie_args(DEV, COOKIE_DOMAIN))
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    who = _signed_in(request)
    if not who:
        raise HTTPException(401, "Please sign in.")
    return {"username": who[1]}


@app.get("/api/tutors")
def tutors():
    return TUTORS


def _need_secret(request):
    if not hmac.compare_digest(request.headers.get("x-tutors-secret", ""), SECRET):
        raise HTTPException(403, "Forbidden.")


@app.get("/api/account/{account_id}")
def account(account_id: int, request: Request):
    _need_secret(request)
    return {"active": accounts.active(account_id)}


@app.get("/api/ip-check")
def ip_check(request: Request):
    """What address the sign-in limit sees, and the headers it comes from:
    for checking the proxy's headers on a deployed app."""
    _need_secret(request)
    return {"ip": _ip(request), "cf-connecting-ip": request.headers.get("cf-connecting-ip"),
            "x-forwarded-for": request.headers.get("x-forwarded-for"),
            "client": request.client.host if request.client else None}
