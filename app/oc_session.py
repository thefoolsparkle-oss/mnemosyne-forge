"""Session Orchestrator — manages the full character creation workflow.

Coordinates Guide, Designer, Consistency, and Export agents.
Handles session lifecycle and persists state to SQLite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import db
from .oc_consistency import check_draft, determine_next_stage
from .oc_designer import extract_settings, extract_settings_fast
from .oc_export import export_card_v2
from .oc_guide import generate_guide_message
from .oc_models import OCDraft, OCSession, ChatMessage
from .oc_search import search_and_inspire
from .oc_search import search_trigger as _search_trigger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_session(initial_idea: str, user_id: int = 0) -> dict:
    """Create a new character creation session from the user's initial idea."""
    session_id = uuid.uuid4().hex[:12]
    now = _now_iso()

    draft = OCDraft()

    db.init_db()
    db.create_session(session_id, user_id, "新角色", draft, now, now)

    # Save user's initial message
    db.add_message(session_id, "user", initial_idea, now)

    # Process the initial idea through the full pipeline
    result = await _process_message_internal(session_id, initial_idea, draft, [])
    db.update_session_draft(session_id, result["draft"])
    db.add_message(session_id, "assistant", result["assistant_message"], _now_iso())

    # Update title from draft name if available
    if result["draft"].name:
        title = result["draft"].name
    elif result["draft"].core_concept:
        title = result["draft"].core_concept[:20]
    else:
        title = initial_idea[:20]
    # Update session title in DB
    db.update_session_title(session_id, title)

    return {
        "session_id": session_id,
        "assistant_message": result["assistant_message"],
        "draft": result["draft"].model_dump(),
        "stage": result["draft"].current_stage,
        "completion_score": result["draft"].completion_score,
    }


async def create_fast_session(initial_idea: str, user_id: int = 0) -> dict:
    """Fast mode: generate a complete character card from a brief idea in one shot."""
    session_id = uuid.uuid4().hex[:12]
    now = _now_iso()

    draft = OCDraft()

    db.init_db()
    db.create_session(session_id, user_id, "快速生成", draft, now, now)
    db.add_message(session_id, "user", initial_idea, now)

    # Fast designer: aggressive one-shot extraction
    extracted = await extract_settings_fast(initial_idea)
    updates = extracted.get("updates", {})

    for field, value in updates.items():
        if hasattr(draft, field) and value is not None:
            setattr(draft, field, value)

    # Consistency check
    check_result = check_draft(draft)
    draft.missing_fields = check_result["missing_fields"]
    draft.completion_score = check_result["completion_score"]
    draft.current_stage = determine_next_stage(draft)

    assistant_msg = f"已根据你的灵感快速生成了角色「{draft.name or '未命名'}」的设定，请查看卡片预览。你可以继续对话来调整细节。"

    db.update_session_draft(session_id, draft)
    db.add_message(session_id, "assistant", assistant_msg, _now_iso())

    # Update title
    title = draft.name or draft.core_concept or initial_idea[:20]
    db.update_session_title(session_id, title)

    # Auto-export
    card_data = None
    try:
        export_result = await export_card_v2(session_id)
        if export_result.get("ok"):
            card_data = export_result.get("card")
    except Exception:
        pass

    return {
        "session_id": session_id,
        "assistant_message": assistant_msg,
        "draft": draft.model_dump(),
        "stage": draft.current_stage,
        "completion_score": draft.completion_score,
        "card": card_data,
    }


