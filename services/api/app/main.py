import os
from typing import Literal

import psycopg
import redis
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.application.commands.creative import (
    CreativeRecordNotFoundError,
    approve_story,
    reject_story,
    revise_story,
    select_idea,
)
from studio.application.commands.assets import (
    AssetRecordNotFoundError,
    list_reference_assets,
    list_scene_assets,
    select_scene_asset,
)
from studio.application.commands.jobs import (
    GenerationJobNotFoundError,
    ProjectNotFoundError,
)
from studio.application.commands.narration import (
    NarrationRecordNotFoundError,
    approve_narration,
    get_narration,
    list_narrations,
)
from studio.application.commands.release import (
    PublicationRecordNotFoundError,
    create_metric_snapshot,
    create_publication,
    get_publication,
    list_metric_snapshots,
    list_publications,
)
from studio.application.commands.rendering import (
    RenderRecordNotFoundError,
    approve_preview,
    enqueue_render_job,
    get_render,
    list_renders,
)
from studio.application.commands.projects import create_project
from studio.application.commands.visuals import (
    VisualRecordNotFoundError,
    approve_visual_bible,
    generate_storyboard,
    generate_visual_bible,
    missing_reference_assets,
    revise_scene,
    revise_visual_bible,
)
from studio.application.contracts import (
    CreativeGenerateRequest,
    CreativeWorkspaceResponse,
    GenerationJobCreateRequest,
    GenerationJobResponse,
    GenerationJobSubmissionResponse,
    GenerationJobTimelineEvent,
    ProjectCreateRequest,
    ProjectResponse,
    IdeaCandidateResponse,
    StoryEditRequest,
    StoryRejectionRequest,
    StoryVersionResponse,
    SceneEditRequest,
    SceneAssetGenerateRequest,
    StockSearchRequest,
    AssetResponse,
    AssetSelectionResponse,
    SceneResponse,
    VisualBibleEditRequest,
    VisualBibleGenerationRequest,
    VisualBibleResponse,
    CaptionAlignRequest,
    CaptionTrackResponse,
    NarrationGenerateRequest,
    NarrationVersionResponse,
    RenderCreateRequest,
    RenderJobSubmissionResponse,
    RenderResponse,
    MetricSnapshotCreateRequest,
    MetricSnapshotResponse,
    PublicationCreateRequest,
    PublicationResponse,
)
from studio.application.queries.creative import list_ideas, list_scenes, list_stories, list_visual_bibles
from studio.application.queries.projects import (
    get_generation_job,
    get_project,
    list_projects,
    list_project_jobs,
    normalize_generation_job_timeline,
)
from studio.application.workflows.dispatch import (
    CeleryJobDispatcher,
    JobDispatchError,
    enqueue_generation_job,
    retry_and_enqueue_generation_job,
)
from studio.application.workflows.progress import project_event_stream
from studio.domain.schemas.contracts import ShotSpec, normalize_visual_bible
from studio.domain.services.transitions import InvalidTransitionError
from studio.persistence.database import create_session_factory, session_scope
from studio.persistence.models import (
    Asset,
    CaptionTrack,
    GenerationJob,
    MetricSnapshot,
    NarrationVersion,
    Publication,
    Render,
    Scene,
    StoryVersion,
    VisualBibleVersion,
)
from studio.rendering.manifest import RenderValidationError
from studio.storage.local import create_artifact_storage


