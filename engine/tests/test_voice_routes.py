import importlib
import io
import os
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from session_cookie import COOKIE, make  # noqa: E402
from tutor import student_slug  # noqa: E402


def _wav(seconds=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\0\0" * 16000 * seconds)
    return buf.getvalue()


WAV_1S = _wav()


class FakeSpeech:
    def __init__(self):
        self.ready, self.error, self.next_text = True, None, "hello tutor"

    async def synth(self, text):
        return b"RIFF" + text.encode()

    async def transcribe(self, wav):
        return self.next_text

    async def idle_wav(self):
        return b"RIFFidle"


def _load(tmp_path, monkeypatch, voice):
    from fastapi.testclient import TestClient
    import speech as speech_mod
    monkeypatch.setattr(speech_mod.Speech, "start", lambda self: None)   # never load real models
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY") or "test")
    if voice:
        monkeypatch.setenv("VOICE_ENABLED", "1")
    else:
        monkeypatch.delenv("VOICE_ENABLED", raising=False)
    monkeypatch.setenv("TUTORS_SECRET", "s")
    import settings
    importlib.reload(settings)
    import app as app_mod
    app_mod = importlib.reload(app_mod)
    app_mod.check.fetch_active = lambda account_id: True
    fake = FakeSpeech()
    if voice:
        app_mod.speech = fake
    return app_mod, TestClient(app_mod.app), None, fake


@pytest.fixture
def text_client(tmp_path, monkeypatch):
    yield _load(tmp_path, monkeypatch, False)[1]
    monkeypatch.undo()
    import settings
    importlib.reload(settings)


@pytest.fixture
def env(tmp_path, monkeypatch):
    yield _load(tmp_path, monkeypatch, True)
    monkeypatch.undo()
    import settings
    importlib.reload(settings)


@pytest.fixture
def voice_client(env):
    return env[1]


@pytest.fixture
def fake_speech(env):
    return env[3]


@pytest.fixture
def signed_in(env):
    app_mod, client, _, _ = env

    def sign_in(spoken=None):
        client.cookies.set(COOKIE, make("s", 7, "jdoe"))
        client.get("/api/me")
        if spoken is not None:
            s = app_mod.store.load("acct-7")
            s["conversation"]["spoken"] = list(spoken)
            s["conversation"]["messages"] = [{"role": "user", "content": "hi"}]   # so /api/new starts afresh
            app_mod.store.save(s)
    return sign_in


def test_config_text_version(text_client):
    assert text_client.get("/api/config").json() == {"voice": False, "voice_ready": False, "idle_seconds": 45}
    assert text_client.get("/api/say/0").status_code == 404
    assert text_client.post("/api/listen", content=b"x").status_code == 404


def test_say_needs_session_and_valid_index(voice_client, signed_in):
    assert voice_client.get("/api/say/0").status_code == 401
    signed_in(spoken=["Hello there."])
    r = voice_client.get("/api/say/0")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert voice_client.get("/api/say/1").status_code == 404
    assert voice_client.get("/api/say/-1").status_code in (404, 422)


def test_idle_and_listen_need_session(voice_client):
    assert voice_client.get("/api/say/idle").status_code == 401
    assert voice_client.post("/api/listen", content=WAV_1S).status_code == 401


def test_idle_returns_wav(voice_client, signed_in):
    signed_in()
    r = voice_client.get("/api/say/idle")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"


def test_new_session_invalidates_old_numbers(voice_client, signed_in):
    signed_in(spoken=["Hello there."])
    voice_client.post("/api/new")
    assert voice_client.get("/api/say/0").status_code == 404


def test_listen_limits_and_empty_text(voice_client, signed_in, fake_speech):
    signed_in()
    assert voice_client.post("/api/listen", content=b"x" * 2_000_001).status_code == 413
    fake_speech.next_text = "   "
    assert voice_client.post("/api/listen", content=WAV_1S).json() == {"text": ""}
    for _ in range(19):
        voice_client.post("/api/listen", content=WAV_1S)
    assert voice_client.post("/api/listen", content=WAV_1S).status_code == 429


def test_listen_returns_text(voice_client, signed_in, fake_speech):
    signed_in()
    fake_speech.next_text = "what is delta"
    assert voice_client.post("/api/listen", content=WAV_1S).json() == {"text": "what is delta"}


def test_models_failed_reports_not_ready(voice_client, fake_speech, signed_in):
    signed_in()
    fake_speech.ready, fake_speech.error = False, "espeak-ng not found"
    assert voice_client.get("/api/config").json()["voice_ready"] is False
    assert voice_client.get("/api/say/idle").status_code == 503


def test_idle_line_is_fixed_copy_and_uses_the_synth_pool(tmp_path, monkeypatch):
    import asyncio
    import settings
    import speech as speech_mod
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "")
    assert speech_mod.IDLE_TEXT == "Press the button when you are ready to continue."
    assert speech_mod.KOKORO_MODEL == "kokoro-v1.0.onnx"
    sp = speech_mod.Speech(tmp_path)
    calls = []
    sp._synth = lambda text: calls.append(text) or b"RIFFx"
    assert asyncio.run(sp.idle_wav()) == b"RIFFx"
    assert asyncio.run(sp.idle_wav()) == b"RIFFx"      # second call reads the cache
    assert calls == ["Press the button when you are ready to continue."]
    assert (tmp_path / "voice" / f"idle-af_heart-{settings.KOKORO_SPEED:g}.wav").exists()


