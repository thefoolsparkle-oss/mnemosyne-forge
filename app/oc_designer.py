"""Designer Agent — extracts character settings from user messages.

Calls the LLM to parse natural language into structured OCDraft updates.
Respects locked_fields and avoids hallucinating unconfirmed details.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft, ChatMessage

DESIGNER_SYSTEM_PROMPT = """你是角色设定提取器。用户会给你一段关于原创角色的描述，你需要从中提取结构化信息。

## 你必须：
1. **core_concept 必须填写**：用用户原话或稍加精炼，概括角色的核心设定。例如用户说"一个被神抛弃后生活在现代都市的冷淡女性"，core_concept 应为"被神抛弃后生活在现代都市的冷淡女性"。
2. 从用户描述中找性格词，填到 personality 列表。例如"冷淡"→["冷淡"]。
3. 从用户描述中找主题关键词，填到 themes 列表。例如"被神抛弃""都市"→["被抛弃","都市奇幻","神性"]。
4. 其他字段有明确信息才填，不要编造。

## 你不能：
- 返回"未知角色""尚未明确"等占位文字。如果用户说了信息，就直接提取。
- 返回空的 updates。至少要有 core_concept。

## JSON 格式：
{"updates": {"core_concept": "...", "personality": [...], "themes": [...], ...}, "confidence": 0.8, "notes": ""}

只返回 JSON，不要用 ``` 包裹。"""

FAST_DESIGNER_PROMPT = """你是角色快速生成器。用户给你一段简短的角色灵感，你需要**大胆推断和补全**，一次性生成完整的角色设定。

## 你必须：
1. 为用户生成一个合适的中文名字。
2. 提炼 core_concept。
3. 推断性格特质（personality），至少 3 个。
4. 推断外貌特征（appearance），写 1-2 句。
5. 推断背景故事（background），写 2-3 句。
6. 推断说话风格（speaking_style），写 1 句。
7. 构思一个典型场景（scenario），写 1-2 句。
8. 生成一句开场白（first_message），角色对用户说的第一句话。
9. 生成一段示例对话（example_dialogue），格式为"角色名: ...\n用户: ...\n角色名: ..."。
10. 提取主题标签（themes），至少 3 个。

## 风格要求：
- 大胆创作，不要保守。即使用户只给了模糊灵感，也请发挥想象力补全。
- 保持角色设定的一致性和合理性。
- 用中文创作。

## JSON 格式：
{"updates": {"name": "", "core_concept": "", "personality": [], "appearance": "", "background": "", "speaking_style": "", "scenario": "", "first_message": "", "example_dialogue": "", "themes": []}, "confidence": 0.8, "notes": ""}

只返回 JSON。"""


async def extract_settings_fast(user_message: str) -> dict:
    """Fast mode: aggressively fill all fields from a brief idea.

    Returns: {"updates": dict, "confidence": float, "notes": str}
    """
    user_prompt = f"角色灵感：{user_message}\n\n请根据这个灵感，一次性生成完整的角色设定。"

    result = await chat_json(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=FAST_DESIGNER_PROMPT,
        agent="designer",
    )

    result.setdefault("updates", {})
    result.setdefault("confidence", 0.0)
    result.setdefault("notes", "")
    return result


def _format_draft_context(draft: OCDraft) -> str:
    """Format the current draft for the LLM prompt."""
    filled = []
    for field_name in [
        "name", "gender", "age_range", "role_type",
        "core_concept", "personality", "appearance", "background",
        "abilities", "weaknesses", "relationships",
        "speaking_style", "scenario", "first_message", "example_dialogue",
        "themes", "tags", "user_preferences",
    ]:
        val = getattr(draft, field_name, None)
        if val is not None and val != [] and val != "":
            if isinstance(val, list):
                filled.append(f"- {field_name}: {', '.join(val)}")
            else:
                filled.append(f"- {field_name}: {val}")

    filled_text = "\n".join(filled) if filled else "(no fields filled yet)"
    locked = ", ".join(draft.locked_fields) if draft.locked_fields else "(none)"

    return f"""## Current draft (filled fields):
{filled_text}

## Locked fields (DO NOT MODIFY): {locked}"""


async def extract_settings(
    user_message: str,
    current_draft: OCDraft,
    chat_history: list[ChatMessage],
) -> dict:
    """Extract character settings from a user message.

    Returns: {"updates": dict, "confidence": float, "notes": str}
    """
    # Build context from recent chat history (last 4 messages)
    history_text = ""
    for msg in chat_history[-4:]:
        role_label = "用户" if msg.role == "user" else "AI"
        history_text += f"[{role_label}]: {msg.content}\n"

    draft_context = _format_draft_context(current_draft)

    user_prompt = f"""当前已有设定：
{draft_context}

用户最新消息：
{user_message}

从用户消息中提取角色设定，返回 JSON。"""

    result = await chat_json(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=DESIGNER_SYSTEM_PROMPT,
        agent="designer",
    )

    # Ensure required keys exist
    result.setdefault("updates", {})
    result.setdefault("confidence", 0.0)
    result.setdefault("notes", "")

    # Filter out locked fields from updates
    updates = result["updates"]
    locked = set(current_draft.locked_fields)
    result["updates"] = {k: v for k, v in updates.items() if k not in locked}

    return result
