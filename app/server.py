"""FastAPI server entry point for Mnemosyne Forge.

Serves the web frontend at root path and API endpoints under /api/.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, db, oc_session
from .config import get_app_config, get_project_root

app = FastAPI(title="Mnemosyne Forge", version="0.1.0")

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


# --- Sessions ---

def _require_session_access(session_id: str, user: dict[str, Any]) -> None:
    is_admin = user.get("role") == "admin"
    if not db.session_belongs_to_user(session_id, _forge_user_id(user), is_admin=is_admin):
        raise HTTPException(status_code=404, detail="Session not found")


def _forge_user_id(user: dict[str, Any]) -> int:
    return int(user.get("forge_user_id") or user["id"])


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
    deleted = db.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


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
    _require_session_access(session_id, user)
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    style = body.get("style", "anime portrait")
    prompt = await build_image_prompt(draft, style)
    audit = await audit_image_prompt(draft, prompt)
    result = await generate_character_image(draft, style)
    result["audit"] = audit
    return result


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

    text = body.get("text") or profile.get("sample_text", "你好。")
    output_dir = get_project_root() / vc.get("output_dir", "exports/voices")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"{session_id}_{provider_name}.mp3")

    try:
        provider = get_provider(provider_name)
        result_path = await provider.synthesize(text, profile, output_path)
        db.insert_voice_generation(session_id, provider_name, text, json.dumps(profile, ensure_ascii=False), result_path)
        from pathlib import Path
        audio_url = "/exports/voices/" + Path(result_path).name
        return {"ok": True, "audio_path": result_path, "audio_url": audio_url, "provider": provider_name}
    except Exception as e:
        db.insert_voice_generation(session_id, provider_name, text, json.dumps(profile, ensure_ascii=False), status="failed", error_message=str(e))
        return {"ok": False, "error": str(e)}


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
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="transcript is required")

    output_dir = get_project_root() / "data" / "voice_references" / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"fish_reference_{len(db.get_voice_references(session_id)) + 1}{ext}"
    content = await file.read()
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
        "providers": ["edge_tts", "fish_audio"],
        "fish_requires_reference_id": False,
        "fish_prompt_without_reference": fish_cfg.get("prompt_without_reference", True),
        "fish_voice_library": library,
    }


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