def test_idle_cache_is_keyed_on_the_voice(tmp_path, monkeypatch):
    import asyncio
    import settings
    import speech as speech_mod
    sp = speech_mod.Speech(tmp_path)
    calls = []
    sp._synth = lambda text: calls.append(settings.KOKORO_VOICE) or f"RIFF{settings.KOKORO_VOICE}".encode()
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(settings, "KOKORO_VOICE", "af_heart")
    assert asyncio.run(sp.idle_wav()) == b"RIFFaf_heart"
    monkeypatch.setattr(settings, "KOKORO_VOICE", "bf_emma")
    assert asyncio.run(sp.idle_wav()) == b"RIFFbf_emma"      # a new voice is synthesized afresh
    assert calls == ["af_heart", "bf_emma"]
    assert (tmp_path / "voice" / f"idle-bf_emma-{settings.KOKORO_SPEED:g}.wav").exists()


def test_elevenlabs_idle_cache_is_keyed_on_its_voice(tmp_path, monkeypatch):
    import asyncio
    import settings
    import speech as speech_mod
    monkeypatch.setattr(settings, "VOICE", "elevenlabs")
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "k")
    sp = speech_mod.Speech(tmp_path)
    sp._synth = lambda text: b"RIFFx"
    assert asyncio.run(sp.idle_wav()) == b"RIFFx"
    name = f"idle-eleven-{settings.ELEVENLABS_VOICE}-{settings.ELEVENLABS_MODEL}.wav"
    assert (tmp_path / "voice" / name).exists()


def test_elevenlabs_synth_asks_for_pcm_and_returns_wav(tmp_path, monkeypatch):
    import io
    import wave
    import httpx
    import settings
    import speech as speech_mod
    monkeypatch.setattr(settings, "VOICE", "elevenlabs")
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "k")
    sent = {}

    def post(url, **kw):
        sent.update(url=url, **kw)
        return httpx.Response(200, content=b"\0\0" * 2400, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    data = speech_mod.Speech(tmp_path)._synth("Hello.")
    assert sent["url"].endswith("/J9NvviOEdVm6E7Hwdpdj")
    assert sent["params"] == {"output_format": "pcm_24000"}
    assert sent["headers"] == {"xi-api-key": "k"}
    assert sent["json"] == {"text": "Hello.", "model_id": "eleven_flash_v2_5"}
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getframerate(), w.getnframes()) == (24000, 2400)


