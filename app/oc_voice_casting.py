"""Voice Casting Agent.

Selects a stable voice identity for an OC before performance prompting.
For Fish Audio, this means choosing a reference_id from configured voices or
public model search. Prompting controls acting; reference_id controls identity.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import get_config
from .env_utils import read_env
from .oc_models import OCDraft


BAD_CASTING_TERMS = [
    "egirl",
    "e-girl",
    "cute",
    "kawaii",
    "anime",
    "vtuber",
    "cartoon",
    "conversational",
    "assistant",
    "robot",
    "ai",
]


def _want_terms(profile: dict) -> list[str]:
    gender = str(profile.get("gender_tone") or "").lower()
    age = str(profile.get("voice_age") or "").lower()
    timbre = str(profile.get("timbre") or "").lower()
    emotion = str(profile.get("emotion_level") or "").lower()
    colors = [str(c).lower() for c in profile.get("emotional_color", []) or []]

    terms: list[str] = []
    if gender == "feminine":
        terms += ["female", "girl", "woman", "feminine"]
    elif gender == "masculine":
        terms += ["male", "boy", "man", "masculine"]
    if age in ("child", "teen"):
        terms += ["young", age]
    elif age in ("young_adult", "adult"):
        terms += ["young", "adult"]
    if timbre:
        terms.append(timbre.replace("_", " "))
    if emotion:
        terms.append(emotion.replace("_", " "))
    terms += colors
    terms += ["natural", "narration", "low", "calm"]
    return [t for t in terms if t]


def _score_model(model: dict[str, Any], terms: list[str]) -> float:
    languages = [str(lang).lower() for lang in model.get("languages", []) or []]
    if languages and not any(lang.startswith("zh") or lang in ("cmn", "yue") for lang in languages):
        return -100.0

    haystack = " ".join(
        [
            str(model.get("title") or ""),
            str(model.get("description") or ""),
            " ".join(str(t) for t in model.get("tags", []) or []),
            " ".join(str(l) for l in model.get("languages", []) or []),
        ]
    ).lower()
    score = 0.0
    for term in terms:
        if term and term in haystack:
            score += 1.0
    score += min(float(model.get("like_count") or 0) / 1000.0, 1.5)
    score += min(float(model.get("task_count") or 0) / 100000.0, 1.0)
    for bad in BAD_CASTING_TERMS:
        if bad in haystack:
            score -= 2.0
    if "zh" in languages or "chinese" in haystack or "mandarin" in haystack:
        score += 4.0
    if "natural" in haystack or "narration" in haystack or "audiobook" in haystack:
        score += 1.5
    return score


def _configured_candidates(profile: dict) -> list[dict[str, Any]]:
    cfg = get_config()
    library = cfg.get("voice", {}).get("fish_audio", {}).get("voice_library", [])
    terms = _want_terms(profile)
    candidates = []
    for entry in library:
        ref_id = entry.get("reference_id")
        if not ref_id:
            continue
        model = {
            "reference_id": ref_id,
            "title": entry.get("label", "Configured Fish voice"),
            "description": "Configured in config.yaml",
            "tags": list((entry.get("profile") or {}).values()),
            "languages": entry.get("languages", []),
            "source": "config",
        }
        model["score"] = _score_model(model, terms)
        candidates.append(model)
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


async def _search_public_models(profile: dict, limit: int = 8) -> list[dict[str, Any]]:
    cfg = get_config()
    fish_cfg = cfg.get("voice", {}).get("fish_audio", {})
    api_key = read_env(fish_cfg.get("api_key_env", "FISH_API_KEY"))
    if not api_key:
        return []

    terms = _want_terms(profile)
    search_titles = []
    if "female" in terms:
        search_titles += ["female mandarin", "female narration", "woman chinese", "soft female", "female calm"]
    elif "male" in terms:
        search_titles += ["male mandarin", "male narration", "man chinese", "calm male"]
    search_titles += terms[:3]

    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for title in search_titles[:6]:
            try:
                resp = await client.get(
                    "https://api.fish.audio/model",
                    headers={"Authorization": f"Bearer {api_key}"},
                    params={"title": title, "page_size": 10, "page_number": 1, "sort_by": "score"},
                )
            except Exception:
                continue
            if resp.status_code != 200:
                continue
            for model in resp.json().get("items", []) or []:
                ref_id = model.get("_id")
                if not ref_id or ref_id in seen:
                    continue
                seen.add(ref_id)
                item = {
                    "reference_id": ref_id,
                    "title": model.get("title", ""),
                    "description": model.get("description", ""),
                    "tags": model.get("tags", []) or [],
                    "languages": model.get("languages", []) or [],
                    "like_count": model.get("like_count", 0),
                    "task_count": model.get("task_count", 0),
                    "source": "fish_public_model",
                }
                item["score"] = _score_model(item, terms)
                candidates.append(item)

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


async def cast_voice(draft: OCDraft, profile: dict, limit: int = 8) -> dict:
    """Return ranked Fish voice identity candidates for this OC."""
    configured = [c for c in _configured_candidates(profile) if c.get("score", 0) > -50]
    public = [c for c in await _search_public_models(profile, limit=limit) if c.get("score", 0) > -50]
    candidates = sorted(configured + public, key=lambda item: item.get("score", 0), reverse=True)[:limit]
    recommendation = candidates[0] if candidates and candidates[0].get("score", 0) >= 3.0 else None
    return {
        "ok": True,
        "strategy": (
            "中文角色必须先锁定可读中文的 reference_id 或 reference audio。"
            "Fish public 英文/二次元/assistant 模型会导致中文崩坏，不应自动推荐。"
        ),
        "needs_reference_audio": recommendation is None,
        "warning": None if recommendation else "未找到高可信中文 Fish 声音底座；请提供中文 reference audio 或配置可靠中文 reference_id。",
        "wanted_terms": _want_terms(profile),
        "recommendation": recommendation,
        "candidates": candidates,
    }
