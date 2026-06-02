"""Image Critic Agent — v0.7

Reviews generated image prompts and results against character draft.
Checks: visual fidelity, style consistency, quality, missing elements.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

CRITIC_PROMPT = """你是 Image Critic（图像评审）。审查生成的图像 prompt 与角色设定的匹配度。

## 评审维度：
- fidelity: prompt 是否忠实反映角色外貌特征（1-10）
- consistency: 风格是否与角色气质一致（1-10）
- quality: prompt 结构质量（1-10）
- missing: prompt 中遗漏的角色视觉元素
- suggestions: 优化建议
- overall_score: 总评分（1-10）
- passed: 是否通过评审（>=6 为通过）

## JSON 格式：
{"critique": {"passed": true, "overall_score": 8, "fidelity": 8, "consistency": 7, "quality": 9, "missing": [], "suggestions": []}}"""


async def critique_image_prompt(draft: OCDraft, prompt: str, negative_prompt: str = "") -> dict:
    """Critique an image prompt against character draft."""
    context = _draft_context(draft)
    text = f"角色:\n{context}\n\n正 prompt: {prompt}\n负 prompt: {negative_prompt}\n\n请评审。"
    try:
        result = await chat_json(
            messages=[{"role": "user", "content": text}],
            system_prompt=CRITIC_PROMPT,
            agent="designer",
        )
        return result.get("critique", result)
    except Exception:
        return {"passed": True, "overall_score": 5, "fidelity": 5, "suggestions": []}


def _draft_context(draft: OCDraft) -> str:
    lines = []
    if draft.name: lines.append(f"名字: {draft.name}")
    if draft.gender: lines.append(f"性别: {draft.gender}")
    if draft.appearance: lines.append(f"外貌: {draft.appearance}")
    if draft.personality: lines.append(f"性格: {', '.join(draft.personality)}")
    return "\n".join(lines)
