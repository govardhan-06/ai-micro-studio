from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

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
    description: str = Field(min_length=1)
    palette: list[str] = Field(min_length=1)
    camera_language: list[str] = Field(min_length=1)


class VisualCharacter(Contract):
    id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    appearance: str = Field(min_length=1)
    clothing: str = Field(min_length=1)
    reference_asset_ids: list[str] = Field(default_factory=list)


class VisualLocation(Contract):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    continuity_notes: str = Field(min_length=1)


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
    "VisualBible",
]