app = FastAPI(title="AI Micro-Story Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session() -> Session:
    with session_scope() as session:
        yield session


def get_session_factory():
    return create_session_factory()


def get_dispatcher() -> CeleryJobDispatcher:
    return CeleryJobDispatcher()


def _job_response(job: GenerationJob) -> GenerationJobResponse:
    return GenerationJobResponse(
        id=job.id,
        project_id=job.project_id,
        type=job.type,
        stage=job.type,
        status=job.status,
        provider=job.provider,
        model=job.model,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        progress=job.progress,
        idempotency_key=job.idempotency_key,
        latency_ms=job.latency_ms,
        outcome=job.outcome,
        usage=job.usage_json,
        cost_usd=job.cost_usd,
        regeneration_count=job.regeneration_count,
        timeline=[
            GenerationJobTimelineEvent.model_validate(event)
            for event in normalize_generation_job_timeline(job.timeline_json)
        ],
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def _idea_response(idea) -> IdeaCandidateResponse:
    return IdeaCandidateResponse(
        id=idea.id,
        project_id=idea.project_id,
        premise=idea.premise,
        hook=idea.hook,
        scores=idea.scores,
        rationale=idea.rationale,
        source_run=idea.source_run,
        is_selected=idea.is_selected,
        created_at=idea.created_at,
        updated_at=idea.updated_at,
    )


def _story_response(story) -> StoryVersionResponse:
    from studio.domain.schemas.contracts import StorySpec

    return StoryVersionResponse(
        id=story.id,
        project_id=story.project_id,
        version=story.version,
        story=StorySpec.model_validate(story.payload),
        critique=story.critique,
        provider=story.provider,
        model=story.model,
        rejection_reason=story.rejection_reason,
        approval_status=story.approval_status,
        approved_at=story.approved_at,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


def _visual_bible_response(visual_bible, session: Session | None = None) -> VisualBibleResponse:
    return VisualBibleResponse(
        id=visual_bible.id,
        project_id=visual_bible.project_id,
        version=visual_bible.version,
        visual_bible=normalize_visual_bible(visual_bible.payload),
        reference_assets=[
            _asset_response(asset).model_dump(mode="json")
            for asset in (list_reference_assets(session, project_id=visual_bible.project_id) if session else [])
        ],
        approval_status=visual_bible.approval_status,
        approved_at=visual_bible.approved_at,
        created_at=visual_bible.created_at,
        updated_at=visual_bible.updated_at,
    )


def _asset_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        project_id=asset.project_id,
        scene_id=asset.scene_id,
        asset_type=asset.asset_type,
        provider=asset.provider,
        model=asset.model,
        local_uri=asset.local_uri,
        content_url=f"/api/v1/assets/{asset.id}/content",
        prompt=asset.prompt,
        metadata=asset.metadata_json,
        status=asset.status,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _scene_response(scene, assets: list[Asset] | None = None, selection=None) -> SceneResponse:
    return SceneResponse(
        id=scene.id,
        project_id=scene.project_id,
        story_version_id=scene.story_version_id,
        order=scene.scene_order,
        narration=scene.narration,
        duration_sec=scene.duration_sec,
        asset_strategy=scene.strategy,
        visual_intent=scene.visual_intent,
        visual_prompt=scene.visual_prompt,
        motion=scene.motion,
        caption_emphasis=scene.caption_emphasis,
        sfx=scene.sfx,
        shot_spec=ShotSpec.model_validate(scene.shot_spec_json) if scene.shot_spec_json else None,
        assets=[_asset_response(asset) for asset in assets or []],
        selected_asset_id=selection.selected_asset_id if selection else None,
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )


def _caption_response(track: CaptionTrack | None) -> CaptionTrackResponse | None:
    if track is None:
        return None
    return CaptionTrackResponse(
        id=track.id,
        narration_version_id=track.narration_version_id,
        word_timings=track.word_timings,
        srt_url=f"/api/v1/captions/{track.id}/srt" if track.srt_uri else None,
        json_url=f"/api/v1/captions/{track.id}/json" if track.json_uri else None,
        created_at=track.created_at,
        updated_at=track.updated_at,
    )


def _narration_response(session: Session, narration: NarrationVersion) -> NarrationVersionResponse:
    return NarrationVersionResponse(
        id=narration.id,
        project_id=narration.project_id,
        version=narration.version,
        provider=narration.provider,
        model=narration.model,
        voice=narration.voice,
        audio_url=f"/api/v1/narrations/{narration.id}/audio",
        duration_sec=narration.duration_sec,
        approval_status=narration.approval_status,
        approved_at=narration.approved_at,
        caption_track=_caption_response(session.scalar(select(CaptionTrack).where(CaptionTrack.narration_version_id == narration.id))),
        created_at=narration.created_at,
        updated_at=narration.updated_at,
    )


def _render_response(render: Render) -> RenderResponse:
    return RenderResponse(
        id=render.id,
        project_id=render.project_id,
        story_version_id=render.story_version_id,
        render_type=render.render_type,
        uri=render.uri,
        content_url=f"/api/v1/renders/{render.id}/content" if render.uri else None,
        status=render.status,
        duration_sec=render.duration_sec,
        preview_approved_at=render.preview_approved_at,
        created_at=render.created_at,
        updated_at=render.updated_at,
    )


def _metric_response(metric: MetricSnapshot) -> MetricSnapshotResponse:
    return MetricSnapshotResponse.model_validate(metric, from_attributes=True)


def _publication_response(session: Session, publication: Publication) -> PublicationResponse:
    return PublicationResponse(
        id=publication.id,
        project_id=publication.project_id,
        platform=publication.platform,
        url=publication.url,
        external_id=publication.external_id,
        published_at=publication.published_at,
        metrics=[_metric_response(metric) for metric in list_metric_snapshots(session, publication_id=publication.id)],
        created_at=publication.created_at,
        updated_at=publication.updated_at,
    )


@app.get("/health")
def health() -> JSONResponse:
    checks = {"database": "ok", "redis": "ok"}

    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except Exception:
        checks["database"] = "unavailable"

    try:
        redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=2).ping()
    except Exception:
        checks["redis"] = "unavailable"

    status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return JSONResponse(
        status_code=200 if status == "ok" else 503,
        content={"status": status, "checks": checks},
    )


@app.post("/api/v1/projects", response_model=ProjectResponse, status_code=201)
def create_project_route(
    payload: ProjectCreateRequest,
    session: Session = Depends(get_session),
) -> ProjectResponse:
    return ProjectResponse.model_validate(create_project(session, title=payload.title, genre=payload.genre))


@app.get("/api/v1/projects", response_model=list[ProjectResponse])
def list_projects_route(session: Session = Depends(get_session)) -> list[ProjectResponse]:
    return [ProjectResponse.model_validate(project) for project in list_projects(session)]


@app.get("/api/v1/projects/{project_id}", response_model=ProjectResponse)
def get_project_route(project_id: str, session: Session = Depends(get_session)) -> ProjectResponse:
    project = get_project(session, project_id=project_id)
    if project is None:
        raise _not_found(f"project {project_id} not found")
    return ProjectResponse.model_validate(project)


@app.get("/api/v1/projects/{project_id}/workspace", response_model=CreativeWorkspaceResponse)
def get_workspace_route(project_id: str, session: Session = Depends(get_session)) -> CreativeWorkspaceResponse:
    project = get_project(session, project_id=project_id)
    if project is None:
        raise _not_found(f"project {project_id} not found")
    return CreativeWorkspaceResponse(
        project=ProjectResponse.model_validate(project),
        ideas=[_idea_response(idea) for idea in list_ideas(session, project_id=project_id)],
        stories=[_story_response(story) for story in list_stories(session, project_id=project_id)],
        visual_bibles=[_visual_bible_response(bible, session) for bible in list_visual_bibles(session, project_id=project_id)],
        scenes=[
            _scene_response(scene, *list_scene_assets(session, scene_id=scene.id))
            for scene in list_scenes(session, project_id=project_id)
        ],
        narrations=[_narration_response(session, narration) for narration in list_narrations(session, project_id=project_id)],
        renders=[_render_response(render) for render in list_renders(session, project_id=project_id)],
        publications=[_publication_response(session, publication) for publication in list_publications(session, project_id=project_id)],
        jobs=[_job_response(job) for job in list_project_jobs(session, project_id=project_id)],
    )


@app.get("/api/v1/projects/{project_id}/ideas", response_model=list[IdeaCandidateResponse])
def list_ideas_route(
    project_id: str,
    sort: str = Query(default="score"),
    session: Session = Depends(get_session),
) -> list[IdeaCandidateResponse]:
    if get_project(session, project_id=project_id) is None:
        raise _not_found(f"project {project_id} not found")
    try:
        return [_idea_response(idea) for idea in list_ideas(session, project_id=project_id, sort=sort)]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/v1/projects/{project_id}/ideas/generate",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def generate_ideas_route(
    project_id: str,
    payload: CreativeGenerateRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type="creative_package_generation",
            request={"run_key": payload.run_key},
            provider=os.getenv("LLM_PRIMARY", "nvidia_nim"),
            model=os.getenv("NIM_MODEL") if os.getenv("LLM_PRIMARY", "nvidia_nim") == "nvidia_nim" else os.getenv("GROQ_MODEL"),
            max_attempts=3,
        )
    except ProjectNotFoundError:
        raise _not_found(f"project {project_id} not found") from None
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return GenerationJobSubmissionResponse(job=_job_response(job), created=created, dispatched=dispatched)


@app.post("/api/v1/projects/{project_id}/ideas/{idea_id}/select", response_model=IdeaCandidateResponse)
def select_idea_route(
    project_id: str,
    idea_id: str,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> IdeaCandidateResponse:
    try:
        idea = select_idea(session, project_id=project_id, idea_id=idea_id)
        enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type="story_generation",
            request={"idea_id": idea_id},
            provider=os.getenv("LLM_PRIMARY", "nvidia_nim"),
            model=os.getenv("NIM_MODEL") if os.getenv("LLM_PRIMARY", "nvidia_nim") == "nvidia_nim" else os.getenv("GROQ_MODEL"),
            max_attempts=3,
        )
        return _idea_response(idea)
    except CreativeRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc


@app.get("/api/v1/projects/{project_id}/stories", response_model=list[StoryVersionResponse])
def list_stories_route(project_id: str, session: Session = Depends(get_session)) -> list[StoryVersionResponse]:
    if get_project(session, project_id=project_id) is None:
        raise _not_found(f"project {project_id} not found")
    return [_story_response(story) for story in list_stories(session, project_id=project_id)]


@app.patch("/api/v1/projects/{project_id}/stories/{story_version_id}", response_model=StoryVersionResponse)
def revise_story_route(
    project_id: str,
    story_version_id: str,
    payload: StoryEditRequest,
    session: Session = Depends(get_session),
) -> StoryVersionResponse:
    try:
        return _story_response(
            revise_story(
                session,
                project_id=project_id,
                story_version_id=story_version_id,
                story=payload.story,
            )
        )
    except CreativeRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None


@app.post("/api/v1/projects/{project_id}/stories/{story_version_id}/approve", response_model=StoryVersionResponse)
def approve_story_route(
    project_id: str,
    story_version_id: str,
    session: Session = Depends(get_session),
) -> StoryVersionResponse:
    try:
        return _story_response(approve_story(session, project_id=project_id, story_version_id=story_version_id))
    except CreativeRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/projects/{project_id}/stories/{story_version_id}/reject", response_model=StoryVersionResponse)
def reject_story_route(
    project_id: str,
    story_version_id: str,
    payload: StoryRejectionRequest,
    session: Session = Depends(get_session),
) -> StoryVersionResponse:
    try:
        return _story_response(
            reject_story(
                session,
                project_id=project_id,
                story_version_id=story_version_id,
                reason=payload.reason,
            )
        )
    except CreativeRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/v1/projects/{project_id}/visual-bible/generate",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def generate_visual_bible_route(
    project_id: str,
    payload: VisualBibleGenerationRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type="visual_bible_generation",
            request={"run_key": payload.run_key},
            provider=os.getenv("LLM_PRIMARY", "nvidia_nim"),
            model=os.getenv("NIM_MODEL") or os.getenv("GROQ_MODEL"),
            max_attempts=3,
        )
    except ProjectNotFoundError:
        raise _not_found(f"project {project_id} not found") from None
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return GenerationJobSubmissionResponse(job=_job_response(job), created=created, dispatched=dispatched)


