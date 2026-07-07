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


def test_performance_mapping_more_emotions() -> None:
    """Cover additional emotion/speed/volume/distance combinations."""
    base = {
        "stability": 0.58,
        "similarity_boost": 0.82,
        "style": 0.22,
        "use_speaker_boost": True,
        "speed": 0.95,
    }

    def unit(emotion: str, speed: str, volume: str, distance: str) -> dict:
        return {
            "clean_text": "sample",
            "emotion": emotion,
            "speed": speed,
            "volume": volume,
            "distance": distance,
        }

    # calm + normal + whisper + formal -> high stability, low style, slow speed
    calm = ElevenLabsProvider._apply_performance(
        {"performance_units": [unit("calm", "normal", "whisper", "formal")]},
        dict(base), {}, unit_index=0,
    )
    assert_close(calm["stability"], 0.69, "calm formal stability")  # 0.65 + 0.04
    assert_close(calm["style"], 0.08, "calm formal style")  # 0.10 - 0.02
    assert_close(calm["speed"], 0.98, "normal speed")
    assert_close(calm["similarity_boost"], 0.72, "whisper volume")

    # expressive + fast + loud + intimate -> low stability, high style, fast speed
    expressive = ElevenLabsProvider._apply_performance(
        {"performance_units": [unit("expressive", "fast", "loud", "intimate")]},
        dict(base), {}, unit_index=0,
    )
    assert_close(expressive["stability"], 0.35, "expressive intimate stability")  # 0.40 - 0.05
    assert_close(expressive["style"], 0.46, "expressive intimate style")  # 0.40 + 0.06
    assert_close(expressive["speed"], 1.08, "fast speed")
    assert_close(expressive["similarity_boost"], 0.88, "loud volume")

    # intense + very_fast + normal + casual -> very low stability, high style
    intense = ElevenLabsProvider._apply_performance(
        {"performance_units": [unit("intense", "very_fast", "normal", "casual")]},
        dict(base), {}, unit_index=0,
    )
    assert_close(intense["stability"], 0.38, "intense stability")
    assert_close(intense["style"], 0.45, "intense style")
    assert_close(intense["speed"], 1.14, "very fast speed")
    assert_close(intense["similarity_boost"], 0.82, "normal volume")

    # sad + slow + soft + distant -> medium-low stability, medium style
    sad = ElevenLabsProvider._apply_performance(
        {"performance_units": [unit("sad", "slow", "soft", "distant")]},
        dict(base), {}, unit_index=0,
    )
    assert_close(sad["stability"], 0.64, "sad distant stability")  # 0.58 + 0.06
    assert_close(sad["style"], 0.11, "sad distant style")  # 0.15 - 0.04
    assert_close(sad["speed"], 0.88, "slow speed")
    assert_close(sad["similarity_boost"], 0.76, "soft volume")

    # gentle + very_slow + whisper + intimate -> low stability, raised style
    gentle = ElevenLabsProvider._apply_performance(
        {"performance_units": [unit("gentle", "very_slow", "whisper", "intimate")]},
        dict(base), {}, unit_index=0,
    )
    assert_close(gentle["stability"], 0.50, "gentle intimate stability")  # 0.55 - 0.05
    assert_close(gentle["style"], 0.24, "gentle intimate style")  # 0.18 + 0.06
    assert_close(gentle["speed"], 0.80, "very slow speed")
    assert_close(gentle["similarity_boost"], 0.72, "whisper volume")


def test_performance_overall_aggregation() -> None:
    """When unit_index is omitted, settings aggregate across all units."""
    base = {
        "stability": 0.58,
        "similarity_boost": 0.82,
        "style": 0.22,
        "use_speaker_boost": True,
        "speed": 0.95,
    }
    # Use repeated values so the dominant emotion/speed/volume/distance is unambiguous
    # regardless of set iteration order.
    hints = {
        "performance_units": [
            {"clean_text": "a", "emotion": "calm", "speed": "slow", "volume": "soft", "distance": "distant"},
            {"clean_text": "b", "emotion": "calm", "speed": "slow", "volume": "soft", "distance": "distant"},
            {"clean_text": "c", "emotion": "angry", "speed": "fast", "volume": "loud", "distance": "intimate"},
        ]
    }
    overall = ElevenLabsProvider._apply_performance(hints, dict(base), {})
    # Dominant emotion = calm, distance = distant, speed = slow, volume = soft
    assert_close(overall["stability"], 0.71, "overall dominant calm/distant stability")
    assert_close(overall["style"], 0.06, "overall dominant calm/distant style")
    assert_close(overall["speed"], 0.88, "overall dominant slow speed")
    assert_close(overall["similarity_boost"], 0.76, "overall dominant soft volume")


def test_performance_context_modulation() -> None:
    """Previous/next text context modulates stability and style."""
    base = {
        "stability": 0.58,
        "similarity_boost": 0.82,
        "style": 0.22,
        "use_speaker_boost": True,
        "speed": 0.95,
    }
    hints = {"performance_units": [{"clean_text": "What?", "emotion": "calm", "speed": "normal", "volume": "normal", "distance": "casual"}]}

    with_question_prev = ElevenLabsProvider._apply_performance(
        hints, dict(base), {}, unit_index=0, previous_text="Are you sure?"
    )
    assert_close(with_question_prev["stability"], 0.60, "previous question lowers stability")

    with_ellipsis_prev = ElevenLabsProvider._apply_performance(
        hints, dict(base), {}, unit_index=0, previous_text="Well..."
    )
    assert_close(with_ellipsis_prev["stability"], 0.68, "previous ellipsis raises stability")

    with_question_next = ElevenLabsProvider._apply_performance(
        hints, dict(base), {}, unit_index=0, next_text="Really?"
    )
    assert_close(with_question_next["style"], 0.13, "next question raises style")


def main() -> None:
    test_elevenlabs_auto_design_guard()
    test_performance_unit_mapping()
    test_performance_mapping_more_emotions()
    test_performance_overall_aggregation()
    test_performance_context_modulation()
    print("voice safety and performance tests passed")


if __name__ == "__main__":
    main()
