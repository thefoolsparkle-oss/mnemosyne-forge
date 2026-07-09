"""Voice-generation safety helpers shared by API code and offline tests."""

from __future__ import annotations


def should_block_elevenlabs_auto_design(provider_name: str, profile: dict, body: dict) -> bool:
    """Return True when ElevenLabs TTS would create a paid voice implicitly."""
    if provider_name != "elevenlabs":
        return False
    if body.get("allow_auto_design"):
        return False
    hints = profile.get("provider_hints", {})
    return not bool(hints.get("elevenlabs_voice_id"))