def test_bad_idle_seconds_falls_back_to_45(monkeypatch):
    import settings
    monkeypatch.setenv("VOICE_IDLE_SECONDS", "forty")
    try:
        assert importlib.reload(settings).VOICE_IDLE_SECONDS == 45
        monkeypatch.setenv("VOICE_IDLE_SECONDS", "20")
        assert importlib.reload(settings).VOICE_IDLE_SECONDS == 20
    finally:
        monkeypatch.undo()
        importlib.reload(settings)


# --- fix round 1 ---------------------------------------------------------------

def test_say_reads_the_live_turn_before_it_is_saved(env, signed_in):
    app_mod, client, _, _ = env
    signed_in(spoken=[])                                  # nothing on disk yet
    slug = student_slug("acct-7")
    app_mod.live[slug] = {"conversation": {"spoken": ["Mid-turn sentence."]}}
    assert client.get("/api/say/0").status_code == 200
    app_mod.live.clear()
    assert client.get("/api/say/0").status_code == 404    # falls back to disk


def test_chat_registers_and_clears_the_live_student(env, signed_in):
    app_mod, client, _, _ = env
    signed_in()
    slug = student_slug("acct-7")
    seen = []

    class FakeTutor:
        voice = True

        def ensure_conversation(self, s, fresh=False):
            return s.setdefault("conversation", {"messages": [], "display": [], "spoken": []})

        async def turn(self, s, text, hidden=False, sheet=None):
            seen.append(app_mod.live.get(slug) is s)
            yield {"type": "text", "text": "x"}

    app_mod.tutor = FakeTutor()
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 200 and seen == [True]
    assert slug not in app_mod.live


def test_chat_clears_live_even_when_the_turn_fails(env, signed_in):
    app_mod, client, _, _ = env
    signed_in()

    class FakeTutor:
        def ensure_conversation(self, s, fresh=False):
            return s.setdefault("conversation", {"messages": [], "display": []})

        async def turn(self, s, text, hidden=False, sheet=None):
            raise RuntimeError("boom")
            yield

    app_mod.tutor = FakeTutor()
    with pytest.raises(Exception):
        client.post("/api/chat", json={"message": "hi"})
    assert app_mod.live == {}


def test_listen_stops_reading_a_chunked_body_at_the_limit(env):
    import asyncio
    app_mod = env[0]
    read = []

    class Req:
        headers = {}

        async def stream(self):
            for _ in range(100):
                read.append(1)
                yield b"x" * 500_000

    with pytest.raises(Exception) as e:
        asyncio.run(app_mod._read_limited(Req()))
    assert e.value.status_code == 413 and len(read) <= 5


def test_chunked_upload_without_length_is_refused(voice_client, signed_in):
    signed_in()
    chunks = (b"x" * 500_000 for _ in range(6))
    assert voice_client.post("/api/listen", content=chunks).status_code == 413


def test_listen_error_mapping(env, signed_in):
    import speech as speech_mod
    app_mod, client, _, fake = env
    signed_in()

    def raising(exc):
        async def t(wav):
            raise exc
        return t

    fake.transcribe = raising(speech_mod.ClipTooLong("too long"))
    assert client.post("/api/listen", content=WAV_1S).status_code == 413
    fake.transcribe = raising(speech_mod.BadAudio("bad"))
    assert client.post("/api/listen", content=WAV_1S).status_code == 400
    fake.transcribe = raising(RuntimeError("whisper died"))
    assert client.post("/api/listen", content=WAV_1S).status_code == 500


class FakeWhisper:
    def __init__(self):
        self.got = None

    def transcribe(self, audio, **kw):
        self.got = (audio, kw)
        from types import SimpleNamespace
        return [SimpleNamespace(text=" hello "), SimpleNamespace(text="world ")], None


