from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from studio.domain.constants import ApprovalStatus, JobStatus, ProjectStage, ProjectStatus
from studio.persistence.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Project(Timestamps, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.DRAFT.value, nullable=False)
    genre: Mapped[str | None] = mapped_column(String(64))
    current_stage: Mapped[str] = mapped_column(String(32), default=ProjectStage.IDEATION.value, nullable=False)


class IdeaCandidate(Timestamps, Base):
    __tablename__ = "idea_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    premise: Mapped[str] = mapped_column(Text, nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source_run: Mapped[str] = mapped_column(String(36), nullable=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StoryVersion(Timestamps, Base):
    __tablename__ = "story_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_story_versions_project_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    critique: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(String(32), default=ApprovalStatus.DRAFT.value, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VisualBibleVersion(Timestamps, Base):
    __tablename__ = "visual_bible_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_visual_bibles_project_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), default=ApprovalStatus.DRAFT.value, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Scene(Timestamps, Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("story_version_id", "scene_order", name="uq_scenes_story_version_order"),
        CheckConstraint("duration_sec > 0", name="ck_scenes_positive_duration"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    story_version_id: Mapped[str] = mapped_column(
        ForeignKey("story_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_order: Mapped[int] = mapped_column(Integer, nullable=False)
    narration: Mapped[str] = mapped_column(Text, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    visual_intent: Mapped[str | None] = mapped_column(Text)
    visual_prompt: Mapped[str | None] = mapped_column(Text)
    motion: Mapped[str | None] = mapped_column(String(64))
    caption_emphasis: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sfx: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class Asset(Timestamps, Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    local_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")


class AssetSelection(Timestamps, Base):
    __tablename__ = "asset_selections"

    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True)
    selected_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)


class NarrationVersion(Timestamps, Base):
    __tablename__ = "narration_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_narration_versions_project_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    voice: Mapped[str | None] = mapped_column(String(128))
    audio_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), default=ApprovalStatus.DRAFT.value, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaptionTrack(Timestamps, Base):
    __tablename__ = "caption_tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    narration_version_id: Mapped[str] = mapped_column(
        ForeignKey("narration_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    word_timings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    srt_uri: Mapped[str | None] = mapped_column(String(1024))
    json_uri: Mapped[str | None] = mapped_column(String(1024))


class GenerationJob(Timestamps, Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        CheckConstraint("attempt >= 1", name="ck_generation_jobs_attempt_positive"),
        CheckConstraint("max_attempts >= 1", name="ck_generation_jobs_max_attempts_positive"),
        CheckConstraint("attempt <= max_attempts", name="ck_generation_jobs_attempt_within_limit"),
        CheckConstraint("progress >= 0 AND progress <= 1", name="ck_generation_jobs_progress_range"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    outcome: Mapped[str | None] = mapped_column(String(32))
    usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    regeneration_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timeline_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Render(Timestamps, Base):
    __tablename__ = "renders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    story_version_id: Mapped[str | None] = mapped_column(ForeignKey("story_versions.id"), index=True)
    render_type: Mapped[str] = mapped_column(String(16), nullable=False)
    uri: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value, nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    preview_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Publication(Timestamps, Base):
    __tablename__ = "publications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048))
    external_id: Mapped[str | None] = mapped_column(String(256))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MetricSnapshot(Timestamps, Base):
    __tablename__ = "metric_snapshots"
    __table_args__ = (
        CheckConstraint("views >= 0", name="ck_metric_snapshots_views_nonnegative"),
        CheckConstraint("likes >= 0", name="ck_metric_snapshots_likes_nonnegative"),
        CheckConstraint("comments >= 0", name="ck_metric_snapshots_comments_nonnegative"),
        CheckConstraint("shares_saves >= 0", name="ck_metric_snapshots_shares_nonnegative"),
        CheckConstraint("followers_gained >= 0", name="ck_metric_snapshots_followers_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retention: Mapped[float | None] = mapped_column(Float)
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shares_saves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    followers_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
