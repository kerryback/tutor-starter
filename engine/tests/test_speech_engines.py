"""Real Kokoro and Whisper engines.  Run with VOICE_ENGINE_TESTS=1.

Uses the repo's git-ignored data/ directory so the models download once.
"""
import asyncio
import io
import os
import sys
import time
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.skipif(os.environ.get("VOICE_ENGINE_TESTS") != "1",
                                reason="set VOICE_ENGINE_TESTS=1 to run the real engines")


@pytest.fixture(scope="module")
def speech():
    from speech import Speech
    s = Speech(ROOT / "data")
    s.start()
    deadline = time.time() + 300
    while not s.ready and not s.error and time.time() < deadline:
        time.sleep(0.5)
    assert s.ready, f"speech did not load: {s.error}"
    return s


def _silence(seconds=1, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\0\0" * rate * seconds)
    return buf.getvalue()


def test_round_trip(speech):
    wav = asyncio.run(speech.synth("The option is worth five dollars today."))
    assert wav[:4] == b"RIFF"
    text = asyncio.run(speech.transcribe(wav))   # transcribe resamples 24 kHz to 16 kHz
    # Whisper writes numbers as digits, so "five dollars" may come back as "$5".
    assert "five dollars" in text.lower() or "$5" in text


def test_silence_gives_no_text(speech):
    text = asyncio.run(speech.transcribe(_silence()))
    assert text.strip(" \t\n.,!?-…") == ""