def test_transcribe_rejects_a_61_second_clip(tmp_path):
    import speech as speech_mod
    sp = speech_mod.Speech(tmp_path)
    sp._whisper = FakeWhisper()
    with pytest.raises(speech_mod.ClipTooLong):
        sp._transcribe(_wav(61))
    assert sp._whisper.got is None


def test_transcribe_passes_16k_mono_array(tmp_path):
    import numpy as np
    import soundfile
    import speech as speech_mod
    buf = io.BytesIO()
    soundfile.write(buf, np.zeros((24000, 2), dtype="float32"), 24000, format="WAV", subtype="PCM_16")
    sp = speech_mod.Speech(tmp_path)
    sp._whisper = FakeWhisper()
    assert sp._transcribe(buf.getvalue()) == "hello world"
    audio, kw = sp._whisper.got
    assert audio.ndim == 1 and audio.dtype == np.float32 and len(audio) == 16000
    assert kw["language"] == "en" and kw["vad_filter"] is False


def test_transcribe_garbage_is_bad_audio(tmp_path):
    import speech as speech_mod
    sp = speech_mod.Speech(tmp_path)
    sp._whisper = FakeWhisper()
    with pytest.raises(speech_mod.BadAudio):
        sp._transcribe(b"not audio at all")


class NoisyWhisper:
    """Whisper output on background noise: a hallucinated line among real speech."""

    def transcribe(self, audio, **kw):
        from types import SimpleNamespace as Seg
        return [Seg(text=" Thank you.", no_speech_prob=0.9, avg_logprob=-0.3),
                Seg(text=" The answer is 0.6.", no_speech_prob=0.1, avg_logprob=-0.4),
                Seg(text=" you", no_speech_prob=0.2, avg_logprob=-1.4)], None


def test_transcribe_drops_no_speech_and_low_confidence_segments(tmp_path):
    import speech as speech_mod
    sp = speech_mod.Speech(tmp_path)
    sp._whisper = NoisyWhisper()
    assert sp._transcribe(_wav(1)) == "The answer is 0.6."


def test_transcribe_of_pure_noise_is_empty(tmp_path):
    import speech as speech_mod
    from types import SimpleNamespace as Seg

    class W:
        def transcribe(self, audio, **kw):
            return iter([Seg(text=" Thank you.", no_speech_prob=0.7, avg_logprob=-0.2)]), None

    sp = speech_mod.Speech(tmp_path)
    sp._whisper = W()
    assert sp._transcribe(_wav(1)) == ""


def test_chat_passes_the_spreadsheet_to_the_tutor(env, signed_in):
    app_mod, client, _, _ = env
    signed_in()
    seen = []

    class FakeTutor:
        voice = True

        def ensure_conversation(self, s, fresh=False):
            return s.setdefault("conversation", {"messages": [], "display": [], "spoken": []})

        async def turn(self, s, text, hidden=False, sheet=None):
            seen.append((text, sheet))
            yield {"type": "text", "text": "x"}

    app_mod.tutor = FakeTutor()
    assert client.post("/api/chat", json={"message": "12.79", "sheet": "B7: =NPV(B1,B2:B6)  → 12.79"}).status_code == 200
    assert client.post("/api/chat", json={"message": "ok"}).status_code == 200
    assert seen == [("12.79", "B7: =NPV(B1,B2:B6)  → 12.79"), ("ok", None)]
    assert client.post("/api/chat", json={"message": "x", "sheet": "x" * 9000}).status_code == 400


def test_a_key_alone_does_not_switch_to_elevenlabs(monkeypatch):
    import settings
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(settings, "VOICE", "kokoro")
    assert settings.use_elevenlabs() is False
    monkeypatch.setattr(settings, "VOICE", "elevenlabs")
    assert settings.use_elevenlabs() is True
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "")
    assert settings.use_elevenlabs() is False      # no key: Kokoro speaks


