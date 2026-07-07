"""Image generation module.

Generates character images via pluggable providers (Stability, OpenAI,
Pollinations, custom). Supports prompt building and actual image generation.
"""

from __future__ import annotations

from typing import Any

from .config import get_config
from .image_providers import get_provider
from .llm_client import chat
from .oc_models import OCDraft

IMAGE_PROMPT_SYSTEM = """你是一个角色立绘 prompt 工程师。根据角色设定，生成适合 Stable Diffusion 的英文 prompt。

## 要求：
- 用英文编写
- 包含：角色外貌、服装风格、姿态、光线、背景氛围
- 加入风格关键词（anime style, portrait, detailed, high quality）
- 加入质量词（masterpiece, best quality）
- 加入负面提示中常见的排除项到正面提示的否定形式
- 不要包含 NSFW 内容
- 保持 50-100 个词

输出：只返回 prompt 文本，不加引号。"""


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
        parts = []
        if draft.name:
            parts.append(draft.name)
        if draft.gender:
            parts.append(draft.gender)
        if draft.appearance:
            parts.append(draft.appearance)
        base = ", ".join(parts) if parts else "character"
        return f"masterpiece, best quality, {style}, {base}, detailed, high quality"


async def build_image_variation_prompt(
    draft: OCDraft,
    locked_prompt: str,
    variation: str,
    style: str = "anime portrait",
) -> str:
    """Build a prompt variant that preserves the locked visual canon."""
    context = _draft_visual(draft)
    anchor = locked_prompt.strip() if locked_prompt else await build_image_prompt(draft, style)
    instruction = f"""Character visual canon:
{anchor}

Character draft:
{context}

Variation request:
{variation}

Rewrite a Stable Diffusion prompt in English. Preserve the same character identity, face shape, hair, eye color, outfit anchors, silhouette, age impression, and overall art style. Change only the requested pose/expression/composition details. Return prompt text only."""

    try:
        prompt = await chat(
            messages=[{"role": "user", "content": instruction}],
            system_prompt=IMAGE_PROMPT_SYSTEM,
            agent="export",
        )
        return prompt.strip()
    except Exception:
        return (
            f"{anchor}, same character, consistent face, consistent hairstyle, consistent eyes, "
            f"consistent outfit, {variation}, {style}, masterpiece, best quality"
        )


async def generate_character_image(
    draft: OCDraft,
    style: str = "anime portrait",
    prompt: str | None = None,
    negative_prompt: str | None = None,
    provider_name: str | None = None,
    **provider_kwargs: Any,
) -> dict[str, Any]:
    """Generate a character image using the configured image provider.

    Returns {ok, image_path, prompt, negative_prompt, seed, error}
    """
    cfg = get_config()
    img_cfg = cfg.get("image", {})
    provider_name = provider_name or img_cfg.get("provider", "pollinations")

    if not draft.appearance:
        return {"ok": False, "error": "角色外貌信息不足，请先在草稿中补充外貌描述（发色、瞳色、服装、气质等）"}

    prompt = prompt or await build_image_prompt(draft, style)
    if not prompt:
        return {"ok": False, "error": "角色外貌信息不足，无法生成图片"}

    negative_prompt = negative_prompt or "low quality, blurry, ugly, deformed, bad anatomy, extra fingers, missing fingers, watermark, text, logo, signature"

    try:
        provider = get_provider(provider_name)
        return await provider.generate(
            draft,
            style,
            prompt,
            negative_prompt,
            **provider_kwargs,
        )
    except Exception as e:
        return {"ok": False, "error": f"生图失败: {e}", "prompt": prompt, "negative_prompt": negative_prompt}


def _normalize_character_style(style: str) -> str:
    """Keep first-pass OC candidates in useful character-portrait styles."""
    raw = (style or "").strip()
    lowered = raw.lower()
    if "flat" in lowered or "illustration" in lowered:
        return "high-detail game character concept art, polished anime rendering, expressive eyes"
    if lowered in {"anime", "anime portrait"}:
        return "premium anime character key visual, detailed face, layered painterly lighting"
    if "cinematic" in lowered:
        return "anime character portrait, cinematic rim light, dramatic library atmosphere"
    return raw or "premium anime character key visual, detailed face, layered painterly lighting"
