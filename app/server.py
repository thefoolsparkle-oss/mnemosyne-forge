"""FastAPI server entry point for Mnemosyne Forge.

Serves the web frontend at root path and API endpoints under /api/.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, db, oc_session
from .config import get_app_config, get_project_root

app = FastAPI(title="Mnemosyne Forge", version="0.1.0")
MAX_VOICE_REFERENCE_BYTES = 50 * 1024 * 1024

# CORS — allow local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Determine web directory
_web_dir = get_project_root() / "web"


@app.on_event("startup")
async def startup():
    db.init_db()
    auth.init_auth_db()
    print(f"[Mnemosyne Forge] Databases initialized")
    print(f"[Mnemosyne Forge] Serving web from: {_web_dir}")


# --- Root: serve index.html ---

@app.get("/")
async def root():
    index_path = _web_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse({"ok": True, "service": "Mnemosyne Forge", "note": "web/ not found, API only mode"})


# --- Static files ---

if _web_dir.exists():
    app.mount("/web", StaticFiles(directory=str(_web_dir)), name="web_static")

# Serve generated assets
_exports_dir = get_project_root() / "exports"
if _exports_dir.exists():
    app.mount("/exports", StaticFiles(directory=str(_exports_dir)), name="exports_static")


# --- Health ---

@app.get("/health")
async def health():
    return {"ok": True, "service": "Mnemosyne Forge"}


@app.post("/shutdown")
async def shutdown(user: dict[str, Any] = Depends(auth.current_admin)):
    """Gracefully shut down the server (admin only)."""
    import sys, os
    # Return response before killing process
    import asyncio
    asyncio.create_task(_delayed_shutdown())
    return {"ok": True, "message": "Shutting down..."}


async def _delayed_shutdown():
    import asyncio, os, signal, sys
    await asyncio.sleep(0.5)
    if hasattr(signal, 'SIGTERM'):
        os.kill(os.getpid(), signal.SIGTERM)
    else:
        sys.exit(0)


# --- Sessions ---

def _require_session_access(session_id: str, user: dict[str, Any]) -> None:
    is_admin = user.get("role") == "admin"
    if not db.session_belongs_to_user(session_id, _forge_user_id(user), is_admin=is_admin):
        raise HTTPException(status_code=404, detail="Session not found")


def _forge_user_id(user: dict[str, Any]) -> int:
    return int(user.get("forge_user_id") or user["id"])


def _safe_asset_file_cleanup(assets: list[dict], protected_paths: set[str] | None = None) -> dict[str, Any]:
    project_root = get_project_root().resolve()
    allowed_roots = [
        (project_root / "exports").resolve(),
        (project_root / "data" / "voice_references").resolve(),
    ]
    protected_paths = protected_paths or set()
    result: dict[str, Any] = {"deleted_files": [], "kept_files": [], "skipped": []}

    for asset in assets:
        raw_path = str(asset.get("path") or "").strip()
        if not raw_path:
            result["skipped"].append({"asset_id": asset.get("id"), "reason": "empty_path"})
            continue
        if raw_path in protected_paths:
            result["kept_files"].append(raw_path)
            continue
        if raw_path.startswith(("http://", "https://")):
            result["skipped"].append({"asset_id": asset.get("id"), "path": raw_path, "reason": "remote_path"})
            continue

        path = Path(raw_path)
        if not path.is_absolute():
            path = project_root / path
        resolved = path.resolve(strict=False)
        if not any(resolved == root or root in resolved.parents for root in allowed_roots):
            result["skipped"].append({"asset_id": asset.get("id"), "path": raw_path, "reason": "outside_allowed_roots"})
            continue
        if not resolved.exists() or not resolved.is_file():
            result["skipped"].append({"asset_id": asset.get("id"), "path": raw_path, "reason": "not_found"})
            continue

        try:
            resolved.unlink()
            result["deleted_files"].append(str(resolved))
        except OSError as exc:
            result["skipped"].append({"asset_id": asset.get("id"), "path": raw_path, "reason": str(exc)})

    return result


@app.post("/api/sessions")
async def create_session(body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    initial_idea = body.get("initial_idea", "").strip()
    if not initial_idea:
        raise HTTPException(status_code=400, detail="initial_idea is required")

    fast_mode = body.get("fast_mode", False)
    user_id = _forge_user_id(user)

    try:
        if fast_mode:
            result = await oc_session.create_fast_session(initial_idea, user_id)
        else:
            result = await oc_session.create_session(initial_idea, user_id)
        return {"ok": True, **result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/api/sessions")
async def list_sessions(user: dict[str, Any] = Depends(auth.current_user)):
    try:
        is_admin = user.get("role") == "admin"
        sessions = db.list_sessions(user_id=None if is_admin else _forge_user_id(user))
        return {"ok": True, "sessions": sessions, "is_admin": is_admin}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/api/sessions/{session_id}/resume")
async def resume_session(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    """Load a session for resuming — returns draft + messages."""
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await oc_session.get_session_messages(session_id)
    return {"ok": True, "session_id": session_id, "draft": draft.model_dump(), "messages": messages}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    assets = db.list_assets(session_id)
    deleted = db.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    cleanup = _safe_asset_file_cleanup(assets)
    return {"ok": True, "cleanup": cleanup}


@app.get("/api/sessions/{session_id}/draft")
async def get_draft(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, "draft": draft.model_dump()}


@app.patch("/api/sessions/{session_id}/draft")
async def update_draft(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    """Update specific draft fields manually."""
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = body.get("updates", {})
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="updates must be a dict")
    locked = body.get("locked_fields", [])

    for field, value in updates.items():
        if hasattr(draft, field):
            setattr(draft, field, value)

    if locked:
        draft.locked_fields = list(set(draft.locked_fields + locked))

    db.update_session_draft(session_id, draft)
    return {"ok": True, "draft": draft.model_dump()}


@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    messages = await oc_session.get_session_messages(session_id)
    return {"ok": True, "messages": messages}


@app.post("/api/sessions/{session_id}/messages")
async def send_message(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        result = await oc_session.process_message(session_id, message)
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.post("/api/sessions/{session_id}/export/card-v2")
async def export_card(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    try:
        result = await oc_session.export_session_card(session_id)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/api/sessions/{session_id}/export/download")
async def download_card(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    """Download the already-exported card JSON file directly, without re-generating."""
    _require_session_access(session_id, user)
    import json as _json
    from pathlib import Path as _Path
    from .config import get_project_root

    export_dir = get_project_root() / "exports"
    file_path = export_dir / f"{session_id}_card.json"
    if not file_path.exists():
        # Fallback: generate if not already saved
        result = await oc_session.export_session_card(session_id)
        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Export failed"))
        file_path = _Path(result["file_path"])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Exported file not found")
        card_data = result["card"]
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            card_data = _json.load(f)

    raw_name = card_data.get("data", {}).get("name", "character")
    safe_name = str(raw_name).replace("/", "_").replace("\\", "_")[:50]
    filename = f"{safe_name}_card.json"
    return JSONResponse(
        content=card_data,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Auth models ──────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=8, max_length=200)
    nickname: str | None = Field(default=None, max_length=60)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=8, max_length=200    )


# ─── Search ─────────────────────────────────────────────

@app.post("/api/sessions/{session_id}/search")
async def search(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_search import search_and_inspire as do_search
    _require_session_access(session_id, user)
    query = body.get("query", "").strip()
    mode = body.get("mode", "manual")
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = await do_search(session_id, query, draft, mode)
        return result.model_dump()
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/api/sessions/{session_id}/search-runs")
async def search_runs(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    runs = db.get_search_runs(session_id)
    return {"ok": True, "runs": runs}


# ─── World generation ──────────────────────────────────

@app.post("/api/sessions/{session_id}/world")
async def generate_world(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_world import generate_world as gen_world
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = await gen_world(draft)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/api/sessions/{session_id}/visual-identity")
async def visual_identity(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_visual_identity import analyze_visual_identity
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    profile = await analyze_visual_identity(draft)
    return {"ok": True, "visual_profile": profile}


@app.post("/api/sessions/{session_id}/image-prompt-direct")
async def image_prompt_direct(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_image_prompt_director import direct_image_prompt
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    visual = body.get("visual_profile")
    result = await direct_image_prompt(draft, visual)
    return {"ok": True, "prompts": result}


@app.post("/api/sessions/{session_id}/image-critique")
async def image_critique(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    from .oc_image_critic import critique_image_prompt
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    critique = await critique_image_prompt(draft, body.get("prompt", ""), body.get("negative_prompt", ""))
    return {"ok": True, "critique": critique}


@app.post("/api/dialogue-performance")
async def dialogue_performance(body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_dialogue_performance import analyze_performance
    draft = None
    session_id = body.get("session_id")
    if session_id:
        _require_session_access(str(session_id), user)
        draft = await oc_session.get_session_draft(str(session_id))
    result = await analyze_performance(body.get("text", ""), draft)
    return {"ok": True, "performance": result}


@app.post("/api/migrate-voice-profiles")
async def migrate_voice_profiles(user: dict[str, Any] = Depends(auth.current_admin)):
    """Clean up legacy Fish provider hints when ElevenLabs is the default."""
    cfg = get_config()
    if cfg.get("voice", {}).get("provider") != "elevenlabs":
        return {"ok": True, "migrated": 0, "note": "Default provider is not elevenlabs, no migration needed"}

    sessions = db.list_sessions()
    migrated = 0
    for s in sessions:
        sid = s["id"]
        profile = db.get_voice_profile(sid)
        if not profile:
            continue
        hints = profile.get("provider_hints", {})
        changed = False
        # Remove legacy Fish fields if present
        for key in list(hints.keys()):
            if key.startswith("fish_") and key != "fish_reference_id":
                del hints[key]
                changed = True
        if changed:
            db.save_voice_profile(sid, json.dumps(profile, ensure_ascii=False))
            migrated += 1

    return {"ok": True, "migrated": migrated}


# ─── Image / Voice / Bridge ────────────────────────────

@app.get("/api/bridge/health")
async def bridge_health(user: dict[str, Any] = Depends(auth.current_user)):
    from .mnemosyne_bridge import check_bridge_health
    return await check_bridge_health()


@app.post("/api/sessions/{session_id}/import-to-mnemosyne")
async def import_to_mnemosyne(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    from .mnemosyne_bridge import import_to_mnemosyne as do_import
    from .oc_export import export_card_v2 as do_export
    _require_session_access(session_id, user)
    export = await do_export(session_id)
    if not export.get("ok"):
        return export
    draft = await oc_session.get_session_draft(session_id)
    return await do_import(session_id, export["card"], draft)


@app.get("/api/sessions/{session_id}/image-prompt")
async def image_prompt(session_id: str, style: str = "anime portrait", user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_image_gen import build_image_prompt
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    prompt = await build_image_prompt(draft, style)
    return {"ok": True, "prompt": prompt}


@app.post("/api/sessions/{session_id}/image")
async def generate_image(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_image_gen import generate_character_image, build_image_prompt
    from .oc_prompt_auditor import audit_image_prompt
    from pathlib import Path
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    style = body.get("style", "anime portrait")
    prompt = await build_image_prompt(draft, style)
    negative_prompt = "low quality, blurry, ugly, deformed, bad anatomy, extra fingers, missing fingers, watermark, text, logo, signature"
    audit = await audit_image_prompt(draft, prompt, negative_prompt)
    result = await generate_character_image(draft, style, prompt=prompt, negative_prompt=negative_prompt)
    result["audit"] = audit
    if result.get("ok") and result.get("image_path"):
        result["image_url"] = "/exports/images/" + Path(result["image_path"]).name
        result["asset_id"] = db.insert_asset(
            session_id,
            "image_candidate",
            "stability",
            result["image_path"],
            {
                "style": style,
                "prompt": result.get("prompt", ""),
                "negative_prompt": result.get("negative_prompt", ""),
                "seed": result.get("seed"),
                "audit": audit,
                "source": "single_image",
            },
        )
    return result


@app.post("/api/sessions/{session_id}/image-candidates")
async def image_candidates(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_image_gen import generate_character_image
    from .oc_visual_identity import analyze_visual_identity
    from .oc_image_prompt_director import direct_image_prompt
    from .oc_image_critic import critique_image_prompt, critique_image_result
    from pathlib import Path

    STYLE_LABEL_MAP = {
        "anime character key visual": "动漫精绘",
        "anime portrait cinematic rim light": "电影感动漫",
        "game character concept art": "游戏立绘",
    }
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Use Visual Identity + Prompt Director for structured prompts
    retry_style = body.get("retry_style", "")
    retry_prompt = body.get("retry_prompt", "")
    retry_negative_prompt = body.get("retry_negative_prompt", "")

    if retry_style and retry_prompt:
        # Retry with exact original prompt — skip Visual Identity + Director
        variations = [{"style": retry_style, "positive_prompt": retry_prompt, "negative_prompt": retry_negative_prompt}]
    else:
        visual = await analyze_visual_identity(draft)
        directed = await direct_image_prompt(draft, visual)
        variations = directed.get("variations", [])
        if retry_style:
            original = next((v for v in variations if v.get("style") == retry_style), None)
            if not original:
                original = {"style": retry_style, "positive_prompt": directed.get("positive_prompt", "")}
            variations = [original]
        elif not variations:
            variations = [
                {"style": "anime character key visual", "positive_prompt": directed.get("positive_prompt", "")},
                {"style": "anime portrait cinematic rim light", "positive_prompt": directed.get("positive_prompt", "")},
                {"style": "game character concept art", "positive_prompt": directed.get("positive_prompt", "")},
            ]

    candidates = []
    for i, v in enumerate(variations[:3]):
        try:
            result = await generate_character_image(draft, v.get("style", "anime"), prompt=v.get("positive_prompt", ""))
            critique = await critique_image_prompt(draft, v.get("positive_prompt", ""), v.get("negative_prompt", ""))
            result_critique = {"note": "result_image_critique_not_available"}
            if result.get("ok") and result.get("image_path"):
                try:
                    result_critique = await critique_image_result(draft, result["image_path"],
                        v.get("positive_prompt", ""), v.get("negative_prompt", ""))
                except Exception:
                    pass
            image_url = ""
            asset_id = None
            if result.get("ok") and result.get("image_path"):
                image_url = "/exports/images/" + Path(result["image_path"]).name
                asset_id = db.insert_asset(session_id, "image_candidate", "stability", result["image_path"],
                    {"index": i, "style": v.get("style", ""), "prompt": v.get("positive_prompt", "")})
            candidates.append({
                "index": i, "label": STYLE_LABEL_MAP.get(v.get("style", ""), f"候选 {i + 1}"),
                "style": v.get("style", ""),
                "ok": result.get("ok", False),
                "image_path": result.get("image_path", ""),
                "image_url": image_url,
                "asset_id": asset_id,
                "prompt": v.get("positive_prompt", ""),
                "negative_prompt": v.get("negative_prompt", ""),
                "error": result.get("error", ""),
                "critique": critique,
                "result_critique": result_critique,
            })
        except Exception as e:
            candidates.append({"index": i, "label": v.get("style", ""), "ok": False, "error": str(e), "critique": None})
    return {"ok": True, "candidates": candidates}


@app.post("/api/sessions/{session_id}/image-variations")
async def image_variations(session_id: str, body: dict | None = None, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_image_gen import build_image_variation_prompt, generate_character_image
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")

    locked = next(iter(db.list_assets(session_id, asset_type="image_locked", selected=True)), None)
    if locked is None:
        locked = next(iter(db.list_assets(session_id, asset_type="image_locked")), None)
    if locked is None:
        raise HTTPException(status_code=400, detail="No locked visual canon. Generate and lock an image first.")

    locked_meta = locked.get("metadata", {})
    locked_prompt = locked_meta.get("locked_prompt") or locked_meta.get("prompt") or ""
    negative_prompt = locked_meta.get("negative_prompt") or "low quality, blurry, ugly, deformed, bad anatomy, extra fingers, missing fingers, watermark, text, logo, signature"
    requests = (body or {}).get("variations") or [
        {"name": "expression", "label": "表情变体", "request": "same character, gentle new expression, half body portrait, consistent outfit"},
        {"name": "pose", "label": "姿势变体", "request": "same character, different upper body pose, dynamic but restrained composition"},
        {"name": "scene", "label": "场景变体", "request": "same character, same design, new background atmosphere that matches the character story"},
    ]

    candidates = []
    for i, item in enumerate(requests):
        label = item.get("label") or item.get("name") or f"Variation {i + 1}"
        variation_request = item.get("request") or label
        try:
            prompt = await build_image_variation_prompt(
                draft,
                locked_prompt,
                variation_request,
                item.get("style") or locked_meta.get("selected_style") or "anime portrait",
            )
            result = await generate_character_image(
                draft,
                item.get("style") or locked_meta.get("selected_style") or "anime portrait",
                prompt=prompt,
                negative_prompt=negative_prompt,
            )
            asset_id = None
            image_url = ""
            if result.get("ok") and result.get("image_path"):
                image_url = "/exports/images/" + Path(result["image_path"]).name
                asset_id = db.insert_asset(
                    session_id,
                    "image_candidate",
                    "stability",
                    result["image_path"],
                    {
                        "index": i,
                        "label": label,
                        "style": item.get("style") or locked_meta.get("selected_style") or "anime portrait",
                        "prompt": result.get("prompt", ""),
                        "negative_prompt": result.get("negative_prompt", ""),
                        "seed": result.get("seed"),
                        "source": "image_variations",
                        "parent_asset_id": locked.get("id"),
                        "parent_image_path": locked.get("path"),
                        "variation_request": variation_request,
                    },
                )
            candidates.append({
                "index": i,
                "label": label,
                "style": item.get("style") or locked_meta.get("selected_style") or "anime portrait",
                "ok": result.get("ok", False),
                "image_path": result.get("image_path", ""),
                "image_url": image_url,
                "asset_id": asset_id,
                "prompt": result.get("prompt", ""),
                "error": result.get("error", ""),
                "parent_asset_id": locked.get("id"),
            })
        except Exception as e:
            candidates.append({"index": i, "label": label, "ok": False, "error": str(e), "parent_asset_id": locked.get("id")})

    return {"ok": True, "parent_asset": locked, "candidates": candidates}


@app.post("/api/sessions/{session_id}/visual-canon-lock")
async def visual_canon_lock(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    asset = None
    if body.get("asset_id"):
        asset = db.select_asset(int(body["asset_id"]), session_id, "image_candidate")
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
    image_path = body.get("image_path") or (asset or {}).get("path", "")
    asset_meta = (asset or {}).get("metadata", {})
    canon = {
        "selected_style": body.get("style") or asset_meta.get("style", ""),
        "locked_prompt": body.get("prompt") or asset_meta.get("prompt", ""),
        "negative_prompt": body.get("negative_prompt") or asset_meta.get("negative_prompt", ""),
        "seed": body.get("seed") or asset_meta.get("seed"),
        "image_path": image_path,
        "asset_id": body.get("asset_id"),
        "locked_at": datetime.now(timezone.utc).isoformat(),
    }
    if image_path:
        canon["locked_asset_id"] = db.insert_asset(
            session_id,
            "image_locked",
            "stability",
            image_path,
            canon,
            selected=True,
        )
    draft.user_preferences.append(json.dumps(canon, ensure_ascii=False))
    db.update_session_draft(session_id, draft)
    return {"ok": True, "canon": canon}


@app.get("/api/sessions/{session_id}/assets")
async def session_assets(
    session_id: str,
    asset_type: str | None = None,
    selected: bool | None = None,
    user: dict[str, Any] = Depends(auth.current_user),
):
    _require_session_access(session_id, user)
    return {"ok": True, "assets": db.list_assets(session_id, asset_type=asset_type, selected=selected)}


@app.post("/api/sessions/{session_id}/assets/cleanup")
async def cleanup_session_assets(
    session_id: str,
    body: dict | None = None,
    user: dict[str, Any] = Depends(auth.current_user),
):
    _require_session_access(session_id, user)
    body = body or {}
    keep_selected = bool(body.get("keep_selected", True))
    assets = db.list_assets(session_id)
    selected_paths = {
        str(asset.get("path") or "").strip()
        for asset in assets
        if asset.get("selected") and asset.get("path")
    }
    targets = [asset for asset in assets if not (keep_selected and asset.get("selected"))]
    cleanup = _safe_asset_file_cleanup(targets, protected_paths=selected_paths if keep_selected else set())
    removed_records = db.delete_assets(session_id, [int(asset["id"]) for asset in targets])
    return {"ok": True, "cleanup": cleanup, "removed_records": removed_records}


@app.post("/api/sessions/{session_id}/assets/{asset_id}/select")
async def select_session_asset(
    session_id: str,
    asset_id: int,
    body: dict | None = None,
    user: dict[str, Any] = Depends(auth.current_user),
):
    _require_session_access(session_id, user)
    asset = db.select_asset(asset_id, session_id, (body or {}).get("asset_type"))
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"ok": True, "asset": asset}


@app.get("/api/sessions/{session_id}/voice-profile")
async def voice_profile(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_voice_director import analyze_voice
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    existing = db.get_voice_profile(session_id)
    if existing:
        return {"ok": True, "voice_profile": existing, "from_cache": True}
    profile = await analyze_voice(draft)
    db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))
    return {"ok": True, "voice_profile": profile, "from_cache": False}


@app.post("/api/sessions/{session_id}/voice-profile/analyze")
async def voice_analyze(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_voice_director import analyze_voice
    from .oc_prompt_auditor import audit_voice_prompt
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    profile = await analyze_voice(draft)
    audit = await audit_voice_prompt(draft, profile)
    # Preserve locked fields and user overrides from existing
    existing = db.get_voice_profile(session_id)
    if existing:
        for field in existing.get("locked_fields", []):
            if field in existing:
                profile[field] = existing[field]
    profile.update(existing.get("user_overrides", {}) if existing else {})

    # Regenerate OC-specific sample lines via Line Writer
    try:
        from .oc_line_writer import write_lines
        line_result = await write_lines(draft, count=5)
        lines = line_result.get("lines", [])
        if lines:
            profile["sample_lines"] = lines
            profile["sample_text"] = lines[0].get("text", profile.get("sample_text", ""))
    except Exception:
        pass

    db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))
    return {"ok": True, "voice_profile": profile, "audit": audit}


@app.patch("/api/sessions/{session_id}/voice-profile")
async def voice_patch(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    existing = db.get_voice_profile(session_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Voice profile not found. Analyze first.")
    if not isinstance(existing.get("locked_fields"), list):
        existing["locked_fields"] = []
    if not isinstance(existing.get("user_overrides"), dict):
        existing["user_overrides"] = {}
    for k, v in body.items():
        if k in ("locked_fields", "user_overrides"):
            continue
        existing[k] = v
        if k not in existing["locked_fields"]:
            existing["locked_fields"].append(k)
    existing["user_overrides"].update({k: v for k, v in body.items() if k not in ("locked_fields", "user_overrides")})
    db.save_voice_profile(session_id, json.dumps(existing, ensure_ascii=False))
    return {"ok": True, "voice_profile": existing}


@app.post("/api/sessions/{session_id}/voice-sample")
async def voice_sample(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    from .config import get_config, get_project_root
    from .voice_providers.base import get_provider
    _require_session_access(session_id, user)
    cfg = get_config()
    vc = cfg.get("voice", {})
    provider_name = body.get("provider") or vc.get("provider", "none")

    profile = db.get_voice_profile(session_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found. Analyze first.")

    body_hints = body.get("provider_hints") or {}
    if body_hints:
        profile.setdefault("provider_hints", {})
        profile["provider_hints"].update(body_hints)
    if body.get("fish_reference_id"):
        profile.setdefault("provider_hints", {})
        profile["provider_hints"]["fish_reference_id"] = body.get("fish_reference_id")
    if body.get("fish_voice_prompt"):
        profile.setdefault("provider_hints", {})
        profile["provider_hints"]["fish_voice_prompt"] = body.get("fish_voice_prompt")
    if body.get("fish_tts_directive") and isinstance(body.get("fish_tts_directive"), dict):
        profile.setdefault("provider_hints", {})
        profile["provider_hints"]["fish_tts_directive"] = body.get("fish_tts_directive")

    if provider_name == "fish_audio":
        refs = db.get_voice_references(session_id, provider="fish_audio")
        if refs:
            profile.setdefault("provider_hints", {})
            profile["provider_hints"]["fish_references"] = [
                {"audio_path": ref["audio_path"], "text": ref["transcript"]}
                for ref in refs[:3]
            ]

    # P0: ElevenLabs requires pre-selected voice_id
    if provider_name == "elevenlabs":
        hints = profile.get("provider_hints", {})
        if not hints.get("elevenlabs_voice_id") and not body.get("allow_auto_design"):
            raise HTTPException(
                status_code=400,
                detail="请先通过'生成专属音色'或'三候选对比'生成候选并选定一个音色。",
            )

    text = body.get("text") or profile.get("sample_text", "")

    # Auto-generate character-specific dialogue lines when no text is provided
    if not text:
        try:
            from .oc_line_writer import write_lines
            draft = await oc_session.get_session_draft(session_id)
            if draft:
                line_result = await write_lines(draft, count=5)
                lines = line_result.get("lines", [])
                if lines:
                    text = lines[0].get("text", "")
                    profile["sample_lines"] = lines
                    profile["sample_text"] = text
        except Exception:
            pass

    if not text:
        text = "你好。"

    try:
        from .oc_dialogue_performance import analyze_performance
        draft = await oc_session.get_session_draft(session_id)

        # Use multi-line text for richer per-unit analysis when sample_lines exist
        sample_lines = profile.get("sample_lines", [])
        analysis_text = text
        if sample_lines:
            analysis_text = "\n".join([l.get("text", "") for l in sample_lines if l.get("text")])

        performance = await analyze_performance(analysis_text, draft)
        profile["last_performance"] = performance
        # Apply performance cues to provider hints for TTS
        units = performance.get("units", [])
        if units:
            profile.setdefault("provider_hints", {})
            profile["provider_hints"]["performance_units"] = units
            profile["provider_hints"]["overall_tone"] = performance.get("overall_tone", "")
    except Exception:
        pass

    output_dir = get_project_root() / vc.get("output_dir", "exports/voices")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"{session_id}_{provider_name}.mp3")

    try:
        provider = get_provider(provider_name)
        result_path = await provider.synthesize(text, profile, output_path)
        db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))
        db.insert_voice_generation(session_id, provider_name, text, json.dumps(profile, ensure_ascii=False), result_path)
        from pathlib import Path
        audio_url = "/exports/voices/" + Path(result_path).name
        asset_id = db.insert_asset(
            session_id,
            "voice_sample",
            provider_name,
            result_path,
            {
                "sample_text": text,
                "voice_profile": profile,
                "audio_url": audio_url,
            },
        )

        # Per-unit TTS: generate audio for each performance unit
        per_unit_results = []
        units = profile.get("provider_hints", {}).get("performance_units", [])
        if units and hasattr(provider, "synthesize_performance_units"):
            try:
                per_unit_results = await provider.synthesize_performance_units(
                    profile, output_path
                )
                for idx, pu in enumerate(per_unit_results):
                    if pu.get("audio_path") and not pu.get("error"):
                        pu_url = "/exports/voices/" + Path(pu["audio_path"]).name
                        # Attach line metadata (emotion, context) from sample_lines
                        if idx < len(sample_lines):
                            pu["context"] = sample_lines[idx].get("context", "")
                            pu["emotion"] = sample_lines[idx].get("emotion", "")
                            pu["to_whom"] = sample_lines[idx].get("to_whom", "")
                        db.insert_asset(
                            session_id, "voice_sample", provider_name, pu["audio_path"],
                            {"unit_index": pu["unit_index"], "clean_text": pu.get("clean_text", ""),
                             "audio_url": pu_url, "parent_asset_id": asset_id}
                        )
            except Exception:
                pass

        return {
            "ok": True,
            "audio_path": result_path,
            "audio_url": audio_url,
            "provider": provider_name,
            "asset_id": asset_id,
            "per_unit_results": per_unit_results if per_unit_results else None,
            "sample_lines": sample_lines if sample_lines else None,
            "overall_tone": profile.get("provider_hints", {}).get("overall_tone", ""),
        }
    except Exception as e:
        db.insert_voice_generation(session_id, provider_name, text, json.dumps(profile, ensure_ascii=False), status="failed", error_message=str(e))
        return {"ok": False, "error": str(e)}


@app.post("/api/sessions/{session_id}/voice-sample-candidates")
async def voice_sample_candidates(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    """Generate 3 voice sample candidates with varying parameters for user selection."""
    from .config import get_config, get_project_root
    from .voice_providers.base import get_provider
    from pathlib import Path
    _require_session_access(session_id, user)

    cfg = get_config()
    vc = cfg.get("voice", {})
    provider_name = body.get("provider") or "elevenlabs"
    el_cfg = cfg.get("voice", {}).get("elevenlabs", {})

    profile = db.get_voice_profile(session_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found. Analyze first.")

    if provider_name == "elevenlabs":
        from .voice_providers.elevenlabs_provider import ElevenLabsProvider

        output_dir = get_project_root() / vc.get("output_dir", "exports/voices")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{session_id}_{provider_name}_design.mp3")
        provider = ElevenLabsProvider()
        try:
            design = await provider.design_voice(profile, output_path=output_path)
        except Exception as e:
            db.insert_voice_generation(
                session_id,
                "elevenlabs_design",
                profile.get("sample_text", ""),
                json.dumps(profile, ensure_ascii=False),
                status="failed",
                error_message=str(e),
            )
            return {"ok": False, "error": str(e)}

        hints = profile.setdefault("provider_hints", {})
        hints["provider"] = "elevenlabs"
        hints["elevenlabs_voice_description"] = design.get("voice_description")
        hints["elevenlabs_preview_text"] = design.get("preview_text")
        hints["elevenlabs_previews"] = design.get("preview_metadata", [])
        hints["elevenlabs_preview_paths"] = design.get("preview_paths", [])
        db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))

        exports_root = get_project_root() / "exports"
        candidates = []
        for preview in design.get("preview_metadata", []):
            preview_path = preview.get("preview_path") or ""
            audio_url = ""
            if preview_path:
                try:
                    audio_url = "/exports/" + Path(preview_path).relative_to(exports_root).as_posix()
                except ValueError:
                    audio_url = preview_path
            asset_id = None
            if preview_path:
                asset_id = db.insert_asset(
                    session_id,
                    "voice_preview",
                    "elevenlabs",
                    preview_path,
                    {
                        "index": preview.get("index"),
                        "generated_voice_id": preview.get("generated_voice_id"),
                        "duration_secs": preview.get("duration_secs"),
                        "language": preview.get("language"),
                        "audio_url": audio_url,
                        "preview_text": design.get("preview_text", ""),
                    },
                )
            candidates.append({
                "index": preview.get("index"),
                "label": f"候选 {preview.get('index')}",
                "generated_voice_id": preview.get("generated_voice_id"),
                "duration_secs": preview.get("duration_secs"),
                "language": preview.get("language"),
                "audio_url": audio_url,
                "audio_path": preview_path,
                "asset_id": asset_id,
            })

        db.insert_voice_generation(
            session_id,
            "elevenlabs_design",
            design.get("preview_text", ""),
            json.dumps(profile, ensure_ascii=False),
            None,
        )
        return {"ok": True, "candidates": candidates, "provider": provider_name, "preview_text": design.get("preview_text", "")}
    text = body.get("text") or profile.get("sample_text", "你好。")
    output_dir = get_project_root() / vc.get("output_dir", "exports/voices")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 3 parameter variations
    candidates = []
    variations = [
        {"stability": el_cfg.get("stability", 0.58), "similarity_boost": el_cfg.get("similarity_boost", 0.82), "label": "默认"},
        {"stability": 0.75, "similarity_boost": 0.6, "label": "沉稳"},
        {"stability": 0.3, "similarity_boost": 0.9, "label": "表现力"},
    ]

    for i, var in enumerate(variations):
        # Create a temporary profile with this variation's settings
        temp_profile = dict(profile)
        temp_profile.setdefault("provider_hints", {})
        temp_profile["provider_hints"]["el_stability"] = var["stability"]
        temp_profile["provider_hints"]["el_similarity_boost"] = var["similarity_boost"]
        output_path = str(output_dir / f"{session_id}_{provider_name}_c{i}.mp3")

        try:
            provider = get_provider(provider_name)
            result_path = await provider.synthesize(text, temp_profile, output_path)
            from pathlib import Path
            candidates.append({
                "index": i,
                "label": var["label"],
                "stability": var["stability"],
                "similarity_boost": var["similarity_boost"],
                "audio_url": "/exports/voices/" + Path(result_path).name,
                "audio_path": result_path,
                "asset_id": db.insert_asset(
                    session_id,
                    "voice_performance_candidate",
                    provider_name,
                    result_path,
                    {
                        "index": i,
                        "label": var["label"],
                        "stability": var["stability"],
                        "similarity_boost": var["similarity_boost"],
                        "sample_text": text,
                    },
                ),
            })
            db.insert_voice_generation(session_id, f"{provider_name}_c{i}", text, json.dumps(temp_profile, ensure_ascii=False), result_path)
        except Exception as e:
            candidates.append({"index": i, "label": var["label"], "error": str(e)})

    return {"ok": True, "candidates": candidates, "provider": provider_name}


@app.post("/api/sessions/{session_id}/voice-sample-candidates/select")
async def select_voice_sample_candidate(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    """Create and save a stable ElevenLabs voice from a selected Voice Design preview."""
    from .voice_providers.elevenlabs_provider import ElevenLabsProvider
    _require_session_access(session_id, user)

    profile = db.get_voice_profile(session_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found. Analyze first.")

    index = int(body.get("index") or 1)
    generated_voice_id = (body.get("generated_voice_id") or "").strip()
    hints = profile.setdefault("provider_hints", {})
    previews = hints.get("elevenlabs_previews") or []
    selected = next((p for p in previews if int(p.get("index") or 0) == index), None)
    if not generated_voice_id and selected:
        generated_voice_id = str(selected.get("generated_voice_id") or "")
    if not generated_voice_id:
        raise HTTPException(status_code=400, detail="generated_voice_id is required")

    voice_description = str(hints.get("elevenlabs_voice_description") or "")
    if not voice_description:
        raise HTTPException(status_code=400, detail="No cached ElevenLabs voice description. Generate candidates first.")

    provider = ElevenLabsProvider()
    not_selected = [
        str(p.get("generated_voice_id"))
        for p in previews
        if p.get("generated_voice_id") and str(p.get("generated_voice_id")) != generated_voice_id
    ]
    try:
        voice = await provider.create_voice(
            generated_voice_id=generated_voice_id,
            voice_name=provider._voice_name(profile),
            voice_description=voice_description,
            played_not_selected_voice_ids=not_selected,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}

    hints["provider"] = "elevenlabs"
    hints["elevenlabs_voice_id"] = voice["voice_id"]
    hints["elevenlabs_voice_name"] = voice.get("name") or provider._voice_name(profile)
    hints["elevenlabs_generated_voice_id"] = generated_voice_id
    hints["elevenlabs_selected_preview_index"] = index
    db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))
    selected_preview_asset_id = None
    for asset in db.list_assets(session_id, asset_type="voice_preview"):
        if asset.get("metadata", {}).get("generated_voice_id") == generated_voice_id:
            selected_preview_asset_id = asset["id"]
            db.select_asset(int(asset["id"]), session_id, "voice_preview")
            break
    voice_identity_asset_id = db.insert_asset(
        session_id,
        "voice_identity",
        "elevenlabs",
        str(voice["voice_id"]),
        {
            "generated_voice_id": generated_voice_id,
            "selected_preview_index": index,
            "selected_preview_asset_id": selected_preview_asset_id,
            "voice_name": voice.get("name") or provider._voice_name(profile),
            "voice_profile": profile,
        },
        selected=True,
    )
    return {
        "ok": True,
        "voice_id": voice["voice_id"],
        "voice_profile": profile,
        "asset_id": voice_identity_asset_id,
        "selected_preview_asset_id": selected_preview_asset_id,
    }


@app.post("/api/sessions/{session_id}/dialogue-rehearsal")
async def dialogue_rehearsal(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    """Run a full dialogue turn: Director → Line Writer → Performance → TTS.

    Takes a user line and optional scene context, returns the full beat analysis,
    the OC's response line, and optionally generated audio.
    """
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_line = body.get("user_line", "").strip()
    if not user_line:
        raise HTTPException(status_code=400, detail="user_line is required")

    scene_context = body.get("scene_context", "") or draft.scenario or ""
    relationship_context = body.get("relationship_context", "")
    generate_audio = body.get("generate_audio", False)

    from .oc_dialogue_director import direct_beat
    from .oc_line_writer import write_lines
    from .oc_dialogue_performance import analyze_performance

    # 1. Director: analyze the beat
    beat = await direct_beat(
        draft, user_line,
        scene_context=scene_context,
        relationship_context=relationship_context,
        history_context=body.get("history_context", ""),
    )

    # 2. Line Writer: generate OC response text (one line)
    line_result = await write_lines(draft, count=1)
    lines = line_result.get("lines", [])
    response_text = lines[0].get("text", "") if lines else ""
    response_emotion = lines[0].get("emotion", "") if lines else ""

    # 3. Performance Director: analyze delivery
    performance = {}
    if response_text:
        try:
            performance = await analyze_performance(response_text, draft)
        except Exception:
            pass

    # 4. TTS: generate audio if requested and ElevenLabs voice exists
    audio_url = None
    if generate_audio and response_text:
        try:
            from .config import get_config, get_project_root
            from .voice_providers.base import get_provider
            cfg = get_config()
            vc = cfg.get("voice", {})
            provider_name = vc.get("provider", "elevenlabs")
            profile = db.get_voice_profile(session_id)
            if profile:
                hints = profile.get("provider_hints", {})
                if hints.get("elevenlabs_voice_id"):
                    provider = get_provider(provider_name)
                    output_dir = get_project_root() / "exports" / "voices"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    from pathlib import Path
                    out_path = str(output_dir / f"{session_id}_rehearsal.mp3")
                    audio_path = await provider.synthesize(response_text, profile, out_path)
                    audio_url = "/exports/voices/" + Path(audio_path).name
                    profile["last_performance"] = performance
                    if performance.get("units"):
                        profile.setdefault("provider_hints", {})
                        profile["provider_hints"]["performance_units"] = performance["units"]
                    db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))
        except Exception:
            pass

    return {
        "ok": True,
        "user_line": user_line,
        "beat": beat,
        "response_text": response_text,
        "response_emotion": response_emotion,
        "performance": performance,
        "audio_url": audio_url,
    }


@app.post("/api/sessions/{session_id}/voice-reference")
async def upload_voice_reference(
    session_id: str,
    transcript: str = Form(...),
    label: str = Form(default=""),
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(auth.current_user),
):
    _require_session_access(session_id, user)
    from .config import get_project_root
    from pathlib import Path

    ext = Path(file.filename or "reference.mp3").suffix.lower() or ".mp3"
    if ext not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
        raise HTTPException(status_code=400, detail=f"不支持的音频格式: {ext}。支持: mp3, wav, m4a, aac, ogg, flac")
    mime = file.content_type or ""
    if mime and not any(mime.startswith(t) for t in ("audio/", "application/octet-stream")):
        raise HTTPException(status_code=400, detail=f"非音频文件: {mime}")
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="transcript is required")

    output_dir = get_project_root() / "data" / "voice_references" / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"fish_reference_{len(db.get_voice_references(session_id)) + 1}{ext}"
    content = await file.read(MAX_VOICE_REFERENCE_BYTES + 1)
    if len(content) > MAX_VOICE_REFERENCE_BYTES:
        raise HTTPException(status_code=413, detail="Reference audio is too large. Max size is 50MB.")
    output_path.write_bytes(content)
    ref_id = db.insert_voice_reference(session_id, str(output_path), transcript.strip(), label.strip(), "fish_audio")
    return {
        "ok": True,
        "reference": {
            "id": ref_id,
            "audio_path": str(output_path),
            "transcript": transcript.strip(),
            "label": label.strip(),
        },
    }


@app.get("/api/sessions/{session_id}/voice-references")
async def list_voice_references(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    return {"ok": True, "references": db.get_voice_references(session_id)}


# DEPRECATED: /voice-cast uses Fish Audio public model search. Main voice flow is now ElevenLabs.
# This endpoint is kept for advanced/debug purposes only. Frontend main flow does NOT call this.
@app.post("/api/sessions/{session_id}/voice-cast")
async def voice_cast(session_id: str, body: dict | None = None, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_voice_casting import cast_voice
    from .oc_voice_director import analyze_voice
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")

    profile = db.get_voice_profile(session_id)
    if not profile:
        profile = await analyze_voice(draft)
        db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))

    result = await cast_voice(draft, profile, limit=(body or {}).get("limit", 8))
    if result.get("recommendation"):
        profile.setdefault("provider_hints", {})
        profile["provider_hints"]["fish_reference_id"] = result["recommendation"]["reference_id"]
        profile["provider_hints"]["voice_casting_source"] = result["recommendation"].get("source")
        db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))
        result["voice_profile"] = profile
    else:
        result["voice_profile"] = profile
    return result


@app.get("/api/sessions/{session_id}/voices")
async def voice_history(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    _require_session_access(session_id, user)
    generations = db.get_voice_generations(session_id)
    return {"ok": True, "generations": generations}


@app.get("/api/voice-options")
async def voice_options(user: dict[str, Any] = Depends(auth.current_user)):
    from .config import get_config
    vc = get_config().get("voice", {})
    fish_cfg = vc.get("fish_audio", {})
    library = []
    for entry in fish_cfg.get("voice_library", []):
        reference_id = entry.get("reference_id", "")
        library.append({
            "label": entry.get("label", "Fish voice"),
            "reference_id": reference_id,
            "profile": entry.get("profile", {}),
            "configured": bool(reference_id),
        })
    return {
        "ok": True,
        "default_provider": vc.get("provider", "edge_tts"),
        "providers": ["elevenlabs", "edge_tts", "fish_audio"],
        "fish_requires_reference_id": False,
        "fish_prompt_without_reference": fish_cfg.get("prompt_without_reference", True),
        "fish_voice_library": library,
    }


@app.post("/api/voice-library/favorite")
async def voice_library_favorite(body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    """Save a voice model reference_id to config.yaml voice_library."""
    from pathlib import Path as _Path
    import yaml

    ref_id = (body.get("reference_id") or "").strip()
    label = (body.get("label") or "收藏音色").strip()
    profile_match = body.get("profile", {})

    if not ref_id:
        raise HTTPException(status_code=400, detail="reference_id is required")

    config_path = get_project_root() / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    library = config.setdefault("voice", {}).setdefault("fish_audio", {}).setdefault("voice_library", [])
    replaced = False
    for entry in library:
        if entry.get("reference_id") == ref_id:
            entry["label"] = label
            entry["profile"] = profile_match
            replaced = True
            break
    if not replaced:
        library.append({"reference_id": ref_id, "label": label, "profile": profile_match})

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    return {"ok": True, "reference_id": ref_id, "label": label}


@app.post("/api/reference-audios")
async def upload_reference_audio(
    label: str = Form(...),
    transcript: str | None = Form(None),
    language: str = Form(default="zh"),
    audio: UploadFile = File(...),
    user: dict[str, Any] = Depends(auth.current_user),
):
    """Upload a Chinese reference audio for voice cloning."""
    from pathlib import Path as _Path
    ref_dir = get_project_root() / "exports" / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)

    uid = user["id"]
    clean_label = label.strip()
    if not clean_label:
        raise HTTPException(status_code=400, detail="label is required")
    safe_label = "".join(c for c in clean_label if c.isalnum() or c in "._- ")[:30] or "reference"
    ext = _Path(audio.filename or "reference.mp3").suffix.lower() or ".mp3"
    if ext not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    fname = f"ref_{uid}_{safe_label}{ext}"
    file_path = ref_dir / fname

    content = await audio.read(MAX_VOICE_REFERENCE_BYTES + 1)
    if len(content) > MAX_VOICE_REFERENCE_BYTES:
        raise HTTPException(status_code=413, detail="Reference audio is too large. Max size is 50MB.")
    file_path.write_bytes(content)

    db.insert_reference_audio(int(uid), clean_label, str(file_path), transcript, language)
    return {"ok": True, "file_path": str(file_path), "label": clean_label}


@app.get("/api/reference-audios")
async def list_reference_audios(user: dict[str, Any] = Depends(auth.current_user)):
    audios = db.get_reference_audios(int(user["id"]))
    return {"ok": True, "audios": audios}


# ─── Auth endpoints ───────────────────────────────────

@app.post("/api/auth/register")
def register(req: RegisterRequest, response: Response):
    user = auth.create_user(req.username, req.password, req.nickname)
    token = auth.create_session(int(user["id"]))
    auth.set_session_cookie(response, token)
    return {"ok": True, "user": auth.public_user(user)}


@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response):
    user = auth.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth.create_session(int(user["id"]))
    auth.set_session_cookie(response, token)
    return {"ok": True, "user": auth.public_user(user)}


@app.post("/api/auth/guest")
def guest_login(response: Response):
    user = auth.create_guest_user()
    token = auth.create_session(int(user["id"]), max_age=auth.GUEST_SECONDS)
    auth.set_session_cookie(response, token, max_age=auth.GUEST_SECONDS)
    return {"ok": True, "user": auth.public_user(user)}


@app.post("/api/auth/logout")
def logout(response: Response, request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    auth.clear_session(response, token)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(auth.current_user)):
    return {"ok": True, "user": auth.public_user(user)}