def test_espeak_falls_back_to_the_bundled_copy(monkeypatch):
    import ctypes.util
    import speech as speech_mod
    monkeypatch.delenv("ESPEAK_LIB", raising=False)
    monkeypatch.delenv("ESPEAK_DATA", raising=False)
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: None)   # as on Windows
    lib, data = speech_mod._espeak()
    import espeakng_loader
    assert (lib, data) == (espeakng_loader.get_library_path(), espeakng_loader.get_data_path())


def test_note_routes_exist_only_in_the_preview(env, signed_in, tmp_path, monkeypatch):
    app_mod, client, _, _ = env
    signed_in()
    assert client.post("/api/note", json={"text": "x"}).status_code == 404
    assert client.get("/api/notes").status_code == 404
    assert "teacher" not in client.get("/api/config").json()

    monkeypatch.setattr(app_mod.settings, "TEACHER", True)
    monkeypatch.setattr(app_mod, "NOTES", tmp_path / "notes.jsonl")
    s = app_mod.store.load("acct-7")
    s["conversation"]["display"] = [
        {"role": "tutor", "text": "## Module 2: Many cash flows\n\nIntro.", "intro": True},
        {"role": "tutor", "text": "## Discount each one\n\nThe year-1 flow is worth 18.18 today."}]
    app_mod.store.save(s)
    assert client.get("/api/config").json()["teacher"] is True
    assert client.post("/api/note", json={"text": "  "}).status_code == 400
    n = client.post("/api/note", json={"text": "Use a bus-ticket analogy."}).json()
    assert (n["id"], n["module"], n["section"], n["status"]) == (1, 2, "Discount each one", "new")
    assert n["tutor_said"].endswith("18.18 today.")
    assert [x["text"] for x in client.get("/api/notes").json()] == ["Use a bus-ticket analogy."]


def test_teacher_mode_needs_a_local_run(monkeypatch):
    import settings
    monkeypatch.setenv("TUTORS_TEACHER", "1")
    monkeypatch.delenv("TUTORS_LOCAL", raising=False)
    assert importlib.reload(settings).TEACHER is False
    monkeypatch.setenv("TUTORS_LOCAL", "1")
    assert importlib.reload(settings).TEACHER is True
    monkeypatch.undo()
    importlib.reload(settings)


def test_restart_starts_the_current_module_over(env, signed_in):
    app_mod, client, _, _ = env
    signed_in()
    client.get("/api/me")
    assert client.post("/api/restart").status_code == 400      # not in a module yet

    s = app_mod.store.load("acct-7")
    s["conversation"]["messages"] = [{"role": "user", "content": "hi"}]
    s["conversation"]["display"] = [
        {"role": "tutor", "text": "## Module 1: One\n\nIntro.", "intro": True},
        {"role": "tutor", "text": "## Module 2: Two\n\nIntro.", "intro": True},
        {"role": "tutor", "text": "## Discount each one\n\nWorth 18.18 today."}]
    s["progress"] = {"modules_done": [1, 2], "now_in": "2, exercise 2.3", "mistakes_seen": ["sign"],
                     "objectives_met": ["1.1", "2.1", "2.2"]}
    app_mod.store.save(s)

    view = client.post("/api/restart").json()
    assert view["module"] == 2 and view["display"] == [] and view["fresh"]
    p = app_mod.store.load("acct-7")["progress"]
    assert p["objectives_met"] == ["1.1"] and p["modules_done"] == [1]
    assert p["mistakes_seen"] == ["sign"] and p["now_in"].startswith("2, restarted")
    assert "2.1" not in app_mod.store.load("acct-7")["conversation"]["record"]


def test_current_module_is_the_last_module_heading():
    from tutor import current_module
    assert current_module([]) is None
    assert current_module([{"role": "student", "text": "## Module 3"},
                           {"role": "tutor", "text": "## Module 1: A\n\n## Step"}]) == 1
