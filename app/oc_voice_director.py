"""Voice Director Agent — v0.8

Analyzes full OC draft to generate a detailed, editable VoiceProfile.
Uses LLM for deep analysis, not simple template matching.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

VOICE_DIRECTOR_PROMPT = """你是 Voice Director Agent（声音导演）+ Fish TTS Prompt Agent。
你的任务不是写漂亮形容词，而是把 OC 设定转换成可执行、可调试的 TTS 指令。

重要现实约束：
- Fish 的 reference_id 决定稳定音色底座；prompt 很难可靠改变性别/年龄/音色本体。
- prompt 更适合控制表演：情绪、语气、音量、停顿、紧张度、台词写法。
- 如果角色对性别、年龄、音色要求很强，必须在 reference_strategy 中说明需要匹配 reference_id。
- 不要把长英文声线描述直接塞进朗读文本，容易被模型读出来或干扰中文发音。

## 分析维度：
- voice_age: 声音年龄感（child / teen / young_adult / adult / mature / elderly）
- gender_tone: 性别倾向（feminine / masculine / androgynous / neutral）
- timbre: 音色质感（clear / soft / husky / deep / airy / metallic / warm / cold / breathy）
- pitch: 音高（very_low / low / medium_low / medium / medium_high / high / very_high）
- speed: 语速（very_slow / slow / medium / fast / very_fast）
- volume: 音量（low / medium / strong）
- emotion_level: 情绪表达强度（flat / restrained / gentle / expressive / intense）
- emotional_color: 情绪色彩列表，如 ["lonely","sacred","tired","cold","melancholic"]
- pause_style: 停顿方式（few_pauses / natural / long_pauses / fragmented）
- articulation: 咬字（clean / lazy / formal / whispery / sharp）
- distance_feeling: 距离感（intimate / distant / commanding / cautious / warm）
- speaking_style: 一段自然中文描述这个角色的说话方式（语气、常用词、句式特点、对话习惯）
- sample_text: 10-35 字的中文试音台词，必须是角色原话，用于 TTS 朗读
- sample_variants: 3 条中文试音台词，分别测试冷静、情绪裂缝、亲密距离
- voice_summary: 一句话概括声音印象
- reference_strategy: 说明是否必须使用 reference_id，以及推荐搜索/筛选什么样的 Fish 音色
- fish_tts_directive: Fish 专用 TTS 指令对象
- reason: 详细解释为什么推荐这个声音方向，引用角色性格/背景/说话方式作为依据
- confidence: 0-1 之间的置信度
- warnings: [] 或提醒列表

## sample_text 要求：
- 必须是角色会在对话中说出的自然语句，不是旁白或描述
- 能体现角色的性格和说话风格
- 不要太长（10-30 字）
- 要有具体的语境感，不要泛泛的"你好"之类
- 中文台词里不要出现英文 prompt、括号标签或旁白

## fish_tts_directive 要求：
{
  "emotion_tags": ["calm", "sad", "whispering"],
  "prosody": {"speed": 0.82, "volume": -4},
  "pause_plan": "short_sentences_with_one_long_pause",
  "text_prefix": "(calm) (sad)",
  "performance_note": "中文说明，描述表演重点",
  "avoid": ["不要撒娇", "不要过度哭腔", "不要活泼"]
}

- emotion_tags 只能放少量高置信标签，不要堆砌
- prosody.speed 建议 0.75-1.15，volume 建议 -8 到 3
- text_prefix 只使用简短括号情绪标签，不写长英文句子
- performance_note 给用户/调参界面看，不直接朗读

## JSON 格式：
{"voice_profile": {"voice_age": "...", "fish_tts_directive": {...}, ...}}

