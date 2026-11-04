"""Web front end for a tutor (the one in TUTOR_DIR).

    uvicorn app:app --port 8000

Students sign in at tutors.example.edu, which sets a cookie this tutor
checks (see auth.py).  Each student's file is keyed by their account id; no
tutor sees an email address.
"""

import asyncio
from html import escape
import json
import re
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import settings  # noqa: E402
import tutor_config as cfg  # noqa: E402
from auth import SessionCheck, home_fetcher  # noqa: E402
import session_cookie as sc  # noqa: E402
import intros  # noqa: E402
from tutor import SESSION_START, Store, Tutor, student_slug  # noqa: E402

HERE = Path(__file__).parent
log = logging.getLogger("tutor")
DATA_DIR = os.environ.get("DATA_DIR", cfg.DIR / "data")   # students' records and speech models; a volume on Railway
store = Store(DATA_DIR)
# Sign-in: with TUTORS_LOCAL=1 (scripts/run.sh), everyone is the local test
# student.  Anywhere else the tutor will not start without TUTORS_SECRET.
SECRET = os.environ.get("TUTORS_SECRET") or None
if not SECRET and os.environ.get("TUTORS_LOCAL") != "1":
    raise RuntimeError("Set TUTORS_SECRET (or TUTORS_LOCAL=1 to run as a local test student).")
HOME = os.environ.get("TUTORS_HOME", "https://tutors.example.edu").rstrip("/")
DEV = os.environ.get("TUTORS_DEV") == "1"
COOKIE_DOMAIN = os.environ.get("TUTORS_COOKIE_DOMAIN")
check = SessionCheck(SECRET, home_fetcher(HOME, SECRET) if SECRET else None)
live = {}   # slug -> in-memory student while a turn runs (say sentences exist before the save)
tutor = Tutor(store, voice=settings.VOICE_ENABLED)
speech = None
if settings.VOICE_ENABLED:
    from speech import BadAudio, ClipTooLong, Speech  # noqa: E402
    speech = Speech(DATA_DIR)
    speech.start()
app = FastAPI(title=cfg.TITLE)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.middleware("http")
async def _revalidate(request, call_next):
    # The page and its scripts change between versions; make browsers check for
    # a new copy (a quick 304 when nothing changed) instead of running a stale one.
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-cache"
    return response


class Chat(BaseModel):
    message: str = ""
    start: bool = False
    module: int | None = None   # the student picked this module from the menu


async def _student(request: Request):
    # In a thread: the hourly check with the home app is a network call.
    who = await asyncio.to_thread(check.student, request.cookies.get(sc.COOKIE))
    if not who:
        raise HTTPException(401, "Please sign in.")
    return who


def _view(student):
    conv = student.get("conversation") or {}
    return {"name": student["name"], "display": conv.get("display", []),
            "fresh": not conv.get("messages")}


async def _open(who, fresh=False):
    async with store.lock(store.load(who.key)["slug"]):
        student = store.load(who.key, who.username)
        tutor.ensure_conversation(student, fresh=fresh)
        store.save(student)
        return _view(student)


@app.get("/")
async def index(request: Request):
    # Not signed in: to tutors.example.edu, which sends the student back here.
    if not await asyncio.to_thread(check.student, request.cookies.get(sc.COOKIE)):
        # Live tutors are always https, whatever the proxy reports.
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme) if DEV else "https"
        here = f"{scheme}://{request.headers.get('host', request.url.netloc)}/"
        return RedirectResponse(f"{HOME}/?next={quote(here, safe='')}", status_code=303)
    # The page names the tutor: {{TITLE}}, {{SUBTITLE}} and {{NAME}} come from tutor.toml.
    html = (HERE / "static" / "index.html").read_text(encoding="utf-8")
    for key in ("TITLE", "SUBTITLE", "NAME"):
        html = html.replace("{{" + key + "}}", escape(getattr(cfg, key)))
    return HTMLResponse(html.replace("{{HOME}}", escape(HOME)))


