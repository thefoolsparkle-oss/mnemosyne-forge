"""ElevenLabs voice design + TTS provider.

Voice identity and performance are deliberately separated:
- Voice Design creates stable OC-specific candidate voices.
- TTS reads actual dialogue with a saved voice_id and per-line settings.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from ..env_utils import read_env


class ElevenLabsProvider:
    async def synthesize(self, text: str, profile: dict, output_path: str, **kwargs) -> str:
        voice_id = await self.ensure_voice(profile, output_path=output_path)
        return await self.text_to_speech(text, voice_id, profile, output_path, **kwargs)

    async def ensure_voice(self, profile: dict, output_path: str | None = None) -> str:
        """Return a saved voice_id, creating one from Voice Design when needed."""
        hints = profile.setdefault("provider_hints", {})
        force_design = bool(hints.get("elevenlabs_force_design"))
        if hints.get("elevenlabs_voice_id") and not force_design:
            return str(hints["elevenlabs_voice_id"])

        design = await self.design_voice(profile, output_path=output_path)
        previews = design.get("previews") or []
        if not previews:
            raise RuntimeError("ElevenLabs Voice Design did not return previews.")

        selected_index = max(1, int(hints.get("elevenlabs_selected_preview_index") or 1))
        selected_index = min(selected_index, len(previews))
        return await self.save_designed_voice(profile, design, selected_index)

    async def save_designed_voice(self, profile: dict, design: dict, selected_index: int = 1) -> str:
        previews = design.get("previews") or []
        if not previews:
            raise RuntimeError("ElevenLabs Voice Design did not return previews.")
        selected_index = max(1, min(int(selected_index), len(previews)))
        selected = previews[selected_index - 1]
        generated_voice_id = selected.get("generated_voice_id")
        if not generated_voice_id:
            raise RuntimeError("Selected ElevenLabs preview has no generated_voice_id.")

        voice = await self.create_voice(
            generated_voice_id=generated_voice_id,
            voice_name=self._voice_name(profile),
            voice_description=design["voice_description"],
            played_not_selected_voice_ids=[
                p["generated_voice_id"]
                for idx, p in enumerate(previews)
                if idx != selected_index - 1 and p.get("generated_voice_id")
            ],
        )
        hints = profile.setdefault("provider_hints", {})
        hints["provider"] = "elevenlabs"
        hints["elevenlabs_voice_id"] = voice["voice_id"]
        hints["elevenlabs_voice_name"] = voice.get("name") or self._voice_name(profile)
        hints["elevenlabs_generated_voice_id"] = generated_voice_id
        hints["elevenlabs_selected_preview_index"] = selected_index
        hints["elevenlabs_voice_description"] = design["voice_description"]
        hints["elevenlabs_preview_paths"] = design.get("preview_paths", [])
        hints["elevenlabs_previews"] = design.get("preview_metadata", [])
        hints.pop("elevenlabs_force_design", None)
        return str(voice["voice_id"])

    async def design_voice(self, profile: dict, output_path: str | None = None) -> dict:
        from ..config import get_config

        cfg = get_config().get("voice", {}).get("elevenlabs", {})
        api_key = self._api_key(cfg)
        model_id = cfg.get("voice_design_model_id", "eleven_multilingual_ttv_v2")
        output_format = cfg.get("voice_design_output_format", cfg.get("output_format", "mp3_44100_128"))
        voice_description = self._voice_description(profile)
        preview_text = self._preview_text(profile)

        import httpx

        payload: dict[str, Any] = {
            "voice_description": voice_description,
            "model_id": model_id,
            "text": preview_text,
            "auto_generate_text": False,
            "loudness": float(cfg.get("design_loudness", 0.35)),
            "guidance_scale": float(cfg.get("design_guidance_scale", 4.0)),
            "quality": float(cfg.get("design_quality", 0.7)),
            "should_enhance": bool(cfg.get("design_should_enhance", True)),
        }
        seed = cfg.get("design_seed")
        if seed is not None and seed != "":
            payload["seed"] = int(seed)

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.elevenlabs.io/v1/text-to-voice/design",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                params={"output_format": output_format},
                json=payload,
            )
        self._raise_for_error(resp, "ElevenLabs Voice Design")
        data = resp.json()

        preview_paths = []
        if output_path:
            preview_dir = Path(output_path).with_suffix("")
            preview_dir.mkdir(parents=True, exist_ok=True)
            for idx, preview in enumerate(data.get("previews", []), start=1):
                audio_b64 = preview.get("audio_base_64")
                if not audio_b64:
                    continue
                media_type = str(preview.get("media_type") or "audio/mpeg")
                ext = ".mp3" if "mpeg" in media_type or "mp3" in media_type else ".wav"
                preview_path = preview_dir / f"preview_{idx}{ext}"
                preview_path.write_bytes(base64.b64decode(audio_b64))
                preview_paths.append(str(preview_path))

        data["voice_description"] = voice_description
        data["preview_text"] = preview_text
        data["preview_paths"] = preview_paths
        data["preview_metadata"] = [
            {
                "index": idx,
                "generated_voice_id": preview.get("generated_voice_id"),
                "media_type": preview.get("media_type"),
                "duration_secs": preview.get("duration_secs"),
                "language": preview.get("language"),
                "preview_path": preview_paths[idx - 1] if idx - 1 < len(preview_paths) else "",
            }
            for idx, preview in enumerate(data.get("previews", []), start=1)
        ]
        return data

    async def create_voice(
        self,
        generated_voice_id: str,
        voice_name: str,
        voice_description: str,
        played_not_selected_voice_ids: list[str] | None = None,
    ) -> dict:
        from ..config import get_config

        cfg = get_config().get("voice", {}).get("elevenlabs", {})
        api_key = self._api_key(cfg)
        payload: dict[str, Any] = {
            "voice_name": voice_name,
            "voice_description": voice_description,
            "generated_voice_id": generated_voice_id,
            "labels": {
                "source": "mnemosyne_forge",
                "language": "zh",
                "use_case": "oc_character_voice",
            },
        }
        if played_not_selected_voice_ids:
            payload["played_not_selected_voice_ids"] = played_not_selected_voice_ids

        import httpx

        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                "https://api.elevenlabs.io/v1/text-to-voice",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
            )
        self._raise_for_error(resp, "ElevenLabs Create Voice")
        return resp.json()

    async def text_to_speech(self, text: str, voice_id: str, profile: dict, output_path: str, **kwargs) -> str:
        from ..config import get_config

        cfg = get_config().get("voice", {}).get("elevenlabs", {})
        api_key = self._api_key(cfg)
        model_id = cfg.get("tts_model_id", "eleven_multilingual_v2")
        output_format = cfg.get("output_format", "mp3_44100_128")

        previous_text = kwargs.get("previous_text", "")
        next_text = kwargs.get("next_text", "")

        payload: dict[str, Any] = {
            "text": text,
            "model_id": model_id,
            "language_code": cfg.get("language_code", "zh"),
            "voice_settings": self._apply_performance(
                profile.get("provider_hints", {}),
                self._voice_settings(profile, cfg),
                cfg,
                unit_index=kwargs.get("unit_index"),
                previous_text=previous_text,
                next_text=next_text,
            ),
        }
        seed = cfg.get("tts_seed")
        if seed is not None and seed != "":
            payload["seed"] = int(seed)

        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                params={"output_format": output_format},
                json=payload,
            )
        self._raise_for_error(resp, "ElevenLabs TTS")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return output_path

    async def synthesize_performance_units(
        self, profile: dict, output_path: str, **kwargs
    ) -> list[dict]:
        """Generate audio for each performance unit with per-unit voice settings.

        Returns a list of {unit_index, clean_text, audio_path, settings_used}.
        Previous/next text context is passed between units for emotional continuity.
        """
        units = profile.get("provider_hints", {}).get("performance_units", [])
        if not units:
            voice_id = await self.ensure_voice(profile, output_path=output_path)
            text = str(profile.get("sample_text") or "你好。")
            path = await self.text_to_speech(text, voice_id, profile, output_path)
            return [{"unit_index": 0, "clean_text": text, "audio_path": path, "settings_used": {}}]

        voice_id = await self.ensure_voice(profile, output_path=output_path)
        results = []
        for i, unit in enumerate(units):
            clean_text = str(unit.get("clean_text", "")).strip()
            if not clean_text:
                continue
            unit_path = output_path.replace(".mp3", "") + f"_unit{i}.mp3"
            prev = units[i - 1].get("clean_text", "") if i > 0 else ""
            nxt = units[i + 1].get("clean_text", "") if i + 1 < len(units) else ""
            try:
                path = await self.text_to_speech(
                    clean_text, voice_id, profile, unit_path,
                    unit_index=i, previous_text=prev, next_text=nxt,
                )
                results.append({"unit_index": i, "clean_text": clean_text, "audio_path": path})
            except Exception as e:
                results.append({"unit_index": i, "clean_text": clean_text, "audio_path": "", "error": str(e)})
        return results

    @staticmethod
    def _api_key(cfg: dict) -> str:
        api_key_env = cfg.get("api_key_env", "ELEVENLABS_API_KEY")
        api_key = read_env(api_key_env)
        if not api_key:
            raise RuntimeError(f"{api_key_env} environment variable is not set.")
        return api_key

    @staticmethod
    def _raise_for_error(resp: Any, label: str) -> None:
        if resp.status_code in (401, 403):
            raise RuntimeError(f"{label} auth failed: {resp.text[:300]}")
        if resp.status_code >= 400:
            raise RuntimeError(f"{label} returned {resp.status_code}: {resp.text[:500]}")

    @staticmethod
    def _voice_name(profile: dict) -> str:
        name = str(profile.get("character_name") or profile.get("name") or "OC Voice")
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        return f"Mnemosyne {name[:40]}"

    @staticmethod
    def _voice_description(profile: dict) -> str:
        hints = profile.get("provider_hints", {}) or {}
        if hints.get("elevenlabs_voice_description"):
            return str(hints["elevenlabs_voice_description"])

        age = profile.get("voice_age") or "young adult"
        gender = profile.get("gender_tone") or "feminine"
        timbre = profile.get("timbre") or "soft, clear, slightly breathy"
        pitch = profile.get("pitch") or "medium high"
        speed = profile.get("speed") or "slow"
        emotion = profile.get("emotion_level") or "restrained"
        colors = ", ".join(profile.get("emotional_color", []) or ["melancholic", "quiet"])
        distance = profile.get("distance_feeling") or "distant but intimate"
        speaking_style = profile.get("speaking_style") or "short Chinese sentences, guarded, emotionally controlled"
        summary = profile.get("voice_summary") or ""

        return (
            f"A natural Mandarin Chinese character voice. {gender} {age} speaker; "
            f"{timbre} timbre; {pitch} pitch; {speed} pacing; {emotion} emotional delivery. "
            f"The voice should feel {distance}, with emotional colors of {colors}. "
            f"Speaking style: {speaking_style}. {summary} "
            "Avoid a robotic assistant tone, avoid exaggerated anime cuteness, avoid English narrator affect, "
            "and avoid overacting. The result should sound like a real person speaking intimate Chinese dialogue."
        )[:1000]

    @staticmethod
    def _preview_text(profile: dict) -> str:
        parts = []
        variants = profile.get("sample_variants") or []
        for line in variants:
            line = str(line).strip()
            if line and line not in parts:
                parts.append(line)
        sample = str(profile.get("sample_text") or "").strip()
        if sample and sample not in parts:
            parts.insert(0, sample)
        fallback = [
            "别靠近我。那不是你该碰的东西。",
            "我没有在等谁，只是这里比较安静。",
            "如果你一定要留下，就别问我从前的事。",
        ]
        for line in fallback:
            if line not in parts:
                parts.append(line)
        text = " ".join(parts)
        while len(text) < 100:
            text += " " + fallback[len(text) % len(fallback)]
        return text[:1000]

    @staticmethod
    def _voice_settings(profile: dict, cfg: dict) -> dict:
        hints = profile.get("provider_hints", {}) or {}
        emotion = str(profile.get("emotion_level") or "").lower()
        speed = str(profile.get("speed") or "").lower()

        stability = float(hints.get("el_stability", cfg.get("stability", 0.58)))
        similarity_boost = float(hints.get("el_similarity_boost", cfg.get("similarity_boost", 0.82)))
        style = float(hints.get("el_style", cfg.get("style", 0.22)))
        speed_value = float(hints.get("el_speed", cfg.get("speed", 0.95)))

        if emotion in ("flat", "restrained"):
            stability = max(stability, 0.62)
            style = min(style, 0.18)
        elif emotion in ("expressive", "intense"):
            stability = min(stability, 0.48)
            style = max(style, 0.35)

        speed_value = {
            "very_slow": 0.82,
            "slow": 0.9,
            "medium": 0.98,
            "fast": 1.06,
            "very_fast": 1.12,
        }.get(speed, speed_value)

        return {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": bool(cfg.get("use_speaker_boost", True)),
            "speed": speed_value,
        }

    @staticmethod
    def _apply_performance(
        hints: dict, base_settings: dict, cfg: dict,
        unit_index: int | None = None,
        previous_text: str = "",
        next_text: str = "",
    ) -> dict:
        """Apply performance_units from Dialogue Performance Agent to ElevenLabs voice_settings.

        Aggregates emotional direction across all units, mapping:
          emotion  -> stability / style
          speed    -> speed
          volume   -> similarity_boost
          distance -> stability / style (distant = more restrained)
          pause    -> applied at the sentence level (future per-unit TTS)

        If unit_index is provided, that unit's emotion/speed/volume dominates.
        """
        units = hints.get("performance_units", [])
        if not units:
            return base_settings

        settings = dict(base_settings)

        if unit_index is not None and 0 <= unit_index < len(units):
            units_to_use = [units[unit_index]]
        else:
            units_to_use = units

        emotions = [str(u.get("emotion", "")).lower() for u in units_to_use if u.get("emotion")]
        speeds = [str(u.get("speed", "")).lower() for u in units_to_use if u.get("speed")]
        volumes = [str(u.get("volume", "")).lower() for u in units_to_use if u.get("volume")]
        distances = [str(u.get("distance", "")).lower() for u in units_to_use if u.get("distance")]

        dominant = lambda vals: max(set(vals), key=vals.count) if vals else ""

        emotion = dominant(emotions) or "calm"
        perf_speed = dominant(speeds) or "normal"
        perf_volume = dominant(volumes) or "normal"
        perf_distance = dominant(distances) or "casual"

        emotion_params = {
            "calm":       {"stability": 0.65, "style": 0.10},
            "restrained": {"stability": 0.70, "style": 0.08},
            "cold":       {"stability": 0.72, "style": 0.05},
            "sad":        {"stability": 0.58, "style": 0.15},
            "tired":      {"stability": 0.62, "style": 0.12},
            "gentle":     {"stability": 0.55, "style": 0.18},
            "expressive": {"stability": 0.40, "style": 0.40},
            "intense":    {"stability": 0.38, "style": 0.45},
            "angry":      {"stability": 0.35, "style": 0.50},
        }
        ep = emotion_params.get(emotion, {"stability": 0.58, "style": 0.22})
        settings["stability"] = ep["stability"]
        settings["style"] = ep["style"]

        dist_adjust = {
            "distant":  {"stability": +0.06, "style": -0.04},
            "intimate": {"stability": -0.05, "style": +0.06},
            "formal":   {"stability": +0.04, "style": -0.02},
        }.get(perf_distance, {})
        settings["stability"] = max(0.0, min(1.0, settings["stability"] + dist_adjust.get("stability", 0)))
        settings["style"] = max(0.0, min(1.0, settings["style"] + dist_adjust.get("style", 0)))

        speed_map = {
            "very_slow": 0.80, "slow": 0.88, "normal": 0.98,
            "fast": 1.08, "very_fast": 1.14,
        }
        settings["speed"] = speed_map.get(perf_speed, settings.get("speed", 0.95))

        vol_boost_map = {"whisper": 0.72, "soft": 0.76, "normal": 0.82, "loud": 0.88}
        settings["similarity_boost"] = vol_boost_map.get(perf_volume, settings.get("similarity_boost", 0.82))

        # Contextual continuity: previous_text / next_text modulate emotional baseline
        if previous_text and len(previous_text) < 200:
            prev_lower = previous_text.lower()
            if any(w in prev_lower for w in ["?", "!", "?"]):
                settings["stability"] = min(1.0, settings["stability"] - 0.05)
            if any(w in prev_lower for w in ["...", ".."]):
                settings["stability"] = min(1.0, settings["stability"] + 0.03)
        if next_text and len(next_text) < 200:
            next_lower = next_text.lower()
            if any(w in next_lower for w in ["?", "!", "?"]):
                settings["style"] = min(1.0, settings["style"] + 0.03)

        return settings
