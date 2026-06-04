"""Image Critic Agent — v0.9

Two-tier critique system:
- Prompt Critic: LLM reviews the image prompt against character draft (current active tier).
- Result Critic: visual-model review of the actual generated image (stub for future, requires vision model API).

Note for v0.9: only prompt-level critique is active. The `/api/sessions/{session_id}/image-critique`
endpoint critiques the prompt, NOT the rendered image. Result-image critique will be activated
when a vision model (GPT-4V / Claude Vision / Gemini) or dedicated image quality API is integrated.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

PROMPT_CRITIC_SYSTEM = """你是 Image Prompt Critic（图像 Prompt 评审）。审查生成的图像 prompt 与角色设定的匹配度。

注意：你审查的是文字 prompt，不是最终渲染图。审查 prompt 中是否：
- 反映了角色外貌特征（发型、瞳色、体型、服装）
- 体现了角色气质和情绪氛围
- 包含了关键标志物或场景元素
- 没有添加与角色矛盾的元素

评审维度：
- fidelity: prompt 是否忠实反映角色外貌特征（1-10）
- consistency: 风格是否与角色气质一致（1-10）
- quality: prompt 结构质量（1-10）
- missing: prompt 中遗漏的角色视觉元素
- suggestions: 优化建议
- overall_score: 总评分（1-10）
- passed: 是否通过评审（>=6 为通过）

JSON 格式：
{"critique": {"passed": true, "overall_score": 8, "fidelity": 8, "consistency": 7, "quality": 9, "missing": [], "suggestions": []}}"""

IMAGE_RESULT_CRITIC_SYSTEM = """你是 Image Result Critic（图像结果评审）。根据角色设定审核已生成的图像。

评审维度：
- character_match: 图片中的人物是否像角色（发型、瞳色、体型、服装、标志物）
- mood_match: 气质氛围是否符合角色（表情、光线、色调、构图）
- prop_check: 关键标志物是否出现在图中
- gender_match: 性别是否匹配
- age_match: 年龄感是否正确
- style_match: 画风是否符合指定风格
- drift_flags: 跑偏警告（如：变成时尚大片、街头风格、性感化、二次元萌化等）
- retry_instructions: 如需重试，应如何调整 prompt

JSON 格式：
{"critique": {..., "drift_flags": [], "needs_retry": false, "retry_instructions": ""}}"""


async def critique_image_prompt(draft: OCDraft, prompt: str, negative_prompt: str = "") -> dict:
    """Critique an image prompt (text) against character draft.

    THIS IS PROMPT-LEVEL CRITIQUE ONLY. It reviews the text prompt, not the rendered image.
    For result-image critique, use critique_image_result() when a vision model is available.
    """
    context = _draft_context(draft)
    text = f"角色:\n{context}\n\n正 prompt: {prompt}\n负 prompt: {negative_prompt}\n\n请评审。"
    try:
        result = await chat_json(
            messages=[{"role": "user", "content": text}],
            system_prompt=PROMPT_CRITIC_SYSTEM,
            agent="designer",
        )
        return result.get("critique", result)
    except Exception:
        return {"passed": True, "overall_score": 5, "fidelity": 5, "suggestions": [], "note": "prompt_only_critique"}


async def critique_image_result(
    draft: OCDraft, image_path: str, prompt: str = "", negative_prompt: str = ""
) -> dict:
    """Critique a generated image against character draft using a vision model.

    CURRENT STATUS: STUB. Requires a multimodal vision model API (GPT-4V / Claude Vision / Gemini).
    When connected, this will send the image and draft to the model for visual review.

    Until then, callers should fall back to prompt-level critique (critique_image_prompt).
    """
    return {
        "passed": True,
        "overall_score": 0,
        "note": "result_image_critique_not_available",
        "message": "Result-image critique requires a vision model API. "
                   "Current critique is prompt-level only via critique_image_prompt().",
        "drift_flags": [],
        "needs_retry": False,
    }


def _draft_context(draft: OCDraft) -> str:
    lines = []
    if draft.name: lines.append(f"名字: {draft.name}")
    if draft.gender: lines.append(f"性别: {draft.gender}")
    if draft.appearance: lines.append(f"外貌: {draft.appearance}")
    if draft.personality: lines.append(f"性格: {', '.join(draft.personality)}")
    return "\n".join(lines)
