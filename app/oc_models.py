"""Pydantic v2 data models for Mnemosyne Forge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OCDraft(BaseModel):
    """Internal draft model for original character creation.

    Fields can be None during creation; they fill in progressively.
    locked_fields prevents the Designer Agent from overwriting confirmed values.
    """

    name: str | None = None
    gender: str | None = None
    age_range: str | None = None
    role_type: str | None = None

    core_concept: str | None = None
    personality: list[str] = Field(default_factory=list)
    appearance: str | None = None
    background: str | None = None
    abilities: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)

    speaking_style: str | None = None
    scenario: str | None = None
    first_message: str | None = None
    example_dialogue: str | None = None

    themes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    user_preferences: list[str] = Field(default_factory=list)
    locked_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)

    current_stage: str = "core_concept"
    completion_score: float = 0.0


class OCSession(BaseModel):
    """A single character creation session."""

    session_id: str
    title: str
    draft: OCDraft
    created_at: str
    updated_at: str
    status: str = "active"


class ChatMessage(BaseModel):
    """A single chat message in a session."""

    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str


# --- Character Card V2 models ---


class TavernCardData(BaseModel):
    name: str
    description: str
    personality: str
    scenario: str
    first_mes: str
    mes_example: str
    creator_notes: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    alternate_greetings: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    creator: str = "Mnemosyne Forge"
    character_version: str = "0.1"
    extensions: dict = Field(default_factory=dict)


class TavernCardV2(BaseModel):
    spec: str = "chara_card_v2"
    spec_version: str = "2.0"
    data: TavernCardData


# ─── Search models ─────────────────────────────────────


class SearchQueryPlan(BaseModel):
    should_search: bool = False
    reason: str | None = None
    category: str | None = None
    queries: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source: str = ""
    query: str
    score: float = 0.0


class InspirationCard(BaseModel):
    title: str
    summary: str
    usable_ideas: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    related_fields: list[str] = Field(default_factory=list)
    sources: list[SearchResult] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    mode: str = "manual"


class SearchResponse(BaseModel):
    ok: bool
    inspiration: InspirationCard | None = None
    results: list[SearchResult] = Field(default_factory=list)
    error: str | None = None


# ─── Image models ──────────────────────────────────────


class ImagePromptRequest(BaseModel):
    style: str = "anime portrait"
    aspect_ratio: str = "1:1"
    detail_level: str = "medium"
    include_background: bool = True


class ImagePromptResult(BaseModel):
    positive_prompt: str
    negative_prompt: str = ""
    style_notes: str = ""
    missing_visual_fields: list[str] = Field(default_factory=list)
    recommended_aspect_ratio: str = "1:1"


class GeneratedImageAsset(BaseModel):
    session_id: str
    provider: str
    prompt: str
    negative_prompt: str | None = None
    image_path: str | None = None
    seed: int | None = None
    width: int | None = None
    height: int | None = None
    created_at: str = ""


# ─── Voice models ──────────────────────────────────────


class VoiceProfile(BaseModel):
    template_id: str
    display_name: str
    gender_tone: str | None = None
    age_tone: str | None = None
    timbre: str = ""
    pitch: str = ""
    speed: str = ""
    emotion: str = ""
    speaking_style: str = ""
    sample_text: str = ""
    provider_params: dict = Field(default_factory=dict)
