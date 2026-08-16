from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.domain.schemas.contracts import StorySpec
from studio.persistence.models import (
    Asset,
    AssetSelection,
    CaptionTrack,
    NarrationVersion,
    Render,
    Scene,
    StoryVersion,
)
from studio.storage.local import LocalArtifactStorage


RENDER_WIDTH = 1080
RENDER_HEIGHT = 1920
RENDER_FPS = 30


class RenderValidationError(ValueError):
    pass


class RenderContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RenderCaption(RenderContract):
    word: str = Field(min_length=1)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "RenderCaption":
        if self.end_sec <= self.start_sec:
            raise ValueError("caption end must be after caption start")
        return self


class RenderScene(RenderContract):
    id: str = Field(min_length=1)
    order: int = Field(ge=1)
    duration_sec: float = Field(gt=0)
    duration_in_frames: int = Field(ge=1)
    narration: str = Field(min_length=1)
    motion: str = Field(default="static", min_length=1)
    asset_path: str = Field(min_length=1)
    asset_kind: Literal["image", "video"]
    sfx: list[str] = Field(default_factory=list)


class RenderManifest(RenderContract):
    schema_version: Literal[1] = 1
    project_id: str = Field(min_length=1)
    render_id: str = Field(min_length=1)
    render_type: Literal["preview", "final"]
    width: Literal[1080] = RENDER_WIDTH
    height: Literal[1920] = RENDER_HEIGHT
    fps: Literal[30] = RENDER_FPS
    duration_sec: float = Field(gt=0)
    duration_in_frames: int = Field(ge=1)
    scenes: list[RenderScene] = Field(min_length=1)
    narration_path: str = Field(min_length=1)
    narration_duration_sec: float = Field(gt=0)
    captions: list[RenderCaption] = Field(min_length=1)
    music_path: str | None = None
    sfx_paths: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_timeline(self) -> "RenderManifest":
        if sum(scene.duration_in_frames for scene in self.scenes) != self.duration_in_frames:
            raise ValueError("scene frames must cover the complete render timeline")
        previous_end = 0.0
        for caption in self.captions:
            if caption.start_sec < previous_end:
                raise ValueError("captions must be ordered and non-overlapping")
            if caption.end_sec > self.duration_sec + (1 / self.fps):
                raise ValueError("caption timing exceeds render duration")
            previous_end = caption.end_sec
        if self.narration_duration_sec > self.duration_sec + 1:
            raise ValueError("narration is longer than the scene timeline")
        if self.music_path is None and self.duration_sec > self.narration_duration_sec + 1:
            raise ValueError("scene timeline leaves dead air after narration")
        return self


def build_render_manifest(
    session: Session,
    *,
    render: Render,
    narration_version_id: str,
    storage: LocalArtifactStorage,
    music_asset_id: str | None = None,
    sfx_asset_ids: dict[str, str] | None = None,
) -> RenderManifest:
    story = session.get(StoryVersion, render.story_version_id)
    if story is None or story.approval_status != "approved":
        raise RenderValidationError("an approved StorySpec is required for rendering")
    narration = session.get(NarrationVersion, narration_version_id)
    if narration is None or narration.project_id != render.project_id:
        raise RenderValidationError("the render narration does not belong to the project")
    if narration.approval_status != "approved":
        raise RenderValidationError("an approved narration is required for rendering")
    track = session.scalar(select(CaptionTrack).where(CaptionTrack.narration_version_id == narration.id))
    if track is None or not track.word_timings:
        raise RenderValidationError("approved narration captions are required for rendering")

    story_spec = StorySpec.model_validate(story.payload)
    scenes = list(
        session.scalars(
            select(Scene).where(Scene.story_version_id == story.id).order_by(Scene.scene_order.asc())
        )
    )
    if len(scenes) != len(story_spec.scenes):
        raise RenderValidationError("storyboard scenes are incomplete for rendering")

    render_scenes: list[RenderScene] = []
    for scene in scenes:
        selection = session.get(AssetSelection, scene.id)
        asset = session.get(Asset, selection.selected_asset_id) if selection else None
        if asset is None or asset.scene_id != scene.id or asset.status != "available":
            raise RenderValidationError(f"scene {scene.scene_order} needs a selected available asset")
        asset_path = _artifact_path(storage, asset.local_uri, f"scene {scene.scene_order} asset")
        frame_count = max(1, round(scene.duration_sec * RENDER_FPS))
        render_scenes.append(
            RenderScene(
                id=scene.id,
                order=scene.scene_order,
                duration_sec=frame_count / RENDER_FPS,
                duration_in_frames=frame_count,
                narration=scene.narration,
                motion=scene.motion or "static",
                asset_path=str(asset_path),
                asset_kind=_asset_kind(asset.asset_type),
                sfx=scene.sfx,
            )
        )

    optional_music = _optional_asset_path(
        session,
        storage=storage,
        project_id=render.project_id,
        asset_id=music_asset_id,
        label="music",
        allowed_types=("music", "audio", "background_music"),
    )
    optional_sfx = {
        name: path
        for name, asset_id in (sfx_asset_ids or {}).items()
        if (path := _optional_asset_path(
            session,
            storage=storage,
            project_id=render.project_id,
            asset_id=asset_id,
            label=f"SFX {name}",
            allowed_types=("sfx", "audio", "sound_effect"),
        ))
    }
    duration_in_frames = sum(scene.duration_in_frames for scene in render_scenes)
    return RenderManifest(
        project_id=render.project_id,
        render_id=render.id,
        render_type=render.render_type,
        duration_sec=duration_in_frames / RENDER_FPS,
        duration_in_frames=duration_in_frames,
        scenes=render_scenes,
        narration_path=str(_artifact_path(storage, narration.audio_uri, "narration")),
        narration_duration_sec=narration.duration_sec,
        captions=[RenderCaption.model_validate(timing) for timing in track.word_timings],
        music_path=optional_music,
        sfx_paths=optional_sfx,
    )


def _artifact_path(storage: LocalArtifactStorage, uri: str, label: str) -> Path:
    path = storage.path_for_uri(uri)
    if not path.is_file():
        raise RenderValidationError(f"{label} is missing from artifact storage")
    return path


def _optional_asset_path(
    session: Session,
    *,
    storage: LocalArtifactStorage,
    project_id: str,
    asset_id: str | None,
    label: str,
    allowed_types: tuple[str, ...],
) -> str | None:
    if asset_id is None:
        return None
    asset = session.get(Asset, asset_id)
    if asset is None or asset.project_id != project_id or asset.status != "available":
        raise RenderValidationError(f"{label} asset is not available in the project")
    if asset.asset_type not in allowed_types:
        raise RenderValidationError(f"{label} asset has unsupported type: {asset.asset_type}")
    return str(_artifact_path(storage, asset.local_uri, label))


def _asset_kind(asset_type: str) -> Literal["image", "video"]:
    if "video" in asset_type:
        return "video"
    if "image" in asset_type or "photo" in asset_type:
        return "image"
    raise RenderValidationError(f"unsupported selected asset type: {asset_type}")
