from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studio.domain.constants import JobStatus
from studio.domain.schemas.contracts import IdeaScores, StorySpec, VisualBible


class APIContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectCreateRequest(APIContract):
    title: str = Field(min_length=1, max_length=200)
    genre: str | None = Field(default=None, max_length=64)


class ProjectResponse(APIContract):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: str
    genre: str | None
    current_stage: str
    created_at: datetime
    updated_at: datetime


class GenerationJobCreateRequest(APIContract):
    type: str = Field(min_length=1, max_length=64)
    version: int | str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=3)


class GenerationJobTimelineEvent(APIContract):
    occurred_at: datetime
    project_id: str
    job_id: str
    provider: str | None
    model: str | None
    stage: str
    attempt: int
    status: JobStatus
    outcome: str
    latency_ms: float | None
    usage: dict[str, Any] | None
    cost_usd: float | None
    regeneration_count: int
    error_code: str | None
    error_message: str | None


class GenerationJobResponse(APIContract):
    id: str
    project_id: str
    type: str
    stage: str
    status: JobStatus
    provider: str | None
    model: str | None
    attempt: int
    max_attempts: int
    progress: float
    idempotency_key: str
    latency_ms: float | None
    outcome: str | None
    usage: dict[str, Any] | None
    cost_usd: float | None
    regeneration_count: int
    timeline: list[GenerationJobTimelineEvent] = Field(default_factory=list)
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class GenerationJobSubmissionResponse(APIContract):
    job: GenerationJobResponse
    created: bool
    dispatched: bool


class CreativeGenerateRequest(APIContract):
    run_key: str = Field(min_length=1, max_length=128)


class IdeaCandidateResponse(APIContract):
    id: str
    project_id: str
    premise: str
    hook: str
    scores: IdeaScores
    rationale: str
    source_run: str
    is_selected: bool
    created_at: datetime
    updated_at: datetime


class StoryVersionResponse(APIContract):
    id: str
    project_id: str
    version: int
    story: StorySpec
    critique: dict | None
    provider: str | None
    model: str | None
    rejection_reason: str | None
    approval_status: str
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VisualBibleGenerationRequest(APIContract):
    run_key: str = Field(min_length=1, max_length=128)


class VisualBibleEditRequest(APIContract):
    visual_bible: VisualBible


class VisualBibleResponse(APIContract):
    id: str
    project_id: str
    version: int
    visual_bible: VisualBible
    approval_status: str
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NarrationGenerateRequest(APIContract):
    run_key: str = Field(min_length=1, max_length=128)
    text: str | None = Field(default=None, min_length=1, max_length=10000)
    voice: str = Field(default="Kore", min_length=1, max_length=128)
    direction: str | None = Field(default=None, max_length=2000)


class CaptionAlignRequest(APIContract):
    run_key: str = Field(min_length=1, max_length=128)
    narration_version_id: str = Field(min_length=1, max_length=36)
    language: str | None = Field(default="en", min_length=2, max_length=8)


class RenderCreateRequest(APIContract):
    run_key: str = Field(min_length=1, max_length=128)
    music_asset_id: str | None = Field(default=None, min_length=1, max_length=36)
    sfx_asset_ids: dict[str, str] = Field(default_factory=dict, max_length=16)


class RenderResponse(APIContract):
    id: str
    project_id: str
    story_version_id: str | None
    render_type: Literal["preview", "final"]
    uri: str | None
    content_url: str | None
    status: JobStatus
    duration_sec: float | None
    preview_approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RenderJobSubmissionResponse(APIContract):
    render: RenderResponse
    job: GenerationJobResponse
    created: bool
    dispatched: bool


class PublicationCreateRequest(APIContract):
    platform: str = Field(min_length=1, max_length=64)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    external_id: str | None = Field(default=None, min_length=1, max_length=256)
    published_at: datetime | None = None


class MetricSnapshotCreateRequest(APIContract):
    captured_at: datetime | None = None
    views: int = Field(default=0, ge=0)
    retention: float | None = Field(default=None, ge=0, le=100)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares_saves: int = Field(default=0, ge=0)
    followers_gained: int = Field(default=0, ge=0)


class MetricSnapshotResponse(APIContract):
    id: str
    publication_id: str
    captured_at: datetime
    views: int
    retention: float | None
    likes: int
    comments: int
    shares_saves: int
    followers_gained: int
    created_at: datetime
    updated_at: datetime


class PublicationResponse(APIContract):
    id: str
    project_id: str
    platform: str
    url: str | None
    external_id: str | None
    published_at: datetime | None
    metrics: list[MetricSnapshotResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CaptionTrackResponse(APIContract):
    id: str
    narration_version_id: str
    word_timings: list[dict[str, Any]]
    srt_url: str | None
    json_url: str | None
    created_at: datetime
    updated_at: datetime


class NarrationVersionResponse(APIContract):
    id: str
    project_id: str
    version: int
    provider: str
    model: str | None
    voice: str | None
    audio_url: str
    duration_sec: float
    approval_status: str
    approved_at: datetime | None
    caption_track: CaptionTrackResponse | None
    created_at: datetime
    updated_at: datetime


class AssetResponse(APIContract):
    id: str
    project_id: str
    scene_id: str | None
    asset_type: str
    provider: str | None
    model: str | None
    local_uri: str
    content_url: str
    prompt: str | None
    metadata: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class SceneResponse(APIContract):
    id: str
    project_id: str
    story_version_id: str
    order: int
    narration: str
    duration_sec: float
    asset_strategy: str
    visual_intent: str | None
    visual_prompt: str | None
    motion: str | None
    caption_emphasis: list[str]
    sfx: list[str]
    assets: list[AssetResponse] = Field(default_factory=list)
    selected_asset_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AssetSelectionResponse(APIContract):
    scene_id: str
    selected_asset_id: str
    selected_at: datetime


class SceneAssetGenerateRequest(APIContract):
    run_key: str = Field(min_length=1, max_length=128)
    prompt: str | None = Field(default=None, min_length=1, max_length=2048)
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=10)


class StockSearchRequest(APIContract):
    run_key: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=200)
    media_type: Literal["photo", "video"] = "photo"
    orientation: Literal["portrait", "landscape", "square"] = "portrait"
    per_page: int = Field(default=6, ge=1, le=12)


class SceneEditRequest(APIContract):
    duration_sec: float | None = Field(default=None, gt=0, le=60)
    visual_prompt: str | None = Field(default=None, min_length=1)
    asset_strategy: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_change(self) -> "SceneEditRequest":
        if self.duration_sec is None and self.visual_prompt is None and self.asset_strategy is None:
            raise ValueError("at least one scene field must be provided")
        return self


class StoryEditRequest(APIContract):
    story: StorySpec


class StoryRejectionRequest(APIContract):
    reason: str = Field(min_length=1, max_length=1000)


class CreativeWorkspaceResponse(APIContract):
    project: ProjectResponse
    ideas: list[IdeaCandidateResponse]
    stories: list[StoryVersionResponse]
    visual_bibles: list[VisualBibleResponse]
    scenes: list[SceneResponse]
    narrations: list[NarrationVersionResponse]
    renders: list[RenderResponse] = Field(default_factory=list)
    publications: list[PublicationResponse] = Field(default_factory=list)
    jobs: list[GenerationJobResponse]
