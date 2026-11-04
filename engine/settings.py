"""Voice settings, read from the environment once at import."""

import os
import tomllib
from pathlib import Path


def _on(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:   # a bad value must not stop the app (the text version imports this too)
        return default


VOICE_ENABLED = _on("VOICE_ENABLED")
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "af_heart")


def _site_voice():
    """The voice named in site.toml: voice = "kokoro" or "elevenlabs" (the old elevenlabs = true too)."""
    try:
        site = tomllib.loads((Path(__file__).resolve().parent.parent / "site.toml")
                            .read_text(encoding="utf-8"))["site"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return ""
    return site.get("voice") or ("elevenlabs" if site.get("elevenlabs") else "")


# Who speaks the tutor's replies: "kokoro" (free, runs on this machine) or
# "elevenlabs" (a paid service; needs ELEVENLABS_API_KEY).  TUTOR_VOICE wins over
# site.toml.  An ElevenLabs key in the shell does nothing unless this says "elevenlabs".
VOICE = (os.environ.get("TUTOR_VOICE") or _site_voice() or "kokoro").strip().lower()
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE = os.environ.get("ELEVENLABS_VOICE", "J9NvviOEdVm6E7Hwdpdj")   # Jerry B
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5")


def _float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


KOKORO_SPEED = _float("KOKORO_SPEED", 0.9)   # 1.0 is Kokoro's normal pace; lower is slower
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base.en")
VOICE_IDLE_SECONDS = _int("VOICE_IDLE_SECONDS", 45)


def use_elevenlabs():
    """True when ElevenLabs speaks: the voice setting says so and there is a key."""
    return VOICE == "elevenlabs" and bool(ELEVENLABS_API_KEY)
