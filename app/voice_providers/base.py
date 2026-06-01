"""Base voice provider protocol."""

from typing import Protocol


class VoiceProvider(Protocol):
    async def synthesize(self, text: str, profile: dict, output_path: str, **kwargs) -> str:
        """Generate audio from text using voice profile. Returns output path."""
        ...


def get_provider(name: str):
    """Factory: return provider instance by name."""
    if name == "none" or not name:
        from .none_provider import NoneProvider
        return NoneProvider()
    if name == "edge_tts":
        from .edge_tts_provider import EdgeTTSProvider
        return EdgeTTSProvider()
    if name == "fish_audio":
        from .fish_audio_provider import FishAudioProvider
        return FishAudioProvider()
    if name == "elevenlabs":
        from .elevenlabs_provider import ElevenLabsProvider
        return ElevenLabsProvider()
    raise ValueError(f"Unknown voice provider: {name}")