@app.post("/api/logout")
def logout(response: Response):
    # The cookie belongs to the whole domain, so this signs out of every tutor.
    response.delete_cookie(sc.COOKIE, **sc.cookie_args(DEV, COOKIE_DOMAIN))
    return {"go": HOME}


@app.get("/api/me")
async def me(request: Request):
    return await _open(await _student(request))


@app.post("/api/new")
async def new_session(request: Request):
    return await _open(await _student(request), fresh=True)


@app.post("/api/chat")
async def chat(req: Chat, request: Request):
    who = await _student(request)
    if not req.start and req.module is None and not req.message.strip():
        raise HTTPException(400, "Empty message.")
    if len(req.message) > 8000:
        raise HTTPException(400, "Message too long.")
    lock = store.lock(store.load(who.key)["slug"])
    if lock.locked():
        raise HTTPException(409, "The tutor is still answering your last message.")

    async def events():
        async with lock:
            s = store.load(who.key, who.username)
            conv = tutor.ensure_conversation(s)
            if req.start and conv["messages"]:
                yield _sse({"type": "done"})
                return
            text = SESSION_START if req.start else req.message.strip()
            live[s["slug"]] = s
            try:
                if req.module is not None:
                    run = tutor.module_turn(s, req.module)
                elif req.start:
                    run = tutor.start_turn(s)
                else:
                    run = tutor.turn(s, text)
                async for ev in run:
                    yield _sse(ev)
            finally:
                live.pop(s["slug"], None)
            yield _sse({"type": "done"})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(obj):
    return f"data: {json.dumps(obj)}\n\n"


# --- voice -------------------------------------------------------------------

MAX_LISTEN_BYTES = 2_000_000
LISTENS_PER_MINUTE = 20
_listens = defaultdict(deque)


@app.get("/api/config")
def config():
    out = {"voice": speech is not None, "voice_ready": bool(speech and speech.ready),
           "idle_seconds": settings.VOICE_IDLE_SECONDS}
    if speech is not None:
        out["modules"] = MODULES
    return out


def _modules():
    """[{"n": 1, "title": "One period: ..."}] for the module menu."""
    return [{"n": m["n"], "title": m["title"]} for m in intros.MODULES.values()]


MODULES = _modules()


async def _read_limited(request):
    """The request body, refused with 413 as soon as it passes MAX_LISTEN_BYTES."""
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_LISTEN_BYTES:
        raise HTTPException(413, "Recording too large.")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_LISTEN_BYTES:
            raise HTTPException(413, "Recording too large.")
    return bytes(body)


def _wav(data):
    return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})


def _need_ready():
    if not speech.ready:
        raise HTTPException(503, "Voice is not ready." + (f" ({speech.error})" if speech.error else ""))


if settings.VOICE_ENABLED:
    # /api/say/idle must come before /api/say/{n}.
    @app.get("/api/say/idle")
    async def say_idle(request: Request):
        await _student(request)
        _need_ready()
        return _wav(await speech.idle_wav())

    @app.get("/api/say/{n}")
    async def say(n: int, request: Request):
        who = await _student(request)
        _need_ready()
        student = live.get(student_slug(who.key)) or store.load(who.key, who.username)
        spoken = (student.get("conversation") or {}).get("spoken") or []
        if not 0 <= n < len(spoken):
            raise HTTPException(404, "No such sentence.")
        return _wav(await speech.synth(spoken[n]))

    @app.post("/api/listen")
    async def listen(request: Request):
        who = await _student(request)
        body = await _read_limited(request)
        _need_ready()
        now = time.monotonic()
        recent = _listens[who.key]
        while recent and now - recent[0] > 60:
            recent.popleft()
        if len(recent) >= LISTENS_PER_MINUTE:
            raise HTTPException(429, "Too many recordings. Wait a minute.")
        recent.append(now)
        try:
            return {"text": (await speech.transcribe(body)).strip()}
        except ClipTooLong as e:
            raise HTTPException(413, str(e))
        except BadAudio:
            raise HTTPException(400, "Could not read that recording.")
        except Exception:
            log.exception("transcription failed")
            raise HTTPException(500, "Transcription failed.")
