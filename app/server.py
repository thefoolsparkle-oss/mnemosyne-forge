"""FastAPI server entry point for Mnemosyne Forge.

Serves the web frontend at root path and API endpoints under /api/.
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
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


# --- Health ---

@app.get("/health")
async def health():
    return {"ok": True, "service": "Mnemosyne Forge"}


# --- Sessions ---

@app.post("/api/sessions")
async def create_session(body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    initial_idea = body.get("initial_idea", "").strip()
    if not initial_idea:
        raise HTTPException(status_code=400, detail="initial_idea is required")

    fast_mode = body.get("fast_mode", False)
    user_id = int(user["id"])

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
        sessions = db.list_sessions(user_id=None if is_admin else int(user["id"]))
        return {"ok": True, "sessions": sessions, "is_admin": is_admin}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/api/sessions/{session_id}/resume")
async def resume_session(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    """Load a session for resuming — returns draft + messages."""
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await oc_session.get_session_messages(session_id)
    return {"ok": True, "session_id": session_id, "draft": draft.model_dump(), "messages": messages}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    deleted = db.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@app.get("/api/sessions/{session_id}/draft")
async def get_draft(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, "draft": draft.model_dump()}


@app.patch("/api/sessions/{session_id}/draft")
async def update_draft(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    """Update specific draft fields manually."""
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = body.get("updates", {})
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
    messages = await oc_session.get_session_messages(session_id)
    return {"ok": True, "messages": messages}


@app.post("/api/sessions/{session_id}/messages")
async def send_message(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
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
    try:
        result = await oc_session.export_session_card(session_id)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/api/sessions/{session_id}/export/download")
async def download_card(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    """Download the already-exported card JSON file directly, without re-generating."""
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

    filename = f"{card_data['data']['name']}_card.json"
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
    runs = db.get_search_runs(session_id)
    return {"ok": True, "runs": runs}


# ─── World generation ──────────────────────────────────

@app.post("/api/sessions/{session_id}/world")
async def generate_world(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_world import generate_world as gen_world
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
    export = await do_export(session_id)
    if not export.get("ok"):
        return export
    draft = await oc_session.get_session_draft(session_id)
    return await do_import(session_id, export["card"], draft)


@app.get("/api/sessions/{session_id}/image-prompt")
async def image_prompt(session_id: str, style: str = "anime portrait", user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_image_gen import build_image_prompt
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    prompt = await build_image_prompt(draft, style)
    return {"ok": True, "prompt": prompt}


@app.post("/api/sessions/{session_id}/image")
async def generate_image(session_id: str, body: dict, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_image_gen import generate_character_image
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    style = body.get("style", "anime portrait")
    result = await generate_character_image(draft, style)
    return result


@app.get("/api/sessions/{session_id}/voice-profile")
async def voice_profile(session_id: str, user: dict[str, Any] = Depends(auth.current_user)):
    from .oc_voice_gen import match_voice_profile, generate_character_voice
    draft = await oc_session.get_session_draft(session_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return await generate_character_voice(draft)


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
