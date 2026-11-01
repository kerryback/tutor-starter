"""Voice settings, read from the environment once at import."""

import os


def _on(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:   # a bad value must not stop the app (the text version imports this too)
        return default


VOICE_ENABLED = _on("VOICE_ENABLED")
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
# With an ElevenLabs key, ElevenLabs speaks the tutor's replies; without one, Kokoro does.
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
