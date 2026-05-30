"""Guide Agent — generates natural Chinese follow-up questions.

Guides the user through character creation stages with warm, professional tone.
Never exposes internal field names. Gives directional choices when possible.
"""

from __future__ import annotations

from .llm_client import chat
from .oc_models import OCDraft, ChatMessage

GUIDE_SYSTEM_PROMPT = """你是造枝（Mnemosyne Forge）的角色创作引导者。你正在采访一位想要创造原创角色（OC）的用户。你的任务是自然地引导用户补全角色设定。

## 你的风格
- 说话自然、温和、专业，像一个有经验的角色创作顾问
- 每次只问一个小问题，不要一口气问太多
- 如果已经确认了一些设定，先简短总结一下（1-2 句）
- 优先给用户 2-3 个可选方向，而不是只问开放性问题
- 不能暴露内部字段名（如 "core_concept"、"personality" 等）
- 不能使用模板化的句式，每次回复要有变化
- 节奏感：不要急着推进，让用户有发挥空间

## 禁忌
- 不要替用户做决定
- 不要在用户没提的情况下突然引入奇幻/科幻元素
- 不要评价用户的创意好坏，只帮助完善
- 不要问"你还想补充什么吗"这种空洞问题

## 输出要求
只输出你要对用户说的话，不要加任何前缀或格式标记。"""

# Stage-specific guidance (used to construct the prompt, not rigid templates)
STAGE_GUIDANCE = {
    "core_concept": "现在阶段是核心概念。用户刚有了一个角色的初步想法。请引导用户细化这个角色的核心气质：她/他给人的第一印象是什么？有什么让人过目不忘的特质？",
    "personality": "现在阶段是性格塑造。核心概念已确定，请引导用户展开角色的性格层次：表面性格 vs 内心真实？有什么矛盾或隐藏的一面？在压力下会怎样？",
    "appearance": "现在阶段是外貌描述。请引导用户想象角色的外观：有什么标志性的外貌特征？穿衣风格？在人群中能被一眼认出的理由？",
    "background": "现在阶段是背景故事。请引导用户回忆角色经历：什么关键事件塑造了今天的她/他？成长过程中的转折点？",
    "abilities": "现在阶段是能力设定。请引导用户思考角色的能力：擅长什么？有什么过人之处？同时也可以问问弱点和局限。",
    "relationships": "现在阶段是人际关系。请引导用户想想角色身边的人：谁是重要的人？和这些人的关系是怎样的？",
    "speaking_style": "现在阶段是说话方式。请引导用户感受角色的语气：她/他平时怎么说话？口头禅？语速快慢？用词特点？",
    "scenario": "现在阶段是使用场景。请引导用户设想：角色通常出现在什么情境中？在做什么？和你（用户）的关系是什么？",
    "opening": "现在阶段是开场设计。请引导用户构思角色开口的第一句话，或者给几个开场白选项让用户选择。",
    "final_review": "现在是最终确认阶段。设定已经比较完整了，请帮用户做一次全面总结，并询问是否有需要调整的地方。",
}


def _format_chat_context(chat_history: list[ChatMessage]) -> str:
    """Format recent chat history for the guide prompt."""
    lines = []
    for msg in chat_history[-6:]:
        role = "用户" if msg.role == "user" else "你"
        lines.append(f"[{role}]: {msg.content}")
    return "\n".join(lines)


def _format_draft_summary(draft: OCDraft) -> str:
    """Create a concise summary of what's been filled."""
    parts = []
    if draft.name:
        parts.append(f"名字: {draft.name}")
    if draft.core_concept:
        parts.append(f"核心概念: {draft.core_concept}")
    if draft.personality:
        parts.append(f"性格: {', '.join(draft.personality)}")
    if draft.gender:
        parts.append(f"性别: {draft.gender}")
    if draft.age_range:
        parts.append(f"年龄: {draft.age_range}")
    if draft.appearance:
        a = draft.appearance
        parts.append(f"外貌: {a[:100]}{'...' if len(a) > 100 else ''}")
    if draft.background:
        b = draft.background
        parts.append(f"背景: {b[:100]}{'...' if len(b) > 100 else ''}")
    return "\n".join(parts) if parts else "尚未确认任何设定"


async def generate_guide_message(
    draft: OCDraft,
    current_stage: str,
    missing_fields: list[str],
    chat_history: list[ChatMessage],
    designer_notes: str = "",
    search_inspiration: str = "",
) -> str:
    """Generate the next natural-language guide message for the user."""
    stage_guidance = STAGE_GUIDANCE.get(current_stage, STAGE_GUIDANCE["core_concept"])
    draft_summary = _format_draft_summary(draft)
    chat_context = _format_chat_context(chat_history)

    user_prompt = f"""## 角色当前设定：
{draft_summary}

## 当前创作阶段：
{stage_guidance}

## 还需要补充的方面：
{', '.join(missing_fields) if missing_fields else '基本完整'}

## 最近对话：
{chat_context}

{f"## 设定分析备注：{designer_notes}" if designer_notes else ""}
{f"## 搜索素材灵感：{search_inspiration}" if search_inspiration else ""}

请根据当前阶段和已有设定，生成一句自然的追问来引导用户继续创作。"""

    response = await chat(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=GUIDE_SYSTEM_PROMPT,
        agent="guide",
    )
    return response.strip()
