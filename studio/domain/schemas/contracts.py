from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studio.domain.constants import ApprovalStatus, JobStatus


Score = Annotated[float, Field(ge=0, le=10)]
SceneDuration = Annotated[float, Field(gt=0, le=60)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IdeaScores(Contract):
    hook: Score
    novelty: Score
    emotional_pull: Score
    twist_payoff: Score
    visual_potential: Score
    short_form_fit: Score


class IdeaCandidate(Contract):
    id: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    hook: str = Field(min_length=1)
    scores: IdeaScores
    rationale: str = Field(min_length=1)
    source_run: str = Field(min_length=1)


class StoryScene(Contract):
    id: str = Field(min_length=1)
    order: int = Field(ge=1)
    duration_sec: SceneDuration
    narration: str = Field(min_length=1)
    visual_intent: str = Field(min_length=1)
    asset_strategy: str = Field(min_length=1)
    visual_prompt: str = Field(min_length=1)
    motion: str = Field(min_length=1)
    caption_emphasis: list[str] = Field(default_factory=list)
    sfx: list[str] = Field(default_factory=list)


class StorySpec(Contract):
    id: str = Field(min_length=1)
    working_title: str = Field(min_length=1)
    genre: str = Field(min_length=1)
    target_duration_sec: float = Field(gt=0, le=180)
    premise: str = Field(min_length=1)
    hook: str = Field(min_length=1)
    narration: str = Field(min_length=1)
    ending_type: str = Field(min_length=1)
    tone: list[str] = Field(min_length=1)
    scenes: list[StoryScene] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scenes(self) -> "StorySpec":
        scene_ids = [scene.id for scene in self.scenes]
        scene_orders = [scene.order for scene in self.scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("scene ids must be unique")
        if scene_orders != list(range(1, len(self.scenes) + 1)):
            raise ValueError("scene orders must be contiguous starting at 1")
        if sum(scene.duration_sec for scene in self.scenes) > 180:
            raise ValueError("total scene duration must be at most 180 seconds")
        return self


class VisualStyle(Contract):
    lighting: str = Field(default="unspecified", min_length=1)
    lens_language: str = Field(default="unspecified", min_length=1)
    render_style: str = Field(default="unspecified", min_length=1)
    aspect_ratio: str = Field(default="9:16", min_length=1)
    description: str | None = None
    palette: list[str] = Field(default_factory=list)
    camera_language: list[str] = Field(default_factory=list)


class VisualCharacter(Contract):
    id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    age: str = Field(default="unspecified", min_length=1)
    presentation: str = Field(default="unspecified", min_length=1)
    ethnicity: str = Field(default="unspecified", min_length=1)
    face: str = Field(default="unspecified", min_length=1)
    hair: str = Field(default="unspecified", min_length=1)
    build: str = Field(default="unspecified", min_length=1)
    clothing: str = Field(default="unspecified", min_length=1)
    accessories: list[str] = Field(default_factory=list)
    immutable_traits: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    appearance: str | None = None


class VisualLocation(Contract):
    id: str = Field(min_length=1)
    name: str = Field(default="location", min_length=1)
    architecture_geometry: str = Field(default="unspecified", min_length=1)
    time: str = Field(default="unspecified", min_length=1)
    weather: str = Field(default="unspecified", min_length=1)
    lighting: str = Field(default="unspecified", min_length=1)
    persistent_props: list[str] = Field(default_factory=list)
    immutable_traits: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    description: str | None = None
    continuity_notes: str | None = None


class ReadableTextMetadata(Contract):
    requested: bool = False
    text: str | None = None
    surface: str | None = None
    placement: str | None = None


class TextOverlay(Contract):
    text: str = Field(min_length=1)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    font_size: int = Field(gt=0, le=240)
    color: str = Field(min_length=1)
    start_sec: float = Field(default=0, ge=0)
    end_sec: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "TextOverlay":
        if self.end_sec is not None and self.end_sec <= self.start_sec:
            raise ValueError("text overlay end must be after start")
        return self


class ShotSpec(Contract):
    location_id: str = Field(min_length=1)
    character_ids: list[str] = Field(default_factory=list)
    action: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    composition: str = Field(min_length=1)
    camera: str = Field(min_length=1)
    temporary_props: list[str] = Field(default_factory=list)
    lighting: str = Field(min_length=1)
    continuity_source: list[str] = Field(default_factory=list)
    readable_text_metadata: ReadableTextMetadata = Field(default_factory=ReadableTextMetadata)
    text_overlay: TextOverlay | None = None

    @model_validator(mode="after")
    def validate_text_overlay(self) -> "ShotSpec":
        if self.text_overlay is not None and not self.readable_text_metadata.requested:
            raise ValueError("text overlay requires readable text metadata")
        return self


class VisualQAIssue(Contract):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"] = "medium"
    correction: str = Field(min_length=1)


class VisualQAResult(Contract):
    passed: bool
    score: float = Field(ge=0, le=1)
    issues: list[VisualQAIssue] = Field(default_factory=list)
    model: str = Field(min_length=1)
    checked_reference_asset_ids: list[str] = Field(default_factory=list)


class VisualBible(Contract):
    style: VisualStyle
    characters: list[VisualCharacter] = Field(default_factory=list)
    locations: list[VisualLocation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ids(self) -> "VisualBible":
        character_ids = [character.id for character in self.characters]
        location_ids = [location.id for location in self.locations]
        if len(character_ids) != len(set(character_ids)):
            raise ValueError("character ids must be unique")
        if len(location_ids) != len(set(location_ids)):
            raise ValueError("location ids must be unique")
        return self


def normalize_visual_bible(payload: dict) -> VisualBible:
    """Read both the original loose Visual Bible and the canonical shape."""
    raw = dict(payload)
    style = dict(raw.get("style") or {})
    style.setdefault("lighting", style.get("description") or "soft motivated cinematic light")
    style.setdefault("lens_language", ", ".join(style.get("camera_language") or ["natural perspective"]))
    style.setdefault("render_style", style.get("description") or "cinematic photorealism")
    style.setdefault("aspect_ratio", "9:16")
    raw["style"] = style

    characters = []
    for item in raw.get("characters") or []:
        character = dict(item)
        appearance = character.get("appearance") or "Preserve the approved character identity."
        character.setdefault("age", "adult")
        character.setdefault("presentation", "unspecified")
        character.setdefault("ethnicity", "unspecified")
        character.setdefault("face", appearance)
        character.setdefault("hair", "as approved")
        character.setdefault("build", "as approved")
        character.setdefault("clothing", character.get("clothing") or "as approved")
        character.setdefault("accessories", [])
        character.setdefault("immutable_traits", [appearance])
        character["appearance"] = appearance
        characters.append(character)
    raw["characters"] = characters

    locations = []
    for item in raw.get("locations") or []:
        location = dict(item)
        description = location.get("description") or "approved physical location"
        continuity = location.get("continuity_notes") or "Preserve geometry and persistent props."
        location.setdefault("name", location.get("id") or "location")
        location.setdefault("architecture_geometry", description)
        location.setdefault("time", "as approved")
        location.setdefault("weather", "as approved")
        location.setdefault("lighting", "as approved")
        location.setdefault("persistent_props", [])
        location.setdefault("immutable_traits", [continuity])
        location["description"] = description
        location["continuity_notes"] = continuity
        locations.append(location)
    raw["locations"] = locations
    return VisualBible.model_validate(raw)


def no_text_instruction(shot_spec: ShotSpec) -> str:
    if shot_spec.readable_text_metadata.requested:
        return "Only render the explicitly requested readable text surface; keep every other surface free of text."
    return "No readable text, letters, captions, logos, watermarks, UI text, or accidental typography."


class GenerationJobContract(Contract):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    status: JobStatus = JobStatus.QUEUED
    provider: Optional[str] = None
    model: Optional[str] = None
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    progress: float = Field(default=0, ge=0, le=1)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_attempt(self) -> "GenerationJobContract":
        if self.attempt > self.max_attempts:
            raise ValueError("attempt cannot exceed max_attempts")
        return self


__all__ = [
    "GenerationJobContract",
    "IdeaCandidate",
    "IdeaScores",
    "StoryScene",
    "StorySpec",
    "ShotSpec",
    "TextOverlay",
    "VisualQAIssue",
    "VisualQAResult",
    "ReadableTextMetadata",
    "VisualBible",
    "normalize_visual_bible",
    "no_text_instruction",
]
