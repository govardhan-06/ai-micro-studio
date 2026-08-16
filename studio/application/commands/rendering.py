from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.application.workflows.dispatch import enqueue_generation_job
from studio.domain.constants import ApprovalStatus
from studio.persistence.models import CaptionTrack, NarrationVersion, Render, StoryVersion
from studio.rendering.manifest import RenderValidationError, build_render_manifest
from studio.storage.local import create_artifact_storage


RenderType = Literal["preview", "final"]


class RenderRecordNotFoundError(LookupError):
    pass


def approve_preview(session: Session, *, project_id: str, render_id: str) -> Render:
    render = get_render(session, render_id=render_id)
    if render.project_id != project_id:
        raise RenderRecordNotFoundError(f"render {render_id} not found")
    if render.render_type != "preview":
        raise RenderValidationError("only preview renders can be approved")
    if render.status != "succeeded":
        raise RenderValidationError("a succeeded preview render is required for approval")
    render.preview_approved_at = datetime.now(timezone.utc)
    session.flush()
    return render


def render_request_id(
    *,
    project_id: str,
    render_type: RenderType,
    run_key: str,
    story_version_id: str,
    narration_version_id: str,
    music_asset_id: str | None,
    sfx_asset_ids: dict[str, str],
) -> str:
    payload = json.dumps(
        {
            "project_id": project_id,
            "render_type": render_type,
            "run_key": run_key,
            "story_version_id": story_version_id,
            "narration_version_id": narration_version_id,
            "music_asset_id": music_asset_id,
            "sfx_asset_ids": sfx_asset_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid5(NAMESPACE_URL, f"ai-micro-story-render:{payload}"))


def prepare_render_request(
    session: Session,
    *,
    project_id: str,
    render_type: RenderType,
    run_key: str,
    music_asset_id: str | None = None,
    sfx_asset_ids: dict[str, str] | None = None,
) -> tuple[Render, dict[str, object]]:
    story = session.scalar(
        select(StoryVersion)
        .where(
            StoryVersion.project_id == project_id,
            StoryVersion.approval_status == ApprovalStatus.APPROVED.value,
        )
        .order_by(StoryVersion.version.desc())
    )
    narration = session.scalar(
        select(NarrationVersion)
        .where(
            NarrationVersion.project_id == project_id,
            NarrationVersion.approval_status == ApprovalStatus.APPROVED.value,
        )
        .order_by(NarrationVersion.version.desc())
    )
    if story is None:
        raise RenderValidationError("an approved StorySpec is required for rendering")
    if narration is None:
        raise RenderValidationError("an approved narration is required for rendering")
    track = session.scalar(select(CaptionTrack).where(CaptionTrack.narration_version_id == narration.id))
    if track is None or not track.word_timings:
        raise RenderValidationError("approved narration captions are required for rendering")
    if render_type == "final":
        approved_preview = session.scalar(
            select(Render)
            .where(
                Render.project_id == project_id,
                Render.story_version_id == story.id,
                Render.render_type == "preview",
                Render.status == "succeeded",
                Render.preview_approved_at.is_not(None),
            )
            .order_by(Render.preview_approved_at.desc())
        )
        if approved_preview is None:
            raise RenderValidationError("an approved successful preview is required before final export")

    sfx_ids = dict(sfx_asset_ids or {})
    render_id = render_request_id(
        project_id=project_id,
        render_type=render_type,
        run_key=run_key,
        story_version_id=story.id,
        narration_version_id=narration.id,
        music_asset_id=music_asset_id,
        sfx_asset_ids=sfx_ids,
    )
    render = session.get(Render, render_id)
    if render is None:
        render = Render(
            id=render_id,
            project_id=project_id,
            story_version_id=story.id,
            render_type=render_type,
            status="queued",
        )
        session.add(render)
        session.flush()
    request: dict[str, object] = {
        "run_key": run_key,
        "render_id": render.id,
        "narration_version_id": narration.id,
        "music_asset_id": music_asset_id,
        "sfx_asset_ids": sfx_ids,
    }
    build_render_manifest(
        session,
        render=render,
        narration_version_id=narration.id,
        storage=create_artifact_storage(),
        music_asset_id=music_asset_id,
        sfx_asset_ids=sfx_ids,
    )
    return render, request


def enqueue_render_job(
    session: Session,
    dispatcher,
    *,
    project_id: str,
    render_type: RenderType,
    run_key: str,
    music_asset_id: str | None = None,
    sfx_asset_ids: dict[str, str] | None = None,
):
    render, request = prepare_render_request(
        session,
        project_id=project_id,
        render_type=render_type,
        run_key=run_key,
        music_asset_id=music_asset_id,
        sfx_asset_ids=sfx_asset_ids,
    )
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type=f"render_{render_type}",
            version=render.id,
            request=request,
            provider="remotion",
            model="remotion-4",
            max_attempts=3,
        )
    except Exception:
        render.status = "failed"
        session.commit()
        raise
    return render, job, created, dispatched


def get_render(session: Session, *, render_id: str) -> Render:
    render = session.get(Render, render_id)
    if render is None:
        raise RenderRecordNotFoundError(f"render {render_id} not found")
    return render


def list_renders(session: Session, *, project_id: str) -> list[Render]:
    return list(
        session.scalars(
            select(Render).where(Render.project_id == project_id).order_by(Render.created_at.desc())
        )
    )
