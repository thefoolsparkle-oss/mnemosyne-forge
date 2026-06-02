"""Visual Identity Agent — v0.7

Analyzes OCDraft to extract a structured visual profile.
Feeds into Image Prompt Director for consistent image generation.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

VISUAL_IDENTITY_PROMPT = """你是 Visual Identity Agent（视觉形象分析师）。根据角色设定，提取结构化的视觉画像。

## 分析维度：
- color_palette: 主色调 + 辅助色（如 ["黑","金","深红"]）
- face: 脸型/五官特征（如 "瓜子脸，狭长眼眸，薄唇"）
- hair: 发型发色（如 "黑色长发及腰，刘海遮右眼"）
- eyes: 眼睛细节（如 "金色瞳孔，眼下有淡淡阴影"）
- build: 体型（如 "纤细，身高168cm"）
- clothing: 服装风格 + 具体描述（如 "深色风衣，内搭黑色高领，银色挂坠"）
- accessories: 配饰（如 ["银色项链"，"右手无名指古银戒指"]）
- posture: 常用姿态（如 "低头，双手插兜，身体微微后倾"）
- expression: 表情特点（如 "冷淡，嘴角微垂，目光涣散像是看着很远的地方"）
- atmosphere: 整体氛围（如 "冷色调城市夜景，霓虹灯光，微雨"）
- style_keywords: 风格关键词列表（如 ["anime","portrait","cinematic","melancholic"]）
- visual_summary: 一句话概括视觉印象
- confidence: 0-1
- missing: 缺失的视觉信息列表

## JSON 格式：
{"visual_profile": {...}}

只返回 JSON。"""


def _draft_context(draft: OCDraft) -> str:
    lines = []
    if draft.name:
        lines.append(f"名字: {draft.name}")
    if draft.gender:
        lines.append(f"性别: {draft.gender}")
    if draft.age_range:
        lines.append(f"年龄: {draft.age_range}")
    if draft.appearance:
        lines.append(f"外貌: {draft.appearance}")
    if draft.personality:
        lines.append(f"性格: {', '.join(draft.personality)}")
    if draft.core_concept:
        lines.append(f"核心: {draft.core_concept}")
    if draft.background:
        lines.append(f"背景: {draft.background}")
    if draft.themes:
        lines.append(f"主题: {', '.join(draft.themes)}")
    return "\n".join(lines)


async def analyze_visual_identity(draft: OCDraft) -> dict:
    """Generate a visual identity profile from character draft."""
    context = _draft_context(draft)
    if not context:
        context = "(角色信息不足)"

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": f"角色设定:\n{context}\n\n提取视觉画像。"}],
            system_prompt=VISUAL_IDENTITY_PROMPT,
            agent="designer",
        )
        return result.get("visual_profile", result)
    except Exception:
        return {
            "visual_summary": "分析失败",
            "missing": ["all"],
            "confidence": 0.0,
        }
