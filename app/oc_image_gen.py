"""Image generation module — v0.7

Builds image generation prompts from character drafts.
Actual image generation is provider-agnostic — configure in config.yaml.
"""

from __future__ import annotations

from .config import get_config
from .llm_client import chat
from .oc_models import OCDraft

IMAGE_PROMPT_SYSTEM = """你是一个角色立绘 prompt 工程师。根据角色设定，生成适合生图模型的英文 prompt。

## 要求：
- 用英文编写，适合 Stable Diffusion / DALL-E / Midjourney
- 包含：角色外貌、服装风格、姿态、光线、背景氛围
- 加入风格关键词（anime style, portrait, detailed, etc.）
- 不要包含 NSFW 内容
- 保持 50-100 个词

输出：直接返回 prompt 文本。"""


async def build_image_prompt(draft: OCDraft, style: str = "anime portrait") -> str:
    """Generate an image prompt from the character draft."""
    context = _draft_visual(draft)
    if not context:
        return ""

    try:
        prompt = await chat(
            messages=[{"role": "user", "content": f"角色信息：\n{context}\n\n风格：{style}"}],
            system_prompt=IMAGE_PROMPT_SYSTEM,
            agent="export",
        )
        return prompt.strip()
    except Exception:
        return _fallback_prompt(draft, style)


def _draft_visual(draft: OCDraft) -> str:
    parts = []
    if draft.name:
        parts.append(f"Name: {draft.name}")
    if draft.gender:
        parts.append(f"Gender: {draft.gender}")
    if draft.age_range:
        parts.append(f"Age: {draft.age_range}")
    if draft.appearance:
        parts.append(f"Appearance: {draft.appearance}")
    if draft.personality:
        parts.append(f"Personality: {', '.join(draft.personality)}")
    if draft.core_concept:
        parts.append(f"Concept: {draft.core_concept}")
    return "\n".join(parts)


def _fallback_prompt(draft: OCDraft, style: str) -> str:
    """Simple prompt builder without LLM."""
    name = draft.name or "character"
    gender = draft.gender or ""
    appearance = draft.appearance or ""
    return f"{style} of {name}, {gender}, {appearance}".strip(", ")


async def generate_character_image(
    draft: OCDraft,
    style: str = "anime portrait",
) -> dict:
    """Generate a character image.

    Returns the prompt. Actual image generation requires a provider
    configured in config.yaml (image.provider + image.api_key_env).
    """
    cfg = get_config()
    img_cfg = cfg.get("image", {})
    provider = img_cfg.get("provider", "")
    api_key_env = img_cfg.get("api_key_env", "")

    prompt = await build_image_prompt(draft, style)
    if not prompt:
        return {"ok": False, "error": "No visual information in draft"}

    if not provider or not api_key_env:
        return {
            "ok": False,
            "error": f"Image provider not configured. Set 'image.provider' and 'image.api_key_env' in config.yaml.\n\nGenerated prompt:\n{prompt}",
            "prompt": prompt,
        }

    return {
        "ok": False,
        "error": f"Image generation via '{provider}' not yet implemented. Configure provider and API key.\n\nGenerated prompt:\n{prompt}",
        "prompt": prompt,
        "provider": provider,
    }
