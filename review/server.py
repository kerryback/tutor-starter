"""The review page: a local app where the user reads and edits a tutor's plan,
intros and explained code.  It writes only review.json and
content/module-intros.md.

    python -m review.server <tutor folder> [--port 8040]
"""

import argparse
import importlib.util
import os
import shutil
import subprocess
import tomllib
import sys
import threading
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from review import intros_file, plan
from review.plan import PlanError

HERE = Path(__file__).parent
ROOT = HERE.parent
ENGINE = ROOT / "engine"
# One plot at a time: _topic reloads the tutor's modules, and two requests at once
# (a module with two plots) would remove each other's half-loaded imports.
_PLOT_LOCK = threading.Lock()
STALE = "The files changed since you opened this page. Reload to see the new version."

if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
import speech_text  # noqa: E402  (the engine's: how the tutor turns text into speech)
from intro_notes import ARITHMETIC_NOTE, MIC_NOTE  # noqa: E402  (what the app adds to the Introduction)


def make_speech(tutor_dir: Path):
    """The engine's voice, loading in the background.  The engine reads
    TUTOR_DIR when speech is first imported."""
    os.environ["TUTOR_DIR"] = str(tutor_dir)
    import speech
    s = speech.Speech(tutor_dir / "data")
    s.start()
    return s


def _topic(tutor_dir: Path):
    """The tutor's topic.py, freshly loaded, with the tutor's own modules it imports (its
    calculations and plots) loaded fresh too, so a preview always shows the code on disk."""
    for name, m in list(sys.modules.items()):
        if Path(getattr(m, "__file__", None) or "/").resolve().parent == tutor_dir:
            del sys.modules[name]
    spec = importlib.util.spec_from_file_location(f"review_topic_{tutor_dir.name}", tutor_dir / "topic.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(tutor_dir))
    write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tutor_dir))
        sys.dont_write_bytecode = write_bytecode
    return module


def create_app(tutor_dir: Path, root: Path = ROOT) -> FastAPI:
    tutor_dir, root = Path(tutor_dir).resolve(), Path(root)
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    voice = {}

    @app.exception_handler(PlanError)
    def _plan_error(request, e):
        return JSONResponse({"error": str(e)}, status_code=422)

    @app.exception_handler(HTTPException)
    def _http_error(request, e):
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    def built():
        if not (tutor_dir / "tutor.toml").exists():
            raise HTTPException(409, "Listen, plots and tests work once the tutor is built.")

    @app.get("/")
    def index():
        return FileResponse(HERE / "static" / "review.html", headers={"Cache-Control": "no-cache"})

    @app.get("/engine/plot-sliders.js")
    def plot_sliders():
        # The whiteboard's own slider code, so a plot's Preview behaves as on the board.
        return FileResponse(ROOT / "engine" / "static" / "plot-sliders.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/api/data")
    def data():
        try:
            return {**plan.page_data(tutor_dir, root), "intro_added": [ARITHMETIC_NOTE, MIC_NOTE]}
        except PlanError:
            raise
        except Exception as e:  # noqa: BLE001 - a shape load() does not check: still one sentence
            raise PlanError(f"review.json has a problem Claude must fix: {type(e).__name__}: {e}.")

    @app.put("/api/save")
    def save(body: dict = Body(...)):
        if body.get("version") != plan.version(tutor_dir):
            raise HTTPException(409, STALE)
        new = plan.apply_edits(plan.load(tutor_dir), body.get("edits") or {})
        intros_path = tutor_dir / "content" / "module-intros.md"
        if body.get("intros") and intros_path.exists():
            intros_file.write(intros_path, body["intros"])
        plan.save(tutor_dir, new)
        return {**plan.page_data(tutor_dir, root), "intro_added": [ARITHMETIC_NOTE, MIC_NOTE]}

    @app.post("/api/listen")
    async def listen(body: dict = Body(...)):
        built()
        if "speech" not in voice:
            voice["speech"] = make_speech(tutor_dir)
        s = voice["speech"]
        if not s.ready:
            raise HTTPException(503, "The voice could not load: " + s.error if s.error
                                else "The voice is still loading. Try again in a minute.")
        say = tomllib.loads((tutor_dir / "tutor.toml").read_text(encoding="utf-8")).get("say", {})
        wav = await s.synth(speech_text.spoken_form(str(body.get("text", "")), say))
        return Response(wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.post("/api/plot")
    def plot(body: dict = Body(...)):
        built()
        module = next((m for m in plan.load(tutor_dir)["modules"] if m["n"] == body.get("module")), None)
        try:
            args = module["plots"][int(body.get("plot"))]["preview"]
        except (TypeError, IndexError, ValueError):
            raise HTTPException(404, "There is no such plot in review.json.")
        if not args:
            raise HTTPException(404, "This plot has no preview settings yet.")
        try:
            with _PLOT_LOCK:
                _, payload = _topic(tutor_dir).make_plot(dict(args))
        except Exception as e:  # noqa: BLE001 - the tutor's ToolError, or a bug in topic.py: say it
            raise HTTPException(400, f"The plot failed: {e}")
        return payload["plot"]

    @app.post("/api/tests")
    def tests():
        built()
        # Through bash, so it runs on Windows too.  shutil.which finds Git Bash's bash
        # before C:\\Windows\\System32\\bash.exe (WSL), which a bare "bash" would start.
        bash = shutil.which("bash") or "bash"
        r = subprocess.run([bash, str(root / "scripts" / "test.sh"), tutor_dir.name], cwd=root,
                           capture_output=True, text=True)
        lines = (r.stdout + r.stderr).strip().splitlines()
        return {"ok": r.returncode == 0, "summary": "\n".join(lines[-15:])}

    return app


def main():
    ap = argparse.ArgumentParser(description="The review page for one tutor.")
    ap.add_argument("tutor_dir", type=Path)
    ap.add_argument("--port", type=int, default=8040)
    args = ap.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.tutor_dir), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
