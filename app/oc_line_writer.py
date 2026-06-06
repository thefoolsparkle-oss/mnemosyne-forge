"""Line Writer Agent — v0.10

Generates character-specific dialogue lines for voice sampling.
Takes OC draft → writes realistic dialogue lines in character's voice.
NOT narration, NOT bio reading, NOT stock TTS test sentences.

Feeds into Dialogue Performance Agent for per-unit TTS settings.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

LINE_WRITER_PROMPT = """你是 Line Writer（台词作者）。根据角色设定写几句这个角色真正会说出来的话。

## 规则：
- 每句必须是角色台词，不是旁白、不是角色简介、不是试音句
- 每句自带场景上下文和情绪标注
- 台词长度 10-30 字
- 不要写"你好""请问""谢谢"等通用句
- 不要写"我是谁谁谁"那种自我介绍
- 要像从一段真实对话中截取出来的

## 输出格式：
{
  "lines": [
    {
      "text": "角色说的话",
      "context": "什么情况下说的（10字以内）",
      "emotion": "calm/sad/cold/tired/angry/gentle/restrained",
      "to_whom": "对谁说（用户/陌生人/自己/朋友/敌人）"
    }
  ],
  "writer_note": "这一批台词的写作方向"
}

## 写作要求：
- 角色性格决定句式：冷淡的不用感叹号，温柔的可以有省略号，暴躁的短句多
- 每句之间要有情绪、场景和对话对象的差异
- 3-5 句即可"""


async def write_lines(draft: OCDraft, count: int = 4) -> dict:
    """Generate OC-specific dialogue lines for voice sampling.

    Returns {lines: [{text, context, emotion, to_whom}], writer_note}.
    """
    context = _draft_to_context(draft)

    prompt = (
        f"{context}\n\n"
        f"请为这个角色写 {count} 句不同场景、不同情绪的台词。"
        f"不要说角色介绍，只写她/他真正会说的话。"
    )

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=LINE_WRITER_PROMPT,
            agent="designer",
        )
        lines = result.get("lines", [])
        if not lines:
            raise ValueError("Line Writer returned no lines")
        return result
    except Exception:
        return _fallback_lines(draft)


def _draft_to_context(draft: OCDraft) -> str:
    parts = []
    if draft.name:
        parts.append(f"角色名: {draft.name}")
    if draft.gender:
        parts.append(f"性别: {draft.gender}")
    if draft.age_range:
        parts.append(f"年龄段: {draft.age_range}")
    if draft.core_concept:
        parts.append(f"核心概念: {draft.core_concept}")
    if draft.personality:
        parts.append(f"性格: {', '.join(draft.personality)}")
    if draft.speaking_style:
        parts.append(f"说话方式: {draft.speaking_style}")
    if draft.background:
        parts.append(f"背景: {draft.background[:200]}")
    if draft.scenario:
        parts.append(f"使用场景: {draft.scenario[:100]}")
    return "\n".join(parts)


def _fallback_lines(draft: OCDraft) -> dict:
    name = draft.name or "角色"
    personality = draft.personality or []
    is_cold = any(w in "".join(personality) for w in ["冷", "疏离", "戒备", "淡漠"])
    is_gentle = any(w in "".join(personality) for w in ["温柔", "安静", "内向", "细腻"])
    is_intense = any(w in "".join(personality) for w in ["热", "激烈", "愤怒", "强"])

    if is_cold:
        lines = [
            {"text": "别靠近我。那不是你该碰的东西。", "context": "有人靠近她的私人物品", "emotion": "cold", "to_whom": "陌生人"},
            {"text": "我没有在等谁，只是这里比较安静。", "context": "被问及为什么独自待着", "emotion": "restrained", "to_whom": "用户"},
            {"text": "如果你一定要留下，就别问我从前的事。", "context": "有人坚持要陪伴她", "emotion": "tired", "to_whom": "用户"},
            {"text": "那架琴……坏了很久了。", "context": "被问到角落里的旧钢琴", "emotion": "sad", "to_whom": "用户"},
        ]
    elif is_gentle:
        lines = [
            {"text": "你来了啊……我刚好泡了茶。", "context": "等待的人终于来了", "emotion": "gentle", "to_whom": "朋友"},
            {"text": "不用着急，慢慢说，我在听。", "context": "对方很焦虑或激动", "emotion": "calm", "to_whom": "用户"},
            {"text": "这本书我很喜欢，你拿去看吧。", "context": "分享自己喜欢的东西", "emotion": "gentle", "to_whom": "朋友"},
            {"text": "有些事……不是不想说，是说了也没用。", "context": "被追问过去", "emotion": "sad", "to_whom": "用户"},
        ]
    elif is_intense:
        lines = [
            {"text": "你以为你是谁？这里轮不到你说话。", "context": "被挑战或冒犯", "emotion": "angry", "to_whom": "陌生人"},
            {"text": "我不会再信任何人了。一次就够了。", "context": "被要求信任某人", "emotion": "intense", "to_whom": "用户"},
            {"text": "走。现在就走。别让我说第二遍。", "context": "想保护对方远离危险", "emotion": "intense", "to_whom": "用户"},
            {"text": "这个仇，我不会忘。", "context": "独处时回忆起过去", "emotion": "cold", "to_whom": "自己"},
        ]
    else:
        lines = [
            {"text": "别靠近我。那不是你该碰的东西。", "context": "有人靠近她的私人物品", "emotion": "cold", "to_whom": "陌生人"},
            {"text": "我没有在等谁，只是这里比较安静。", "context": "被问及为什么独自待着", "emotion": "restrained", "to_whom": "用户"},
            {"text": "你来了啊……我以为你不会来了。", "context": "等待的人终于来了", "emotion": "gentle", "to_whom": "朋友"},
            {"text": "有些事……不是不想说，是说了也没用。", "context": "被追问过去", "emotion": "sad", "to_whom": "用户"},
        ]

    return {
        "lines": lines,
        "writer_note": f"fallback: 基于 {name} 性格关键词自动生成的台词模板",
    }
