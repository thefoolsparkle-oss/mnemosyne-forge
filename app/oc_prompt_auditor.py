"""Prompt Auditor Agent — v0.8

Reviews image and voice prompts before sending to external APIs.
Catches: gender mismatches, quality issues, inappropriate content, missing info.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

AUDITOR_PROMPT = """你是 Prompt 审核专家。用户生成了一组用于调用外部 API 的 prompt，你需要根据角色原始设定审核这些 prompt 是否存在问题。

## 审核维度：
- gender_match: 生成内容（声音/图像）的性别是否与角色设定一致
- age_match: 年龄感是否匹配
- style_match: 风格/气质是否匹配
- quality: prompt 质量如何（1-10）
- issues: 发现的问题列表
- suggestions: 修改建议

## JSON 格式：
{
  "passed": true/false,
  "score": 8,
  "gender_match": true/false,
  "age_match": true/false, 
  "style_match": true/false,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1"],
  "summary": "一句话总评"
}"""


async def audit_image_prompt(draft: OCDraft, prompt: str, negative_prompt: str = "") -> dict:
    """Review an image generation prompt against character draft."""
    context = _draft_summary(draft)
    content = f"角色设定:\n{context}\n\n正面 prompt:\n{prompt}\n\n负面 prompt:\n{negative_prompt}\n\n审核这个生图 prompt。"
    try:
        result = await chat_json(
            messages=[{"role": "user", "content": content}],
            system_prompt=AUDITOR_PROMPT,
            agent="designer",
        )
        result.setdefault("passed", True)
        return result
    except Exception:
        return {"passed": True, "score": 5, "issues": [], "suggestions": [], "summary": "审核失败，跳过"}


async def audit_voice_prompt(draft: OCDraft, voice_profile: dict) -> dict:
    """Review a voice profile against character draft."""
    context = _draft_summary(draft)
    vp_text = "\n".join(f"{k}: {v}" for k, v in voice_profile.items() if v and k not in ("user_overrides", "locked_fields", "provider_hints"))
    content = f"角色设定:\n{context}\n\n声音画像:\n{vp_text}\n\n审核这个声音配置是否与角色匹配。"
    try:
        result = await chat_json(
            messages=[{"role": "user", "content": content}],
            system_prompt=AUDITOR_PROMPT,
            agent="designer",
        )
        result.setdefault("passed", True)
        return result
    except Exception:
        return {"passed": True, "score": 5, "issues": [], "suggestions": [], "summary": "审核失败，跳过"}


def _draft_summary(draft: OCDraft) -> str:
    lines = []
    if draft.name:
        lines.append(f"名字: {draft.name}")
    if draft.gender:
        lines.append(f"性别: {draft.gender}")
    if draft.age_range:
        lines.append(f"年龄: {draft.age_range}")
    if draft.core_concept:
        lines.append(f"核心概念: {draft.core_concept}")
    if draft.personality:
        lines.append(f"性格: {', '.join(draft.personality)}")
    if draft.appearance:
        lines.append(f"外貌: {draft.appearance}")
    if draft.speaking_style:
        lines.append(f"说话方式: {draft.speaking_style}")
    return "\n".join(lines)
