"""Offline regression tests for voice safety and performance mapping.

This script avoids external voice APIs. It checks the guard that prevents
implicit ElevenLabs voice creation and the local mapping from Dialogue
Performance units to ElevenLabs voice_settings.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.voice_safety import should_block_elevenlabs_auto_design
from app.voice_providers.elevenlabs_provider import ElevenLabsProvider


def assert_close(actual: float, expected: float, label: str) -> None:
    assert abs(actual - expected) < 0.0001, f"{label}: expected {expected}, got {actual}"


def test_elevenlabs_auto_design_guard() -> None:
    assert should_block_elevenlabs_auto_design("elevenlabs", {}, {}) is True
    assert should_block_elevenlabs_auto_design(
        "elevenlabs",
        {"provider_hints": {"elevenlabs_voice_id": "voice_123"}},
        {},
    ) is False
    assert should_block_elevenlabs_auto_design(
        "elevenlabs",
        {},
        {"allow_auto_design": True},
    ) is False
    assert should_block_elevenlabs_auto_design("edge_tts", {}, {}) is False


def test_performance_unit_mapping() -> None:
    base = {
        "stability": 0.58,
        "similarity_boost": 0.82,
        "style": 0.22,
        "use_speaker_boost": True,
        "speed": 0.95,
    }
    hints = {
        "performance_units": [
            {
                "clean_text": "I am keeping my distance.",
                "emotion": "restrained",
                "speed": "slow",
                "volume": "soft",
                "distance": "distant",
            },
            {
                "clean_text": "Do not touch that!",
                "emotion": "angry",
                "speed": "very_fast",
                "volume": "loud",
                "distance": "intimate",
            },
        ]
    }

    first = ElevenLabsProvider._apply_performance(hints, dict(base), {}, unit_index=0)
    assert_close(first["stability"], 0.76, "restrained distant stability")
    assert_close(first["style"], 0.04, "restrained distant style")
    assert_close(first["speed"], 0.88, "slow speed")
    assert_close(first["similarity_boost"], 0.76, "soft volume")

    second = ElevenLabsProvider._apply_performance(hints, dict(base), {}, unit_index=1)
    assert_close(second["stability"], 0.30, "angry intimate stability")
    assert_close(second["style"], 0.56, "angry intimate style")
    assert_close(second["speed"], 1.14, "very fast speed")
    assert_close(second["similarity_boost"], 0.88, "loud volume")

    contextual = ElevenLabsProvider._apply_performance(
        hints,
        dict(base),
        {},
        unit_index=0,
        previous_text="Really?",
        next_text="Are you sure?",
    )
    assert_close(contextual["stability"], 0.71, "previous question lowers stability")
    assert_close(contextual["style"], 0.07, "next question raises style")


def main() -> None:
    test_elevenlabs_auto_design_guard()
    test_performance_unit_mapping()
    print("voice safety and performance tests passed")


if __name__ == "__main__":
    main()
