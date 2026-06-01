"""Edge TTS provider — free, no API key required.

Maps VoiceProfile fields to Edge TTS parameters.
"""

from __future__ import annotations

import os


class EdgeTTSProvider:
    async def synthesize(self, text: str, profile: dict, output_path: str, **kwargs) -> str:
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError("edge-tts not installed. Run: pip install edge-tts")

        voice = await self._pick_voice(profile)
        rate = self._to_rate(profile.get("speed", "medium"))
        pitch = self._to_pitch(profile.get("pitch", "medium"))

        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        except Exception:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        try:
            await communicate.save(output_path)
        except Exception:
            fallback = edge_tts.Communicate(text, voice)
            await fallback.save(output_path)
        return output_path

    async def _pick_voice(self, profile: dict) -> str:
        """Map gender_tone → Edge TTS voice."""
        hints = profile.get("provider_hints", {}) if isinstance(profile.get("provider_hints"), dict) else {}
        if hints.get("edge_voice"):
            return hints["edge_voice"]

        # Try to list voices
        try:
            import edge_tts
            voices = await edge_tts.list_voices()
            zh_voices = [v for v in voices if v.get("Locale", "").startswith("zh-CN")]
            gt = profile.get("gender_tone", "")
            if "feminine" in str(gt).lower():
                preferred = ["Xiaoxiao", "Xiaoyi", "Xiaochen", "Xiaohan", "Xiaomeng"]
                for name in preferred:
                    candidates = [v for v in zh_voices if name in v.get("ShortName", "")]
                    if candidates:
                        return candidates[0]["ShortName"]
            if "masculine" in str(gt).lower():
                candidates = [v for v in zh_voices if "Yunyang" in v.get("ShortName", "")]
                if candidates:
                    return candidates[0]["ShortName"]
            # default
            if zh_voices:
                return zh_voices[0]["ShortName"]
        except Exception:
            pass
        # Fallback
        if "feminine" in str(profile.get("gender_tone", "")).lower():
            return "zh-CN-XiaoxiaoNeural"
        return "zh-CN-YunyangNeural"

    @staticmethod
    def _to_rate(speed: str) -> str:
        mapping = {
            "very_slow": "-30%", "slow": "-15%", "medium": "+0%",
            "fast": "+15%", "very_fast": "+30%",
        }
        return mapping.get(str(speed).lower(), "+0%")

    @staticmethod
    def _to_pitch(pitch: str) -> str:
        mapping = {
            "very_low": "-10Hz", "low": "-5Hz", "medium_low": "-2Hz",
            "medium": "+0Hz", "medium_high": "+3Hz",
            "high": "+5Hz", "very_high": "+10Hz",
        }
        return mapping.get(str(pitch).lower(), "+0Hz")