async def process_message(session_id: str, user_message: str) -> dict:
    """Process a user message in an existing session.

    Returns: {"assistant_message": str, "draft": dict, "stage": str, "completion_score": float}
    """
    # Load session
    session_data = db.get_session(session_id)
    if session_data is None:
        raise ValueError(f"Session not found: {session_id}")

    draft: OCDraft = session_data["draft"]
    messages = db.get_messages(session_id)
    chat_history = [ChatMessage(**m) for m in messages]

    # Save user message
    now = _now_iso()
    db.add_message(session_id, "user", user_message, now)
    chat_history.append(ChatMessage(role="user", content=user_message, created_at=now))

    # Process
    result = await _process_message_internal(session_id, user_message, draft, chat_history)

    # Save results
    db.update_session_draft(session_id, result["draft"])
    db.add_message(session_id, "assistant", result["assistant_message"], _now_iso())

    # Update title
    new_title = result["draft"].name or result["draft"].core_concept or session_data.get("title", "新角色")
    new_title = new_title[:30] if new_title else "新角色"
    db.update_session_title(session_id, new_title)

    # Detect export intent
    card_data = None
    export_keywords = ["生成角色卡", "导出角色卡", "生成卡片", "做角色卡", "创建角色卡",
                       "导出v2", "下载角色卡", "生成v2", "做卡片", "导出卡片"]
    if any(kw in user_message for kw in export_keywords) and result["draft"].completion_score >= 0.2:
        try:
            export_result = await export_card_v2(session_id)
            if export_result.get("ok"):
                card_data = export_result.get("card")
        except Exception:
            pass  # Export failed silently, still return the normal message

    return {
        "assistant_message": result["assistant_message"],
        "draft": result["draft"].model_dump(),
        "stage": result["draft"].current_stage,
        "completion_score": result["draft"].completion_score,
        "card": card_data,
    }


async def _process_message_internal(
    session_id: str,
    user_message: str,
    draft: OCDraft,
    chat_history: list[ChatMessage],
) -> dict:
    """Core pipeline: extract → check → guide. Returns dict with assistant_message and draft."""
    # 1. Designer: extract settings
    extracted = await extract_settings(user_message, draft, chat_history)
    updates = extracted.get("updates", {})
    designer_notes = extracted.get("notes", "")

    # 2. Apply updates to draft (respect locked_fields)
    for field, value in updates.items():
        if field in draft.locked_fields:
            continue
        if hasattr(draft, field):
            existing = getattr(draft, field)
            # For list fields, merge instead of replace
            if isinstance(existing, list) and isinstance(value, list):
                merged = list(existing)
                for item in value:
                    if item not in merged:
                        merged.append(item)
                setattr(draft, field, merged)
            elif value is not None:
                setattr(draft, field, value)

    # 3. Consistency: check draft
    check_result = check_draft(draft)
    draft.missing_fields = check_result["missing_fields"]
    draft.completion_score = check_result["completion_score"]

    # 4. Stage progression
    draft.current_stage = determine_next_stage(draft)

    # 4.5. Search for inspiration (auto mode)
    from .config import get_config
    if get_config().get("features", {}).get("search_enabled", False):
        try:
            plan = await _search_trigger(user_message, draft)
            if plan.should_search or plan.queries:
                search_result = await search_and_inspire(session_id, user_message, draft, "auto")
                if search_result.ok and search_result.inspiration:
                    insp = search_result.inspiration
                    search_context = f"\n[搜索灵感] {insp.title}: {insp.summary}\n"
                    for idea in insp.usable_ideas:
                        search_context += f"  · {idea}\n"
                    if insp.cautions:
                        search_context += f"注意: {', '.join(insp.cautions)}\n"
                    designer_notes += search_context
        except Exception:
            pass  # Search failure never breaks chat

    # 5. Guide: generate response
    search_context_final = designer_notes if "[搜索灵感]" in designer_notes else ""
    assistant_message = await generate_guide_message(
        draft=draft,
        current_stage=draft.current_stage,
        missing_fields=check_result["missing_fields"],
        chat_history=chat_history,
        designer_notes=designer_notes,
        search_inspiration=search_context_final,
    )

    return {
        "assistant_message": assistant_message,
        "draft": draft,
    }


async def get_session_draft(session_id: str) -> OCDraft | None:
    """Get the current draft for a session."""
    session_data = db.get_session(session_id)
    if session_data is None:
        return None
    return session_data["draft"]


async def get_session_messages(session_id: str) -> list[dict]:
    """Get all messages for a session."""
    return db.get_messages(session_id)


async def export_session_card(session_id: str) -> dict:
    """Export the Character Card V2 for a session."""
    return await export_card_v2(session_id)