@app.patch("/api/v1/projects/{project_id}/visual-bible", response_model=VisualBibleResponse)
def revise_visual_bible_route(
    project_id: str,
    payload: VisualBibleEditRequest,
    session: Session = Depends(get_session),
) -> VisualBibleResponse:
    try:
        return _visual_bible_response(
            revise_visual_bible(session, project_id=project_id, visual_bible=payload.visual_bible),
            session,
        )
    except VisualRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None


@app.post(
    "/api/v1/projects/{project_id}/visual-bible/{visual_bible_version_id}/approve",
    response_model=VisualBibleResponse,
)
def approve_visual_bible_route(
    project_id: str,
    visual_bible_version_id: str,
    session: Session = Depends(get_session),
) -> VisualBibleResponse:
    try:
        return _visual_bible_response(
            approve_visual_bible(
                session,
                project_id=project_id,
                visual_bible_version_id=visual_bible_version_id,
            ), session
        )
    except VisualRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.post(
    "/api/v1/projects/{project_id}/visual-bible/references:generate",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def generate_visual_references_route(
    project_id: str,
    payload: VisualBibleGenerationRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type="visual_reference_generation",
            request={"run_key": payload.run_key},
            provider="cloudflare",
            model=os.getenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-4b"),
            max_attempts=3,
        )
    except ProjectNotFoundError:
        raise _not_found(f"project {project_id} not found") from None
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return GenerationJobSubmissionResponse(job=_job_response(job), created=created, dispatched=dispatched)


@app.post(
    "/api/v1/projects/{project_id}/storyboard/generate",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def generate_storyboard_route(
    project_id: str,
    payload: VisualBibleGenerationRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    approved_bible = session.scalar(
        select(VisualBibleVersion)
        .where(
            VisualBibleVersion.project_id == project_id,
            VisualBibleVersion.approval_status == "approved",
        )
        .order_by(VisualBibleVersion.version.desc())
    )
    if approved_bible is None:
        raise HTTPException(status_code=409, detail="an approved Visual Bible is required before storyboard generation")
    if missing_reference_assets(
        session, project_id=project_id, bible=normalize_visual_bible(approved_bible.payload)
    ):
        raise HTTPException(status_code=409, detail="generate canonical character and location references before storyboard generation")
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type="storyboard_generation",
            request={"run_key": payload.run_key},
            provider=os.getenv("LLM_PRIMARY", "nvidia_nim"),
            model=os.getenv("NIM_MODEL") or os.getenv("GROQ_MODEL"),
            max_attempts=3,
        )
    except ProjectNotFoundError:
        raise _not_found(f"project {project_id} not found") from None
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return GenerationJobSubmissionResponse(job=_job_response(job), created=created, dispatched=dispatched)


@app.patch("/api/v1/scenes/{scene_id}", response_model=SceneResponse)
def revise_scene_route(
    scene_id: str,
    payload: SceneEditRequest,
    session: Session = Depends(get_session),
) -> SceneResponse:
    try:
        return _scene_response(
            revise_scene(
                session,
                scene_id=scene_id,
                duration_sec=payload.duration_sec,
                visual_prompt=payload.visual_prompt,
                asset_strategy=payload.asset_strategy,
                shot_spec=payload.shot_spec,
            )
        )
    except VisualRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/v1/projects/{project_id}/narrations", response_model=list[NarrationVersionResponse])
def list_narrations_route(project_id: str, session: Session = Depends(get_session)) -> list[NarrationVersionResponse]:
    if get_project(session, project_id=project_id) is None:
        raise _not_found(f"project {project_id} not found")
    return [_narration_response(session, narration) for narration in list_narrations(session, project_id=project_id)]


@app.post(
    "/api/v1/projects/{project_id}/narration:generate",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def generate_narration_route(
    project_id: str,
    payload: NarrationGenerateRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    if get_project(session, project_id=project_id) is None:
        raise _not_found(f"project {project_id} not found")
    text = payload.text
    target_duration_sec = None
    if text is None:
        story = session.scalar(
            select(StoryVersion)
            .where(
                StoryVersion.project_id == project_id,
                StoryVersion.approval_status == "approved",
            )
            .order_by(StoryVersion.version.desc())
        )
        if story is None or not story.payload.get("narration"):
            raise HTTPException(status_code=422, detail="an approved StorySpec with narration is required")
        text = story.payload["narration"]
        if isinstance(story.payload.get("target_duration_sec"), (int, float)):
            target_duration_sec = story.payload["target_duration_sec"]
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type="narration_generation",
            request={
                "run_key": payload.run_key,
                "text": text,
                "voice": payload.voice,
                "direction": payload.direction,
                "target_duration_sec": target_duration_sec,
            },
            provider="gemini_tts",
            model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
            max_attempts=3,
        )
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return GenerationJobSubmissionResponse(job=_job_response(job), created=created, dispatched=dispatched)


@app.post(
    "/api/v1/projects/{project_id}/captions:align",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def align_captions_route(
    project_id: str,
    payload: CaptionAlignRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    narration = session.get(NarrationVersion, payload.narration_version_id)
    if narration is None or narration.project_id != project_id:
        raise _not_found(f"narration {payload.narration_version_id} not found")
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type="caption_alignment",
            version=narration.id,
            request={
                "run_key": payload.run_key,
                "narration_version_id": narration.id,
                "language": payload.language,
            },
            provider="cloudflare_whisper",
            model=os.getenv("CLOUDFLARE_WHISPER_MODEL", "@cf/openai/whisper-large-v3-turbo"),
            max_attempts=3,
        )
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return GenerationJobSubmissionResponse(job=_job_response(job), created=created, dispatched=dispatched)


@app.post(
    "/api/v1/projects/{project_id}/narration/{narration_version_id}/approve",
    response_model=NarrationVersionResponse,
)
def approve_narration_route(
    project_id: str,
    narration_version_id: str,
    session: Session = Depends(get_session),
) -> NarrationVersionResponse:
    try:
        return _narration_response(
            session,
            approve_narration(
                session,
                project_id=project_id,
                narration_version_id=narration_version_id,
            ),
        )
    except NarrationRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.get("/api/v1/narrations/{narration_version_id}/audio")
def narration_audio_route(narration_version_id: str, session: Session = Depends(get_session)) -> Response:
    try:
        narration = get_narration(session, narration_version_id=narration_version_id)
    except NarrationRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    try:
        content = create_artifact_storage().read(narration.audio_uri)
    except FileNotFoundError:
        raise _not_found(f"narration {narration_version_id} audio not found") from None
    return Response(content=content, media_type="audio/wav")


def _caption_content_route(
    caption_id: str,
    session: Session,
    *,
    uri_field: str,
    media_type: str,
) -> Response:
    track = session.get(CaptionTrack, caption_id)
    if track is None:
        raise _not_found(f"caption track {caption_id} not found")
    uri = getattr(track, uri_field)
    if not uri:
        raise _not_found(f"caption track {caption_id} {uri_field} not found")
    try:
        content = create_artifact_storage().read(uri)
    except FileNotFoundError:
        raise _not_found(f"caption track {caption_id} content not found") from None
    return Response(content=content, media_type=media_type)


@app.get("/api/v1/captions/{caption_id}/srt")
def caption_srt_route(caption_id: str, session: Session = Depends(get_session)) -> Response:
    return _caption_content_route(caption_id, session, uri_field="srt_uri", media_type="application/x-subrip")


@app.get("/api/v1/captions/{caption_id}/json")
def caption_json_route(caption_id: str, session: Session = Depends(get_session)) -> Response:
    return _caption_content_route(caption_id, session, uri_field="json_uri", media_type="application/json")


def _submit_render_route(
    project_id: str,
    payload: RenderCreateRequest,
    *,
    render_type: Literal["preview", "final"],
    session: Session,
    dispatcher,
) -> RenderJobSubmissionResponse:
    if get_project(session, project_id=project_id) is None:
        raise _not_found(f"project {project_id} not found")
    try:
        render, job, created, dispatched = enqueue_render_job(
            session,
            dispatcher,
            project_id=project_id,
            render_type=render_type,
            run_key=payload.run_key,
            music_asset_id=payload.music_asset_id,
            sfx_asset_ids=payload.sfx_asset_ids,
        )
    except RenderValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return RenderJobSubmissionResponse(
        render=_render_response(render),
        job=_job_response(job),
        created=created,
        dispatched=dispatched,
    )


@app.post(
    "/api/v1/projects/{project_id}/renders:preview",
    response_model=RenderJobSubmissionResponse,
    status_code=202,
)
def render_preview_route(
    project_id: str,
    payload: RenderCreateRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> RenderJobSubmissionResponse:
    return _submit_render_route(
        project_id,
        payload,
        render_type="preview",
        session=session,
        dispatcher=dispatcher,
    )


@app.post(
    "/api/v1/projects/{project_id}/renders:final",
    response_model=RenderJobSubmissionResponse,
    status_code=202,
)
def render_final_route(
    project_id: str,
    payload: RenderCreateRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> RenderJobSubmissionResponse:
    return _submit_render_route(
        project_id,
        payload,
        render_type="final",
        session=session,
        dispatcher=dispatcher,
    )


@app.get("/api/v1/projects/{project_id}/renders", response_model=list[RenderResponse])
def list_renders_route(project_id: str, session: Session = Depends(get_session)) -> list[RenderResponse]:
    if get_project(session, project_id=project_id) is None:
        raise _not_found(f"project {project_id} not found")
    return [_render_response(render) for render in list_renders(session, project_id=project_id)]


@app.post(
    "/api/v1/projects/{project_id}/renders/{render_id}/approve-preview",
    response_model=RenderResponse,
)
def approve_preview_route(
    project_id: str,
    render_id: str,
    session: Session = Depends(get_session),
) -> RenderResponse:
    try:
        return _render_response(approve_preview(session, project_id=project_id, render_id=render_id))
    except RenderRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except RenderValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.get("/api/v1/renders/{render_id}/content")
def render_content_route(render_id: str, session: Session = Depends(get_session)) -> Response:
    try:
        render = get_render(session, render_id=render_id)
    except RenderRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    if not render.uri:
        raise _not_found(f"render {render_id} content not found")
    try:
        content = create_artifact_storage().read(render.uri)
    except FileNotFoundError:
        raise _not_found(f"render {render_id} content not found") from None
    return Response(content=content, media_type="video/mp4")


@app.post(
    "/api/v1/projects/{project_id}/publications",
    response_model=PublicationResponse,
    status_code=201,
)
def create_publication_route(
    project_id: str,
    payload: PublicationCreateRequest,
    session: Session = Depends(get_session),
) -> PublicationResponse:
    try:
        publication = create_publication(
            session,
            project_id=project_id,
            platform=payload.platform,
            url=payload.url,
            external_id=payload.external_id,
            published_at=payload.published_at,
        )
        session.commit()
        return _publication_response(session, publication)
    except PublicationRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.get("/api/v1/projects/{project_id}/publications", response_model=list[PublicationResponse])
def list_publications_route(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[PublicationResponse]:
    if get_project(session, project_id=project_id) is None:
        raise _not_found(f"project {project_id} not found")
    return [_publication_response(session, publication) for publication in list_publications(session, project_id=project_id)]


@app.post(
    "/api/v1/publications/{publication_id}/metrics",
    response_model=MetricSnapshotResponse,
    status_code=201,
)
def create_metric_snapshot_route(
    publication_id: str,
    payload: MetricSnapshotCreateRequest,
    session: Session = Depends(get_session),
) -> MetricSnapshotResponse:
    try:
        snapshot = create_metric_snapshot(
            session,
            publication_id=publication_id,
            captured_at=payload.captured_at,
            views=payload.views,
            retention=payload.retention,
            likes=payload.likes,
            comments=payload.comments,
            shares_saves=payload.shares_saves,
            followers_gained=payload.followers_gained,
        )
        session.commit()
        return _metric_response(snapshot)
    except PublicationRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None


@app.get("/api/v1/publications/{publication_id}/metrics", response_model=list[MetricSnapshotResponse])
def list_metric_snapshots_route(
    publication_id: str,
    session: Session = Depends(get_session),
) -> list[MetricSnapshotResponse]:
    try:
        get_publication(session, publication_id=publication_id)
    except PublicationRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    return [_metric_response(metric) for metric in list_metric_snapshots(session, publication_id=publication_id)]


@app.get("/api/v1/scenes/{scene_id}/assets", response_model=list[AssetResponse])
def list_scene_assets_route(scene_id: str, session: Session = Depends(get_session)) -> list[AssetResponse]:
    try:
        assets, _ = list_scene_assets(session, scene_id=scene_id)
        return [_asset_response(asset) for asset in assets]
    except AssetRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None


@app.post(
    "/api/v1/scenes/{scene_id}/assets:generate",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def generate_scene_asset_route(
    scene_id: str,
    payload: SceneAssetGenerateRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    scene = session.get(Scene, scene_id)
    if scene is None:
        raise _not_found(f"scene {scene_id} not found")
    approved_bible = session.scalar(
        select(VisualBibleVersion)
        .where(
            VisualBibleVersion.project_id == scene.project_id,
            VisualBibleVersion.approval_status == "approved",
        )
        .order_by(VisualBibleVersion.version.desc())
    )
    if approved_bible is None:
        raise HTTPException(status_code=409, detail="an approved Visual Bible is required before scene generation")
    if missing_reference_assets(session, project_id=scene.project_id, bible=normalize_visual_bible(approved_bible.payload)):
        raise HTTPException(status_code=409, detail="generate canonical character and location references before scene generation")
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=scene.project_id,
            job_type="scene_asset_generation",
            version=scene.id,
            request={"scene_id": scene.id, "prompt_override": payload.prompt},
            provider="cloudflare",
            model=os.getenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-4b"),
            max_attempts=3,
        )
    except ProjectNotFoundError:
        raise _not_found(f"project {scene.project_id} not found") from None
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return GenerationJobSubmissionResponse(job=_job_response(job), created=created, dispatched=dispatched)


@app.post(
    "/api/v1/scenes/{scene_id}/assets:search-stock",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def search_scene_stock_route(
    scene_id: str,
    payload: StockSearchRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    scene = session.get(Scene, scene_id)
    if scene is None:
        raise _not_found(f"scene {scene_id} not found")
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=scene.project_id,
            job_type="scene_stock_search",
            version=scene.id,
            request={"scene_id": scene.id, **payload.model_dump(mode="json")},
            provider="pexels",
            max_attempts=3,
        )
    except ProjectNotFoundError:
        raise _not_found(f"project {scene.project_id} not found") from None
    except JobDispatchError as exc:
        raise HTTPException(status_code=503, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    return GenerationJobSubmissionResponse(job=_job_response(job), created=created, dispatched=dispatched)


@app.post("/api/v1/scenes/{scene_id}/assets/{asset_id}:select", response_model=AssetSelectionResponse)
def select_scene_asset_route(
    scene_id: str,
    asset_id: str,
    session: Session = Depends(get_session),
) -> AssetSelectionResponse:
    try:
        selection = select_scene_asset(session, scene_id=scene_id, asset_id=asset_id)
        return AssetSelectionResponse(
            scene_id=selection.scene_id,
            selected_asset_id=selection.selected_asset_id,
            selected_at=selection.updated_at,
        )
    except AssetRecordNotFoundError as exc:
        raise _not_found(str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/v1/assets/{asset_id}/content")
def asset_content_route(asset_id: str, session: Session = Depends(get_session)) -> Response:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise _not_found(f"asset {asset_id} not found")
    try:
        content = create_artifact_storage().read(asset.local_uri)
    except FileNotFoundError:
        raise _not_found(f"asset {asset_id} content not found") from None
    media_type = asset.metadata_json.get("content_type", "application/octet-stream")
    return Response(content=content, media_type=media_type)


@app.post(
    "/api/v1/projects/{project_id}/jobs",
    response_model=GenerationJobSubmissionResponse,
    status_code=202,
)
def submit_generation_job_route(
    project_id: str,
    payload: GenerationJobCreateRequest,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobSubmissionResponse:
    try:
        job, created, dispatched = enqueue_generation_job(
            session,
            dispatcher,
            project_id=project_id,
            job_type=payload.type,
            version=payload.version,
            request=payload.request,
            provider=payload.provider,
            model=payload.model,
            max_attempts=payload.max_attempts,
        )
    except ProjectNotFoundError:
        raise _not_found(f"project {project_id} not found") from None
    except JobDispatchError as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": str(exc), "job_id": exc.job_id},
        ) from exc
    return GenerationJobSubmissionResponse(
        job=_job_response(job),
        created=created,
        dispatched=dispatched,
    )


@app.get("/api/v1/jobs/{job_id}", response_model=GenerationJobResponse)
def get_job_route(job_id: str, session: Session = Depends(get_session)) -> GenerationJobResponse:
    job = get_generation_job(session, job_id=job_id)
    if job is None:
        raise _not_found(f"job {job_id} not found")
    return _job_response(job)


@app.post("/api/v1/jobs/{job_id}:retry", response_model=GenerationJobResponse, status_code=202)
def retry_job_route(
    job_id: str,
    session: Session = Depends(get_session),
    dispatcher=Depends(get_dispatcher),
) -> GenerationJobResponse:
    try:
        job = retry_and_enqueue_generation_job(session, dispatcher, job_id=job_id)
    except GenerationJobNotFoundError:
        raise _not_found(f"job {job_id} not found") from None
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except JobDispatchError as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": str(exc), "job_id": exc.job_id},
        ) from exc
    return _job_response(job)


@app.get("/api/v1/projects/{project_id}/events")
def project_events_route(
    project_id: str,
    session_factory=Depends(get_session_factory),
) -> StreamingResponse:
    with session_factory() as session:
        if get_project(session, project_id=project_id) is None:
            raise _not_found(f"project {project_id} not found")
    return StreamingResponse(
        project_event_stream(session_factory, project_id=project_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
