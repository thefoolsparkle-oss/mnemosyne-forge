"""Fish Audio provider — v0.8.

Fish reference_id controls the stable voice model. Voice Director controls
performance through short emotion tags and prosody parameters.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..env_utils import read_env


class FishAudioProvider:
    async def synthesize(self, text: str, profile: dict, output_path: str, **kwargs) -> str:
        from ..config import get_config

        cfg = get_config()
        fish_cfg = cfg.get("voice", {}).get("fish_audio", {})
        api_key_env = fish_cfg.get("api_key_env", "FISH_API_KEY")
        api_key = read_env(api_key_env)
        if not api_key:
            raise RuntimeError(f"{api_key_env} 环境变量未设置，请在 .env 中添加 {api_key_env}=your-key")

        import httpx

        references = profile.get("provider_hints", {}).get("fish_references", []) or []
        reference_id = "" if references else profile.get("provider_hints", {}).get("fish_reference_id", "")
        if not reference_id:
            reference_id = self._match_from_library(profile)
        directive = self._voice_directive(profile)

        payload = {
            "text": self._apply_speech_cues(text, profile, directive),
            "format": "mp3",
            "normalize": False,
            "prosody": directive.get("prosody", {}),
        }
        if reference_id:
            payload["reference_id"] = reference_id

        latency = profile.get("provider_hints", {}).get("fish_latency", "")
        if latency:
            payload["latency"] = latency

        headers = {"Authorization": f"Bearer {api_key}", "model": fish_cfg.get("model", "s2-pro")}
        async with httpx.AsyncClient(timeout=90.0) as client:
            if references:
                files = self._multipart_files(payload, references)
                try:
                    resp = await client.post("https://api.fish.audio/v1/tts", headers=headers, files=files)
                finally:
                    for item in files:
                        value = item[1]
                        if isinstance(value, tuple) and hasattr(value[-1], "close"):
                            value[-1].close()
            else:
                resp = await client.post(
                    "https://api.fish.audio/v1/tts",
                    headers={**headers, "Content-Type": "application/json"},
                    json=payload,
                )

        if resp.status_code == 401 or resp.status_code == 403:
            raise RuntimeError("Fish Audio API Key 无效，请检查 FISH_API_KEY")
        if resp.status_code != 200:
            raise RuntimeError(f"Fish Audio API 返回错误 {resp.status_code}: {resp.text[:200]}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return output_path

    @staticmethod
    def _multipart_files(payload: dict, references: list[dict]) -> list[tuple]:
        files: list[tuple] = []
        for key, value in payload.items():
            if isinstance(value, dict):
                import json
                files.append((key, (None, json.dumps(value, ensure_ascii=False))))
            else:
                files.append((key, (None, str(value))))

        for idx, ref in enumerate(references):
            path = Path(ref.get("audio_path", ""))
            text = str(ref.get("text") or ref.get("transcript") or "")
            if not path.exists() or not text:
                continue
            files.append((f"references[{idx}][audio]", (path.name, open(path, "rb"), "audio/mpeg")))
            files.append((f"references[{idx}][text]", (None, text)))
        return files

    @staticmethod
    def _voice_directive(profile: dict) -> dict:
        hints = profile.get("provider_hints", {}) or {}
        directive = dict(profile.get("fish_tts_directive") or {})
        if hints.get("fish_tts_directive") and isinstance(hints["fish_tts_directive"], dict):
            directive.update(hints["fish_tts_directive"])
        if hints.get("fish_voice_prompt"):
            directive["text_prefix"] = hints["fish_voice_prompt"]

        if not directive:
            directive = {
                "emotion_tags": ["calm"],
                "prosody": {"speed": 0.9, "volume": -3},
                "text_prefix": "(calm)",
            }
        directive.setdefault("emotion_tags", [])
        directive.setdefault("prosody", {"speed": 0.9, "volume": -3})
        directive.setdefault("text_prefix", "")
        return directive

    @staticmethod
    def _apply_speech_cues(text: str, profile: dict, directive: dict) -> str:
        """Apply speech cues to text based on VoiceProfile.

        Adds concise Fish emotion tags based on:
        - emotion_level: flat/restrained → fewer cues; intense → more
        - pause_style: long_pauses → short wording is preferred over extra tags
        - emotional_color: maps to a small number of tags
        """
        colors = [c.lower() for c in (profile.get("emotional_color", []) or [])]

        cues = []
        prefix = str(directive.get("text_prefix") or "").strip()
        if prefix:
            cues.append(prefix)
        else:
            for tag in directive.get("emotion_tags", [])[:2]:
                tag = str(tag).strip().strip("()[]")
                if tag:
                    cues.append(f"({tag})")

        # Emotion color cues
        existing = " ".join(cues)
        for c in colors:
            if c in ("tired", "exhausted", "weary", "疲惫") and "tired" not in existing:
                cues.append("(tired)")
            if c in ("melancholic", "sad", "melancholy") and "sad" not in existing:
                cues.append("(sad)")

        # Build final text
        prefix = " ".join(cues[:3]).strip()
        return f"{prefix} {text}" if prefix else text

    @staticmethod
    def _map_speed(profile: dict) -> float:
        """Map VoiceProfile speed to Fish Audio speed multiplier (0.5 - 2.0)."""
        s = str(profile.get("speed", "medium")).lower()
        return {
            "very_slow": 0.7, "slow": 0.85, "medium": 1.0,
            "fast": 1.25, "very_fast": 1.5,
        }.get(s, 1.0)

    @staticmethod
    def _match_from_library(profile: dict) -> str:
        """Match VoiceProfile against config.yaml fish_audio.voice_library.

        Returns the best-matching reference_id, or empty string if none found.
        """
        try:
            from ..config import get_config
            cfg = get_config()
            library = cfg.get("voice", {}).get("fish_audio", {}).get("voice_library", [])
        except Exception:
            return ""

        if not library:
            return ""

        best_id = ""
        best_score = 0

        gt = str(profile.get("gender_tone", "")).lower()
        va = str(profile.get("voice_age", "")).lower()
        el = str(profile.get("emotion_level", "")).lower()

        for entry in library:
            ref_id = entry.get("reference_id", "")
            if not ref_id:
                continue
            p = entry.get("profile", {})
            score = 0
            if p.get("gender_tone") == gt:
                score += 2
            if p.get("voice_age") == va:
                score += 1
            if p.get("emotion_level") == el:
                score += 1
            if score > best_score:
                best_score = score
                best_id = ref_id

        return best_id
