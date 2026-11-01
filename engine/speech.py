"""Text-to-speech (ElevenLabs, or Kokoro without a key) and speech-to-text (faster-whisper).

Each engine runs on its own single-thread executor, so one synthesis and one
transcription can run at once and neither blocks the event loop.  The models
load on a background thread at start-up.  The heavy libraries are imported
inside the loader and worker code only, so the text version imports nothing
extra.
"""

import asyncio
import ctypes.util
import io
import os
import threading
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tutor_config

import settings

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_MODEL = "kokoro-v1.0.onnx"
KOKORO_VOICES = "voices-v1.0.bin"
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
ELEVENLABS_TIMEOUT = 30
MAX_CLIP_SECONDS = 60
SAMPLE_RATE = 24000
WHISPER_RATE = 16000
NO_SPEECH_MAX = 0.6      # segments Whisper thinks are not speech are dropped
LOGPROB_MIN = -1.0       # so are low-confidence segments (hallucinations on noise)
IDLE_TEXT = "Press the button when you are ready to continue."
WHISPER_PROMPT = tutor_config.WHISPER_PROMPT
ESPEAK_DATA_DIRS = [
    "/opt/homebrew/share/espeak-ng-data",
    "/usr/local/share/espeak-ng-data",
    "/usr/share/espeak-ng-data",
    "/usr/lib/x86_64-linux-gnu/espeak-ng-data",
    "/usr/lib/aarch64-linux-gnu/espeak-ng-data",
]


class ClipTooLong(ValueError):
    """The recording is longer than MAX_CLIP_SECONDS."""


class BadAudio(ValueError):
    """The upload is not audio the decoder can read."""


def _espeak_lib():
    return os.environ.get("ESPEAK_LIB") or ctypes.util.find_library("espeak-ng")


def _espeak_data():
    if os.environ.get("ESPEAK_DATA"):
        return os.environ["ESPEAK_DATA"]
    return next((d for d in ESPEAK_DATA_DIRS if Path(d).is_dir()), None)


def _download(url, dest: Path):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    part.rename(dest)


def _wav_bytes(samples, rate):
    import soundfile
    buf = io.BytesIO()
    soundfile.write(buf, samples, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _pcm_wav(pcm, rate):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _voice_name():
    if settings.ELEVENLABS_API_KEY:
        return f"eleven-{settings.ELEVENLABS_VOICE}-{settings.ELEVENLABS_MODEL}"
    return f"{settings.KOKORO_VOICE}-{settings.KOKORO_SPEED:g}"


class Speech:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.ready = False
        self.error = None
        self._kokoro = None
        self._whisper = None
        self._tts_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")
        self._stt_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")

    def start(self):
        threading.Thread(target=self._load, name="speech-load", daemon=True).start()

    def _load(self):
        try:
            from faster_whisper import WhisperModel
            from kokoro_onnx import Kokoro
            from kokoro_onnx.config import EspeakConfig

            models = self.data_dir / "models"
            if settings.ELEVENLABS_API_KEY:
                print(f"speech: ElevenLabs voice {settings.ELEVENLABS_VOICE}", flush=True)
            else:
                print("speech: no ELEVENLABS_API_KEY, so Kokoro speaks", flush=True)
                _download(MODEL_URL + KOKORO_MODEL, models / KOKORO_MODEL)
                _download(MODEL_URL + KOKORO_VOICES, models / KOKORO_VOICES)
                lib, data = _espeak_lib(), _espeak_data()
                if not lib or not data:
                    raise RuntimeError("espeak-ng not found")
                self._kokoro = Kokoro(str(models / KOKORO_MODEL), str(models / KOKORO_VOICES),
                                      espeak_config=EspeakConfig(lib_path=lib, data_path=data))
            self._whisper = WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8",
                                         download_root=str(models))
            self.ready = True
        except Exception as e:  # noqa: BLE001 - any load failure means "voice off"
            self.error = f"{type(e).__name__}: {e}"
            print("speech: models failed to load:", self.error, flush=True)

    # --- text to speech ---

    def _synth(self, text):
        if settings.ELEVENLABS_API_KEY:
            return self._synth_eleven(text)
        samples, rate = self._kokoro.create(text, voice=settings.KOKORO_VOICE, speed=settings.KOKORO_SPEED, lang="en-us")
        return _wav_bytes(samples, rate)

    def _synth_eleven(self, text):
        import httpx
        r = httpx.post(ELEVENLABS_URL.format(voice=settings.ELEVENLABS_VOICE),
                       params={"output_format": f"pcm_{SAMPLE_RATE}"},
                       headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
                       json={"text": text, "model_id": settings.ELEVENLABS_MODEL},
                       timeout=ELEVENLABS_TIMEOUT)
        r.raise_for_status()
        return _pcm_wav(r.content, SAMPLE_RATE)

    async def synth(self, text: str) -> bytes:
        return await asyncio.get_running_loop().run_in_executor(self._tts_pool, self._synth, text)

    async def idle_wav(self) -> bytes:
        path = self.data_dir / "voice" / f"idle-{_voice_name()}.wav"
        if not path.exists():
            data = await self.synth(IDLE_TEXT)   # same single-thread pool as every other synthesis
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)
        return path.read_bytes()

    # --- speech to text ---

    def _transcribe(self, wav):
        import numpy as np
        import soundfile
        try:
            samples, rate = soundfile.read(io.BytesIO(wav), dtype="float32", always_2d=True)
        except (soundfile.LibsndfileError, RuntimeError) as e:
            raise BadAudio(str(e)) from e
        if len(samples) / rate > MAX_CLIP_SECONDS:
            raise ClipTooLong(f"Recording is longer than {MAX_CLIP_SECONDS} seconds.")
        audio = samples.mean(axis=1)
        if rate != WHISPER_RATE and len(audio):
            n = round(len(audio) * WHISPER_RATE / rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        segments, _ = self._whisper.transcribe(audio, language="en", vad_filter=False,
                                               initial_prompt=WHISPER_PROMPT)
        kept = (s.text for s in segments
                if getattr(s, "no_speech_prob", 0.0) <= NO_SPEECH_MAX
                and getattr(s, "avg_logprob", 0.0) >= LOGPROB_MIN)
        return "".join(kept).strip()

    async def transcribe(self, wav: bytes) -> str:
        return await asyncio.get_running_loop().run_in_executor(self._stt_pool, self._transcribe, wav)
