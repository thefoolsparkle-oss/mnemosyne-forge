"""Dialogue Director Agent — v0.10

Analyzes a dialogue turn from the character's perspective.
Takes: OC draft + user line + scene context
Outputs: scene state, user intent, character inner reaction, relationship delta,
         beat goal, response mode, and voice direction parameters.

Does NOT generate dialogue text — that is the Line Writer's job.
Does NOT tag performance for TTS — that is the Performance Director's job.

The Director answers: "Why does this character respond this way, right now?"
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

DIRECTOR_PROMPT = """你是 Dialogue Director（对话导演）。分析一次对话回合，从角色的视角理解发生了什么。

## 你的职责：
分析以下内容——不要产出台词，不要写角色该说什么，只分析场景和反应：

1. scene_state：当前场景下的状态（天气/地点/氛围/物理动作）
2. user_intent：用户这句话在试探什么、想要什么、传达什么
3. character_inner_reaction：角色听到这句话时内心的第一反应（不是她说什么，是她感觉到什么）
4. relationship_delta：和用户的关系在这一次对话中怎么变了（靠拢/推开/放松/更戒备/无变化）
5. beat_goal：这一轮角色回复想达到什么（阻止/接纳/回避/反问/沉默/讽刺/解释/推开）
6. response_mode：回应的方式（短句/长句/反问/沉默/命令/回避/碎片化）
7. voice_direction：如果要说出来，声音该是什么感觉
   - emotion: calm/sad/cold/tired/angry/gentle/restrained
   - pause: where the pause should be (before_speaking/after_warning/mid_sentence/none)
   - volume: whisper/soft/normal/loud
   - speed: slow/normal/fast

## 输出格式：
{
  "scene_state": "20字以内",
  "user_intent": "10字以内",
  "character_inner_reaction": "30字以内",
  "relationship_delta": "靠拢/推开/放松/更戒备/无变化",
  "beat_goal": "20字以内",
  "response_mode": "15字以内",
  "voice_direction": {
    "emotion": "cold",
    "pause": "after_warning",
    "volume": "soft",
    "speed": "slow"
  }
}

## 分析原则：
- 不要预设角色会说什么——你做的是心理分析，不是台词生成
- 根据角色性格推断她的反应，不要假设她"应该"友善或"应该"回应
- relationship_delta 必须基于角色性格和当前关系氛围
- 冷淡的角色听到关怀不会立刻变温柔——可能是更戒备
- 声音方向要比情绪标签更具体：restrained 不等于 calm"""


async def direct_beat(
    draft: OCDraft,
    user_line: str,
    scene_context: str = "",
    relationship_context: str = "",
    history_context: str = "",
) -> dict:
    """Analyze a dialogue turn and produce a directing beat.

    Returns the full beat analysis dict with scene_state, user_intent,
    character_inner_reaction, relationship_delta, beat_goal, response_mode,
    and voice_direction.
    """
    char_context = _draft_context(draft)

    prompt_parts = [f"## 角色:\n{char_context}"]
    if scene_context:
        prompt_parts.append(f"## 场景:\n{scene_context}")
    if relationship_context:
        prompt_parts.append(f"## 当前关系:\n{relationship_context}")
    if history_context:
        prompt_parts.append(f"## 最近对话:\n{history_context}")
    prompt_parts.append(f"## 用户这一轮说:\n{user_line}")
    prompt_parts.append(f"\n请从角色视角分析这个对话回合。")

    prompt = "\n\n".join(prompt_parts)

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=DIRECTOR_PROMPT,
            agent="designer",
        )
        return result
    except Exception:
        return _fallback_beat(draft, user_line)


def _draft_context(draft: OCDraft) -> str:
    parts = []
    if draft.name:
        parts.append(f"名字: {draft.name}")
    if draft.gender:
        parts.append(f"性别: {draft.gender}")
    if draft.core_concept:
        parts.append(f"核心: {draft.core_concept}")
    if draft.personality:
        parts.append(f"性格: {', '.join(draft.personality)}")
    if draft.speaking_style:
        parts.append(f"说话方式: {draft.speaking_style}")
    if draft.background:
        parts.append(f"背景: {draft.background[:200]}")
    if draft.scenario:
        parts.append(f"场景设定: {draft.scenario[:100]}")
    return "\n".join(parts)


def _fallback_beat(draft: OCDraft, user_line: str) -> dict:
    personality = draft.personality or []
    is_cold = any(w in "".join(personality) for w in ["冷", "疏离", "戒备", "淡漠"])

    return {
        "scene_state": draft.scenario or "未知场景",
        "user_intent": "交流",
        "character_inner_reaction": "保持距离" if is_cold else "稍有回应",
        "relationship_delta": "无变化" if is_cold else "微弱放松",
        "beat_goal": "简短回应" if is_cold else "温和回应",
        "response_mode": "短句，不多说" if is_cold else "短句",
        "voice_direction": {
            "emotion": "cold" if is_cold else "calm",
            "pause": "before_speaking",
            "volume": "soft",
            "speed": "slow",
        },
    }