只返回 JSON。"""


def _draft_context(draft: OCDraft) -> str:
    lines = []
    if draft.name:
        lines.append(f"角色名: {draft.name}")
    if draft.gender:
        lines.append(f"性别: {draft.gender}")
    if draft.age_range:
        lines.append(f"年龄: {draft.age_range}")
    if draft.core_concept:
        lines.append(f"核心概念: {draft.core_concept}")
    if draft.personality:
        lines.append(f"性格: {', '.join(draft.personality)}")
    if draft.background:
        lines.append(f"背景: {draft.background}")
    if draft.speaking_style:
        lines.append(f"说话方式: {draft.speaking_style}")
    if draft.scenario:
        lines.append(f"场景: {draft.scenario}")
    if draft.themes:
        lines.append(f"主题: {', '.join(draft.themes)}")
    return "\n".join(lines) if lines else "(角色信息不足)"


async def analyze_voice(draft: OCDraft) -> dict:
    """Analyze character draft and generate a VoiceProfile."""
    context = _draft_context(draft)

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": f"角色设定:\n{context}\n\n请分析这个角色的声音方向。"}],
            system_prompt=VOICE_DIRECTOR_PROMPT,
            agent="export",
        )
        profile = result.get("voice_profile", result)
        profile.setdefault("language", "zh-CN")
        profile.setdefault("user_overrides", {})
        profile.setdefault("locked_fields", [])
        profile.setdefault("provider_preference", None)
        profile.setdefault("provider_hints", {})
        profile.setdefault("sample_variants", _fallback_sample_variants(profile))
        profile.setdefault("reference_strategy", _fallback_reference_strategy(profile))
        profile.setdefault("fish_tts_directive", _fallback_fish_tts_directive(profile))
        profile.setdefault("fish_voice_prompt", _legacy_fish_voice_prompt(profile))
        return profile
    except Exception:
        return {
            "voice_age": None, "gender_tone": None, "timbre": None,
            "pitch": None, "speed": None, "volume": None,
            "emotion_level": None, "emotional_color": [],
            "pause_style": None, "articulation": None,
            "distance_feeling": None, "speaking_style": None,
            "sample_text": None, "voice_summary": "分析失败",
            "sample_variants": [],
            "reference_strategy": "角色音色需要人工或自动匹配 reference_id；当前仅能用情绪标签控制表演。",
            "fish_tts_directive": _fallback_fish_tts_directive({}),
            "fish_voice_prompt": "",
            "reason": "LLM 调用失败", "confidence": 0.0, "warnings": [],
            "language": "zh-CN", "user_overrides": {}, "locked_fields": [],
            "provider_preference": None, "provider_hints": {},
        }


def _fallback_sample_variants(profile: dict) -> list[str]:
    return [
        "别靠近我。那不是你该碰的东西。",
        "我没有在等谁，只是这里比较安静。",
        "如果你一定要留下，就别问我从前的事。",
    ]


def _fallback_reference_strategy(profile: dict) -> str:
    gender = str(profile.get("gender_tone") or "neutral")
    age = str(profile.get("voice_age") or "adult")
    timbre = str(profile.get("timbre") or "soft")
    return (
        f"优先匹配 Fish reference_id：{age}, {gender}, {timbre}, restrained/calm。"
        "prompt 只负责表演，不保证改变音色本体。"
    )


def _fallback_fish_tts_directive(profile: dict) -> dict:
    speed = str(profile.get("speed") or "slow").lower()
    volume = str(profile.get("volume") or "low").lower()
    emotion = str(profile.get("emotion_level") or "restrained").lower()
    colors = [str(c).lower() for c in profile.get("emotional_color", []) or []]

    tags = ["calm"]
    if "sad" in colors or "melancholic" in colors or "lonely" in colors:
        tags.append("sad")
    if volume == "low":
        tags.append("whispering")

    speed_value = {
        "very_slow": 0.76,
        "slow": 0.84,
        "medium": 0.96,
        "fast": 1.08,
        "very_fast": 1.16,
    }.get(speed, 0.88)
    volume_value = {"low": -5, "medium": -1, "strong": 2}.get(volume, -3)

    if emotion in ("flat", "restrained"):
        tags = tags[:2]

    return {
        "emotion_tags": tags[:3],
        "prosody": {"speed": speed_value, "volume": volume_value},
        "pause_plan": "short_sentences_with_one_long_pause",
        "text_prefix": " ".join(f"({tag})" for tag in tags[:2]),
        "performance_note": "压低情绪，不要哭腔；句子短，停顿明确，像是在把人推远。",
        "avoid": ["不要撒娇", "不要活泼", "不要夸张哭腔"],
    }


def _legacy_fish_voice_prompt(profile: dict) -> str:
    directive = profile.get("fish_tts_directive") or _fallback_fish_tts_directive(profile)
    return directive.get("text_prefix", "")
