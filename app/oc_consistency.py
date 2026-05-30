"""Consistency Agent — checks for missing fields and stage progression.

v0.1 uses rule-based checks (no LLM calls). Detects:
- Which important fields are empty
- Completion score based on filled fields
- Whether to advance to the next stage
"""

from __future__ import annotations

from .oc_models import OCDraft

# Core fields that count toward completion_score during conversation.
# first_message and example_dialogue are generated at export time, not during chat.
IMPORTANT_FIELDS = [
    "name",
    "core_concept",
    "personality",
    "appearance",
    "background",
]

# Ordered stage progression
STAGE_ORDER = [
    "core_concept",
    "personality",
    "appearance",
    "background",
    "abilities",
    "relationships",
    "speaking_style",
    "scenario",
    "opening",
    "final_review",
]

# Which fields gate each stage (must be non-empty to advance past)
STAGE_GATES: dict[str, str] = {
    "core_concept": "core_concept",
    "personality": "personality",
    "appearance": "appearance",
    "background": "background",
    "abilities": "abilities",
    "relationships": "relationships",
    "speaking_style": "speaking_style",
    "scenario": "scenario",
    "opening": "first_message",
}

# Human-readable field labels for display
FIELD_LABELS: dict[str, str] = {
    "name": "名字",
    "gender": "性别",
    "age_range": "年龄范围",
    "role_type": "角色类型",
    "core_concept": "核心概念",
    "personality": "性格特质",
    "appearance": "外貌特征",
    "background": "背景故事",
    "abilities": "能力特长",
    "weaknesses": "弱点缺陷",
    "relationships": "关系网络",
    "speaking_style": "说话方式",
    "scenario": "使用场景",
    "first_message": "开场白",
    "example_dialogue": "示例对话",
}


def _is_filled(draft: OCDraft, field: str) -> bool:
    val = getattr(draft, field, None)
    if val is None:
        return False
    if isinstance(val, list) and len(val) == 0:
        return False
    if isinstance(val, str) and val.strip() == "":
        return False
    return True


def check_draft(draft: OCDraft) -> dict:
    """Run rule-based consistency check on the draft.

    Returns a dict with missing_fields, completion_score, contradictions, and suggestions.
    """
    missing = []
    for field in IMPORTANT_FIELDS:
        if not _is_filled(draft, field):
            missing.append(field)

    # Completion: weighted by important fields
    filled_count = len(IMPORTANT_FIELDS) - len(missing)
    score = round(filled_count / len(IMPORTANT_FIELDS), 2)

    # Also add secondary fields that are empty (informational, not scored)
    secondary_missing = []
    for field in ["gender", "age_range", "role_type", "speaking_style", "scenario"]:
        if not _is_filled(draft, field):
            secondary_missing.append(field)

    contradictions: list[str] = []
    # Simple contradiction checks
    if draft.age_range and draft.background:
        age_lower = draft.age_range.lower()
        if "少年" in age_lower or "儿童" in age_lower or "未成年" in age_lower:
            if "工作" in draft.background and "多年" in draft.background:
                contradictions.append("年龄与背景中的工作年限可能不一致")

    suggestions: list[str] = []
    if "personality" in missing:
        suggestions.append("建议补充至少 2-3 个性格特质")
    if "appearance" in missing:
        suggestions.append("建议描述角色的外貌特征，让形象更立体")
    if "background" in missing:
        suggestions.append("建议补充背景故事，让角色更有深度")
    if "first_message" in missing:
        suggestions.append("可以构思角色开口说的第一句话")

    return {
        "missing_fields": missing,
        "secondary_missing": secondary_missing,
        "completion_score": score,
        "contradictions": contradictions,
        "suggestions": suggestions,
    }


def determine_next_stage(draft: OCDraft) -> str:
    """Advance the stage if the current stage's gate field is filled.

    Never regress — stays at or beyond the current stage.
    """
    current_idx = STAGE_ORDER.index(draft.current_stage) if draft.current_stage in STAGE_ORDER else 0

    # Try to advance
    for offset in range(len(STAGE_ORDER) - current_idx):
        candidate = STAGE_ORDER[current_idx + offset]
        gate = STAGE_GATES.get(candidate)
        if gate is None:
            continue
        if _is_filled(draft, gate):
            continue  # This stage is satisfied, try next
        return candidate  # First unsatisfied stage

    # All gates passed → final review
    return "final_review"
