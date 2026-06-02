"""Image Prompt Director — v0.7

Translates Visual Identity Profile into structured image generation prompts.
Separates positive/negative prompts, style guidance, and aspect ratio recommendations.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

DIRECTOR_PROMPT = """你是 Image Prompt Director（图像提示词导演）。将视觉画像转化为可直接送入 AI 生图的正负面 prompt。

## 输出格式（严格 JSON）：
{
  "positive_prompt": "完整的英文正面 prompt",
  "negative_prompt": "英文负面 prompt",
  "aspect_ratio": "推荐宽高比（如 1:1, 3:4, 16:9）",
  "style_notes": "风格说明",
  "variations": [
    {"style": "anime", "positive_prompt": "...", "negative_prompt": "..."},
    {"style": "cinematic", "positive_prompt": "...", "negative_prompt": "..."},
    {"style": "flat", "positive_prompt": "...", "negative_prompt": "..."}
  ],
  "seed_hint": -1
}

规则：
- positive_prompt 包含角色外貌、服装、姿态、光线、背景、质量词
- negative_prompt 包含常见排除项
- variations 为三种不同风格变体
"""


async def direct_image_prompt(draft: OCDraft, visual_profile: dict | None = None) -> dict:
    """Generate structured image prompts from character draft + visual profile."""
    context = _draft_context(draft)
    if visual_profile:
        import json
        context += f"\n\n视觉画像:\n{json.dumps(visual_profile, ensure_ascii=False)}"

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": f"角色信息:\n{context}\n\n生成图像 prompt。"}],
            system_prompt=DIRECTOR_PROMPT,
            agent="export",
        )
        return result
    except Exception:
        return {"positive_prompt": "", "negative_prompt": "low quality, blurry", "variations": [], "aspect_ratio": "1:1"}


def _draft_context(draft: OCDraft) -> str:
    lines = []
    if draft.name: lines.append(f"名字: {draft.name}")
    if draft.gender: lines.append(f"性别: {draft.gender}")
    if draft.appearance: lines.append(f"外貌: {draft.appearance}")
    if draft.personality: lines.append(f"性格: {', '.join(draft.personality)}")
    if draft.core_concept: lines.append(f"核心: {draft.core_concept}")
    if draft.themes: lines.append(f"主题: {', '.join(draft.themes)}")
    return "\n".join(lines)
