"""Speed benchmark for the voice engines.  Run: .venv/bin/python scripts/voice_bench.py

Prints seconds of computing per second of audio (lower is faster; under 1 is real time).
"""
import asyncio
import io
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import soundfile  # noqa: E402

from speech import Speech  # noqa: E402

SENTENCES = [
    "In a one-period binomial tree, the stock either moves up by the factor u or down by the factor d.",
    "The risk-neutral probability q makes the expected stock return equal to the risk-free rate.",
    "Because early exercise is worth more than holding the option, the American put is exercised at that node.",
]


def wav_seconds(wav):
    info = soundfile.info(io.BytesIO(wav))
    return info.frames / info.samplerate


async def main():
    s = Speech(Path(os.environ.get("DATA_DIR") or ROOT / "data"))
    t = time.time()
    s.start()
    while not s.ready and not s.error:
        await asyncio.sleep(0.5)
    if s.error:
        sys.exit(f"load failed: {s.error}")
    print(f"load: {time.time() - t:.1f} s")

    await s.synth("Warm up.")
    t = time.time()
    audio = 0.0
    clips = []
    for text in SENTENCES:
        wav = await s.synth(text)
        clips.append(wav)
        audio += wav_seconds(wav)
    took = time.time() - t
    print(f"synth: {took:.2f} s compute for {audio:.1f} s audio = {took / audio:.2f} s per audio second")

    # build a clip of about 5 s from the synthesized speech
    samples, rate = soundfile.read(io.BytesIO(clips[0]), dtype="float32")
    buf = io.BytesIO()
    soundfile.write(buf, samples[: 5 * rate], rate, format="WAV", subtype="PCM_16")
    clip = buf.getvalue()
    await s.transcribe(clip)   # warm up
    t = time.time()
    text = await s.transcribe(clip)
    took = time.time() - t
    secs = wav_seconds(clip)
    print(f"transcribe: {took:.2f} s compute for {secs:.1f} s audio = {took / secs:.2f} s per audio second")
    print("heard:", text)


asyncio.run(main())
