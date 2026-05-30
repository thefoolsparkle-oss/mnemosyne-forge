"""Voice generation module — v0.8

Matches character traits to voice profiles. TTS generation is
provider-agnostic — configure in config.yaml.
"""

from __future__ import annotations

from .config import get_config
from .oc_models import OCDraft

# Voice template library
VOICE_TEMPLATES: dict[str, dict] = {
    "gentle_female": {
        "label": "温柔女声",
        "traits": ["温柔", "善良", "体贴", "柔和", "优雅"],
        "zh_voice": "zh-CN-XiaoxiaoNeural",
        "pitch": "+0Hz",
        "rate": "-10%",
    },
    "cool_female": {
        "label": "清冷女声",
        "traits": ["冷淡", "疏离", "冷静", "理性", "神秘"],
        "zh_voice": "zh-CN-XiaoyiNeural",
        "pitch": "-2Hz",
        "rate": "-5%",
    },
    "lively_female": {
        "label": "活泼少女声",
        "traits": ["活泼", "开朗", "元气", "热情", "天真"],
        "zh_voice": "zh-CN-XiaoxiaoNeural",
        "pitch": "+5Hz",
        "rate": "+5%",
    },
    "mature_female": {
        "label": "成熟女声",
        "traits": ["成熟", "稳重", "强势", "高贵", "冷艳"],
        "zh_voice": "zh-CN-YunxiNeural",
        "pitch": "-3Hz",
        "rate": "-8%",
    },
    "calm_male": {
        "label": "沉稳男声",
        "traits": ["沉稳", "可靠", "成熟", "坚毅", "寡言"],
        "zh_voice": "zh-CN-YunyangNeural",
        "pitch": "+0Hz",
        "rate": "-5%",
    },
    "youth_male": {
        "label": "少年音",
        "traits": ["少年", "热血", "冲动", "单纯", "勇敢"],
        "zh_voice": "zh-CN-YunyangNeural",
        "pitch": "+3Hz",
        "rate": "+5%",
    },
    "deep_mysterious": {
        "label": "低沉神秘声",
        "traits": ["神秘", "阴暗", "冷酷", "深沉", "魅惑"],
        "zh_voice": "zh-CN-YunjianNeural",
        "pitch": "-5Hz",
        "rate": "-10%",
    },
}


def match_voice_profile(draft: OCDraft) -> dict:
    """Match character traits to the best voice template."""
    char_traits = set(t.lower() for t in (draft.personality or []))
    if draft.gender:
        char_traits.add(draft.gender.lower())

    best_score = 0
    best_template = "cool_female"  # default

    for name, template in VOICE_TEMPLATES.items():
        score = sum(1 for t in template["traits"] if t in char_traits)
        if score > best_score:
            best_score = score
            best_template = name

    return {"template": best_template, "score": best_score, "config": VOICE_TEMPLATES[best_template]}


async def generate_character_voice(
    draft: OCDraft,
    template: str | None = None,
    sample_text: str | None = None,
) -> dict:
    """Generate a voice profile for the character.

    Returns voice configuration. TTS generation requires a provider
    configured in config.yaml (voice.provider + voice.api_key_env).
    """
    cfg = get_config()
    voice_cfg = cfg.get("voice", {})
    provider = voice_cfg.get("provider", "")
    api_key_env = voice_cfg.get("api_key_env", "")

    if template is None:
        matched = match_voice_profile(draft)
        template = matched["template"]

    voice_config = VOICE_TEMPLATES.get(template, VOICE_TEMPLATES["cool_female"])

    if sample_text is None:
        sample_text = draft.first_message or f"你好，我是{draft.name or '...'}。"

    result: dict = {
        "ok": True,
        "template": template,
        "label": voice_config["label"],
        "config": voice_config,
        "sample_text": sample_text,
        "tts_ready": bool(provider and api_key_env),
    }

    if not provider:
        result["note"] = "TTS provider not configured. Set 'voice.provider' and 'voice.api_key_env' in config.yaml."
    else:
        result["note"] = f"TTS provider '{provider}' configured but not yet connected."

    return result
