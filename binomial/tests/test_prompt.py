import hashlib

import tutor_config as cfg
from tutor import build_system_prompt

# Pinned so a change to the prompt is always deliberate. Update it when you
# change the instructions, topic.md, a teaching script or the module intros.
VOICE_PROMPT_SHA256 = "5ef8dc3f724e0dbd50d784484029fc59992acd430b945fb4983a240f9973870c"  # 2026-11-18: teach first; never ask for what you just said


def test_voice_prompt_has_every_part_of_the_tutor():
    p = build_system_prompt(voice=True)
    for part in [cfg.INSTRUCTIONS / "teaching.md", cfg.CONTENT / "topic.md", cfg.INSTRUCTIONS / "voice.md"]:
        assert part.read_text() in p
    for name in cfg.REFERENCES:
        assert (cfg.CONTENT / name).read_text() in p
    assert "3.8 Explain why, as the number of periods grows" in p     # the objectives


def test_voice_prompt_unchanged():
    p = build_system_prompt(voice=True)
    assert hashlib.sha256(p.encode()).hexdigest() == VOICE_PROMPT_SHA256
