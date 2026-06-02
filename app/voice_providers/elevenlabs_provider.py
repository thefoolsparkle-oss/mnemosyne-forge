"""ElevenLabs provider — v0.8.

Supports:
- TTS with existing voice_id
- Voice design from VoiceProfile (creates temporary voice)
"""

from __future__ import annotations

import os


class ElevenLabsProvider:
    async def synthesize(self, text: str, profile: dict, output_path: str, **kwargs) -> str:
        from ..config import get_config
        from ..env_utils import read_env

        cfg = get_config()
        el_cfg = cfg.get("voice", {}).get("elevenlabs", {})
        api_key = read_env(el_cfg.get("api_key_env", "ELEVENLABS_API_KEY"))
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY 环境变量未设置")

        import httpx

        voice_id = profile.get("provider_hints", {}).get("elevenlabs_voice_id", "")

        # If no voice_id, use built-in voice (Bella for feminine, Adam for masculine)
        if not voice_id:
            gt = str(profile.get("gender_tone", "")).lower()
            voice_id = "EXAVITQu4vr4xnSDxMaL" if "feminine" in gt else "pNInz6obpgDQGcFmaJgB"

        # Build TTS request
        tts_payload = {
            "text": text,
            "model_id": el_cfg.get("tts_model_id", "eleven_multilingual_v2"),
            "voice_settings": {
                "stability": el_cfg.get("stability", 0.58),
                "similarity_boost": el_cfg.get("similarity_boost", 0.82),
                "style": el_cfg.get("style", 0.22),
                "speed": el_cfg.get("speed", 0.95),
                "use_speaker_boost": el_cfg.get("use_speaker_boost", True),
            },
        }

        output_format = el_cfg.get("output_format", "mp3_44100_128")
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                params={"output_format": output_format},
                headers=headers,
                json=tts_payload,
            )

        if resp.status_code == 401:
            raise RuntimeError("ElevenLabs API Key 无效")
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs API 返回错误 {resp.status_code}: {resp.text[:200]}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return output_path

    async def _design_voice(self, profile: dict, api_key: str, el_cfg: dict) -> str:
        """Design a temporary voice from VoiceProfile using ElevenLabs Voice Design API.

        Two-step process: 1) create previews -> get generated_voice_id, 2) create voice from preview.
        """
        import httpx
        import uuid

        # Build voice description
        parts = []
        for field in ["gender_tone", "voice_age", "timbre", "pitch", "emotion_level"]:
            v = profile.get(field, "")
            if v:
                parts.append(f"{field}: {v}")
        summary = profile.get("voice_summary", "")
        if summary:
            parts.append(summary)
        voice_description = ". ".join(parts) if parts else "A natural, clear Chinese voice."

        sample_text = profile.get("sample_text", "你好，这是我说话的方式。")
        # ElevenLabs requires >= 100 characters
        while len(sample_text) < 110:
            sample_text = sample_text + " " + sample_text

        generated_voice_id = uuid.uuid4().hex
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}

        # Step 1: Create voice previews
        previews_payload = {
            "voice_description": voice_description,
            "text": sample_text,
            "auto_generate_text": False,
            "loudness": el_cfg.get("design_loudness", 0.35),
            "quality": el_cfg.get("design_quality", 0.7),
            "seed": 0,
            "guidance_scale": el_cfg.get("design_guidance_scale", 4.0),
            "generated_voice_id": generated_voice_id,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.elevenlabs.io/v1/text-to-voice/create-previews",
                headers=headers,
                json=previews_payload,
            )
            if resp.status_code != 200:
                return ""

            previews = resp.json()
            previews_list = previews.get("previews", [])
            if not previews_list:
                return ""

            # Use the first preview's generated_voice_id
            actual_generated_id = previews[0].get("generated_voice_id", generated_voice_id)

        # Step 2: Create voice from preview
        create_payload = {
            "voice_name": f"forge_{uuid.uuid4().hex[:8]}",
            "generated_voice_id": actual_generated_id,
            "voice_description": voice_description,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.elevenlabs.io/v1/text-to-voice/create-voice-from-preview",
                headers=headers,
                json=create_payload,
            )

        if resp.status_code == 200:
            data = resp.json()
            return data.get("voice_id", "")

        return ""
