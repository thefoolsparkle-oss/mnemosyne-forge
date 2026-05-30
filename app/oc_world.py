"""World-building extension — v0.5

Generates a complete world setting from a character draft, including:
- Geography, history, organizations, rule systems, key events
- Character's relationship to the world
- World Book entries for SillyTavern-compatible context injection
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

WORLD_PROMPT = """你是世界观构建师。根据给定的角色设定，构建一个完整的虚构世界观。

## 必须包含：

### 1. 世界概述（summary）
用 2-3 句话概括这个世界的基本面貌。

### 2. 地理（geography）
描述这个世界的地理特征，至少 2-3 个重要地点。

### 3. 历史（history）
2-3 个关键历史事件或时间线节点，塑造了当今世界格局。

### 4. 组织与势力（organizations）
列出 2-4 个重要组织、国家或势力，说明其目标和影响力。

### 5. 规则体系（rules）
描述世界的特殊规则：是否存在魔法？科技水平如何？有什么物理/社会法则？

### 6. 关键事件（events）
1-2 个正在发生或即将发生的重要事件。

### 7. 角色与世界的联系（character_link）
说明角色在这个世界中的位置、与哪些势力有关联、在世界历史中的角色。

### 8. 世界书条目（world_book）
生成 4-8 个世界书条目，每个条目包含：
- key: 触发关键词（中文，用于在对话中匹配注入）
- content: 条目内容（50-100字）
- priority: 重要性（1-10）

## JSON 格式：
{
  "summary": "...",
  "geography": "...",
  "history": "...",
  "organizations": "...",
  "rules": "...",
  "events": "...",
  "character_link": "...",
  "world_book": [
    {"key": "关键词", "content": "条目内容", "priority": 5}
  ]
}

只返回 JSON。"""


async def generate_world(draft: OCDraft) -> dict:
    """Generate a world setting from a character draft."""
    context = _format_draft(draft)
    prompt = f"角色设定：\n{context}\n\n请根据这个角色，构建一个完整的虚构世界观。"

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=WORLD_PROMPT,
            agent="export",
        )
        return {"ok": True, "world": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _format_draft(draft: OCDraft) -> str:
    lines = []
    if draft.name:
        lines.append(f"角色名：{draft.name}")
    if draft.core_concept:
        lines.append(f"核心设定：{draft.core_concept}")
    if draft.personality:
        lines.append(f"性格：{', '.join(draft.personality)}")
    if draft.background:
        lines.append(f"背景：{draft.background}")
    if draft.abilities:
        lines.append(f"能力：{', '.join(draft.abilities)}")
    if draft.weaknesses:
        lines.append(f"弱点：{', '.join(draft.weaknesses)}")
    if draft.themes:
        lines.append(f"主题：{', '.join(draft.themes)}")
    return "\n".join(lines)


async def generate_world_book(draft: OCDraft, world: dict | None = None) -> dict:
    """Generate standalone world book entries (without full world generation)."""
    return await generate_world(draft)
