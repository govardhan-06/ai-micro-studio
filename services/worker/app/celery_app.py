import os

from celery import Celery
from sqlalchemy import select

from studio.agents.creative_director import CreativeDirector
from studio.application.commands.assets import (
    list_reference_assets,
    persist_generated_image,
    persist_reference_image,
    persist_stock_media,
)
from studio.application.commands.creative import persist_creative_package, persist_story_draft
from studio.application.commands.narration import get_narration, persist_caption_track, persist_narration
from studio.application.commands.rendering import RenderRecordNotFoundError
from studio.application.commands.visuals import (
    build_image_prompt,
    canonical_visual_bible_payload,
    generate_storyboard,
    generate_visual_bible,
    missing_reference_assets,
    shot_spec_for_scene,
)
from studio.application.commands.jobs import (
    GenerationJobNotFoundError,
    complete_generation_job,
    fail_generation_job,
    start_generation_job,
    update_generation_job_observability,
)
from studio.application.workflows.dispatch import CELERY_TASK_NAME
from studio.persistence.database import session_scope
from studio.domain.schemas.contracts import IdeaCandidate, ShotSpec, StorySpec, normalize_visual_bible
from studio.domain.constants import ProjectStage
from studio.domain.services.transitions import advance_project_stage
from studio.persistence.models import (
    GenerationJob,
    IdeaCandidate as IdeaCandidateRecord,
    Project,
    StoryVersion,
    VisualBibleVersion,
)
from studio.persistence.models import Render, Scene, Asset, AssetSelection
from studio.providers.factory import create_image_provider, create_stock_provider, create_vision_provider
from studio.providers.factory import create_transcription_provider, create_tts_provider
from studio.providers.media import MediaProviderError
from studio.rendering.manifest import build_render_manifest
from studio.rendering.runner import render_manifest as run_renderer
from studio.storage.local import create_artifact_storage

celery_app = Celery("ai_micro_story_studio", broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def create_creative_director() -> CreativeDirector:
    return CreativeDirector.from_env()


def _approved_visual_bible(session, project_id: str):
    record = session.scalar(
        select(VisualBibleVersion)
        .where(
            VisualBibleVersion.project_id == project_id,
            VisualBibleVersion.approval_status == "approved",
        )
        .order_by(VisualBibleVersion.version.desc())
    )
    if record is None:
        raise RuntimeError("an approved Visual Bible is required")
    return record, normalize_visual_bible(record.payload)


def run_visual_reference_job(job_id: str, attempt: int) -> None:
    with session_scope() as session:
        job = session.get(GenerationJob, job_id)
        if job is None or job.attempt != attempt:
            raise GenerationJobNotFoundError(job_id)
        record, bible = _approved_visual_bible(session, job.project_id)
        assets = list_reference_assets(session, project_id=job.project_id)
        by_key = {
            asset.metadata_json.get("reference_key"): asset
            for asset in assets
            if asset.status == "available"
        }
        provider = create_image_provider()
        storage = create_artifact_storage()
        for character in bible.characters:
            if character.id in by_key:
                character.reference_asset_ids = [by_key[character.id].id]
                continue
            prompt = (
                f"Canonical character reference sheet for {character.id}, role {character.role}: age {character.age}; "
                f"presentation {character.presentation}; ethnicity {character.ethnicity}; face {character.face}; hair {character.hair}; "
                f"build {character.build}; clothing {character.clothing}; accessories {', '.join(character.accessories) or 'none'}. "
                f"Immutable traits: {', '.join(character.immutable_traits) or 'none'}. Plain neutral background, no text."
            )
            asset = persist_reference_image(
                session,
                project_id=job.project_id,
                reference_key=character.id,
                asset_type="character_reference",
                prompt=prompt,
                result=provider.generate(prompt, aspect_ratio=bible.style.aspect_ratio),
                storage=storage,
            )
            character.reference_asset_ids = [asset.id]
            by_key[character.id] = asset
        for location in bible.locations:
            if location.id in by_key:
                location.reference_asset_ids = [by_key[location.id].id]
                continue
            prompt = (
                f"Canonical physical location reference for {location.id}, {location.name}: architecture and geometry {location.architecture_geometry}; "
                f"time {location.time}; weather {location.weather}; lighting {location.lighting}; "
                f"persistent props {', '.join(location.persistent_props) or 'none'}; immutable traits {', '.join(location.immutable_traits) or 'none'}. No text."
            )
            asset = persist_reference_image(
                session,
                project_id=job.project_id,
                reference_key=location.id,
                asset_type="location_reference",
                prompt=prompt,
                result=provider.generate(prompt, aspect_ratio=bible.style.aspect_ratio),
                storage=storage,
            )
            location.reference_asset_ids = [asset.id]
            by_key[location.id] = asset
        record.payload = canonical_visual_bible_payload(bible)
        session.flush()


ASSET_JOB_TYPES = {"scene_asset_generation", "scene_stock_search", "visual_reference_generation"}
AUDIO_JOB_TYPES = {"narration_generation", "caption_alignment"}
RENDER_JOB_TYPES = {"render_preview", "render_final"}


def run_scene_asset_job(job_id: str, attempt: int) -> None:
    with session_scope() as session:
        job = session.get(GenerationJob, job_id)
        if job is None or job.attempt != attempt:
            raise GenerationJobNotFoundError(job_id)
        request = job.request_json
        scene = session.get(Scene, request.get("scene_id"))
        if scene is None or scene.project_id != job.project_id:
            raise RuntimeError("asset job scene does not belong to its project")
        storage = create_artifact_storage()
        if job.type == "scene_asset_generation":
            _, bible = _approved_visual_bible(session, job.project_id)
            missing = missing_reference_assets(session, project_id=job.project_id, bible=bible)
            if missing:
                raise RuntimeError("canonical references must be generated before scene image generation")
            story_record = session.get(StoryVersion, scene.story_version_id)
            if story_record is None:
                raise RuntimeError("scene StorySpec is missing")
            shot_spec = (
                ShotSpec.model_validate(scene.shot_spec_json)
                if scene.shot_spec_json
                else shot_spec_for_scene(StorySpec.model_validate(story_record.payload), bible, scene.scene_order)
            )
            previous = session.scalar(
                select(Asset)
                .join(AssetSelection, AssetSelection.selected_asset_id == Asset.id)
                .join(Scene, Scene.id == AssetSelection.scene_id)
                .where(
                    Scene.story_version_id == scene.story_version_id,
                    Scene.scene_order < scene.scene_order,
                    Asset.status == "available",
                )
                .order_by(Scene.scene_order.desc())
            )
            reference_assets = list_reference_assets(session, project_id=job.project_id)
            by_id = {asset.id: asset for asset in reference_assets if asset.status == "available"}
            selected_ids = [
                asset_id
                for character in bible.characters
                for asset_id in character.reference_asset_ids
                if asset_id in by_id
            ]
            location = next(item for item in bible.locations if item.id == shot_spec.location_id)
            selected_ids.extend(asset_id for asset_id in location.reference_asset_ids if asset_id in by_id)
            if previous is not None:
                selected_ids.append(previous.id)
            provider = create_image_provider()
            selected_ids = selected_ids[: provider.capabilities.max_reference_images]
            reference_uri_by_id = {asset.id: asset.local_uri for asset in reference_assets}
            if previous is not None:
                reference_uri_by_id[previous.id] = previous.local_uri
            references = [reference_uri_by_id[asset_id] for asset_id in selected_ids if asset_id in reference_uri_by_id]
            previous_linkage = previous.id if previous is not None else None
            prompt = build_image_prompt(bible, shot_spec, previous_shot=previous_linkage)
            if request.get("qa_correction"):
                prompt += f" Additive QA correction for this regeneration: {request['qa_correction']}"
            job.request_json = {
                **request,
                "selected_reference_ids": selected_ids if provider.capabilities.supports_reference_images else [],
                "model_capabilities": {
                    "supports_reference_images": provider.capabilities.supports_reference_images,
                    "max_reference_images": provider.capabilities.max_reference_images,
                    "supports_image_editing": provider.capabilities.supports_image_editing,
                },
                "shot_spec": shot_spec.model_dump(mode="json"),
                "prompt": prompt,
                "previous_shot_asset_id": previous_linkage,
            }
            session.flush()
            result = provider.generate(
                prompt,
                references=references if provider.capabilities.supports_reference_images else None,
                aspect_ratio=bible.style.aspect_ratio,
            )
            reference_meta = {
                "selected_reference_ids": selected_ids if provider.capabilities.supports_reference_images else [],
                "previous_shot_asset_id": previous_linkage,
                "shot_spec": shot_spec.model_dump(mode="json"),
                "model_capabilities": {
                    "supports_reference_images": provider.capabilities.supports_reference_images,
                    "max_reference_images": provider.capabilities.max_reference_images,
                    "supports_image_editing": provider.capabilities.supports_image_editing,
                },
            }
            if not provider.capabilities.supports_reference_images:
                reference_meta["capability_limitation"] = "provider is prompt-only; canonical prompt used without image references"
            qa = create_vision_provider().evaluate(
                result.content,
                prompt=(
                    f"Evaluate this generated scene against ShotSpec {shot_spec.model_dump_json()} and Visual Bible style "
                    f"{bible.style.model_dump_json()}. Return only JSON with passed (boolean), score (0 to 1), and "
                    "issues (an array of objects containing code, message, severity, and correction). Use an empty "
                    "issues array when the image passes. Do not return a top-level correction field."
                ),
                references=[storage.read(reference_uri_by_id[asset_id]) for asset_id in selected_ids if asset_id in reference_uri_by_id],
                reference_asset_ids=selected_ids,
            )
            persist_generated_image(
                session,
                scene_id=scene.id,
                prompt=prompt,
                result=result,
                storage=storage,
                metadata_extra={**reference_meta, "qa": qa.model_dump(mode="json")},
                status="available" if qa.passed else "qa_rejected",
            )
            metadata = dict(result.metadata)
            update_generation_job_observability(
                session,
                job_id=job.id,
                attempt=attempt,
                provider=result.provider,
                model=result.model,
                usage=metadata.get("usage") if isinstance(metadata.get("usage"), dict) else None,
                cost_usd=metadata.get("cost_usd") if isinstance(metadata.get("cost_usd"), (int, float)) else None,
            )
            return

        provider = create_stock_provider()
        query = request.get("query") or scene.visual_intent or scene.visual_prompt
        if not query:
            raise RuntimeError("scene needs a visual intent before stock search")
        candidates = provider.search(
            query,
            media_type=request.get("media_type", "photo"),
            orientation=request.get("orientation", "portrait"),
            per_page=request.get("per_page", 6),
        )
        if not candidates:
            raise MediaProviderError(
                "stock provider returned no candidates",
                code="media_no_results",
                provider=provider.name,
            )
        downloads = []
        first_error = None
        for candidate in candidates:
            try:
                downloads.append(provider.download(candidate))
            except MediaProviderError as exc:
                first_error = first_error or exc
        if not downloads:
            raise first_error or RuntimeError("stock provider returned no downloadable candidates")
        persist_stock_media(session, scene_id=scene.id, query=query, downloads=downloads, storage=storage)


def run_audio_job(job_id: str, attempt: int) -> None:
    with session_scope() as session:
        job = session.get(GenerationJob, job_id)
        if job is None or job.attempt != attempt:
            raise GenerationJobNotFoundError(job_id)
        request = job.request_json
        storage = create_artifact_storage()
        if job.type == "narration_generation":
            text = request.get("text", "")
            result = create_tts_provider().synthesize(
                text,
                voice=request.get("voice") or "Kore",
                direction=request.get("direction"),
            )
            persist_narration(
                session,
                project_id=job.project_id,
                result=result,
                voice=request.get("voice") or "Kore",
                storage=storage,
            )
            metadata = dict(result.metadata)
            usage = dict(metadata.get("usage") or {}) if isinstance(metadata.get("usage"), dict) else {}
            usage["actual_duration_sec"] = result.duration_sec
            target_duration_sec = request.get("target_duration_sec")
            if isinstance(target_duration_sec, (int, float)):
                usage["target_duration_sec"] = target_duration_sec
                usage["duration_delta_sec"] = result.duration_sec - target_duration_sec
            update_generation_job_observability(
                session,
                job_id=job.id,
                attempt=attempt,
                provider=result.provider,
                model=result.model,
                usage=usage,
                cost_usd=metadata.get("cost_usd") if isinstance(metadata.get("cost_usd"), (int, float)) else None,
            )
            return

        narration = get_narration(session, narration_version_id=request.get("narration_version_id", ""))
        word_timings = create_transcription_provider().align(
            storage.read(narration.audio_uri),
            content_type="audio/wav",
            language=request.get("language") or "en",
        )
        persist_caption_track(
            session,
            narration_version_id=narration.id,
            word_timings=word_timings,
            storage=storage,
        )


def run_render_job(job_id: str, attempt: int) -> None:
    with session_scope() as session:
        job = session.get(GenerationJob, job_id)
        if job is None or job.attempt != attempt:
            raise GenerationJobNotFoundError(job_id)
        request = job.request_json
        render = session.get(Render, request.get("render_id"))
        if render is None or render.project_id != job.project_id:
            raise RenderRecordNotFoundError(request.get("render_id", ""))
        render.status = "running"
        session.flush()
        manifest = build_render_manifest(
            session,
            render=render,
            narration_version_id=request.get("narration_version_id", ""),
            storage=create_artifact_storage(),
            music_asset_id=request.get("music_asset_id"),
            sfx_asset_ids=request.get("sfx_asset_ids", {}),
        )
        rendered = run_renderer(manifest)
        uri = create_artifact_storage().put(
            f"projects/{render.project_id}/renders/{render.id}.mp4",
            rendered.content,
        )
        render.uri = uri
        render.duration_sec = rendered.duration_sec
        render.status = "succeeded"
        project = session.get(Project, render.project_id)
        if project is not None and list(ProjectStage).index(ProjectStage(project.current_stage)) < list(ProjectStage).index(ProjectStage.RENDER):
            project.current_stage = advance_project_stage(project.current_stage, ProjectStage.RENDER)
        session.flush()


@celery_app.task(name=CELERY_TASK_NAME)
def run_generation_job(job_id: str, attempt: int | None = None) -> dict[str, str | int]:
    with session_scope() as session:
        if attempt is None:
            job = session.get(GenerationJob, job_id)
            if job is None:
                raise GenerationJobNotFoundError(job_id)
            attempt = job.attempt
        job = start_generation_job(session, job_id=job_id, attempt=attempt)
        job_type = job.type
        current_status = job.status
        current_attempt = job.attempt
    if current_status != "running" or job_type not in {
        "creative_package_generation",
        "story_generation",
        "visual_bible_generation",
        "storyboard_generation",
        *ASSET_JOB_TYPES,
        *AUDIO_JOB_TYPES,
        *RENDER_JOB_TYPES,
    }:
        return {"job_id": job_id, "status": current_status, "attempt": current_attempt}

    try:
        if job_type == "visual_reference_generation":
            run_visual_reference_job(job_id, current_attempt)
            with session_scope() as session:
                completed = complete_generation_job(session, job_id=job_id, attempt=current_attempt)
                return {"job_id": completed.id, "status": completed.status, "attempt": completed.attempt}

        if job_type in ASSET_JOB_TYPES:
            run_scene_asset_job(job_id, current_attempt)
            with session_scope() as session:
                completed = complete_generation_job(session, job_id=job_id, attempt=current_attempt)
                return {"job_id": completed.id, "status": completed.status, "attempt": completed.attempt}

        if job_type in AUDIO_JOB_TYPES:
            run_audio_job(job_id, current_attempt)
            with session_scope() as session:
                completed = complete_generation_job(session, job_id=job_id, attempt=current_attempt)
                return {"job_id": completed.id, "status": completed.status, "attempt": completed.attempt}

        if job_type in RENDER_JOB_TYPES:
            run_render_job(job_id, current_attempt)
            with session_scope() as session:
                completed = complete_generation_job(session, job_id=job_id, attempt=current_attempt)
                return {"job_id": completed.id, "status": completed.status, "attempt": completed.attempt}

        director = create_creative_director()
        with session_scope() as session:
            project = session.get(Project, job.project_id)
            if project is None:
                raise GenerationJobNotFoundError(job.project_id)
            brief = project.title if not project.genre else f"{project.title}; genre: {project.genre}"
            selected_record = session.scalar(
                select(IdeaCandidateRecord).where(
                    IdeaCandidateRecord.project_id == project.id,
                    IdeaCandidateRecord.is_selected.is_(True),
                )
            )
            if job_type == "story_generation" and selected_record is None:
                raise RuntimeError("a selected idea is required before story generation")
            selected_idea = (
                IdeaCandidate.model_validate(
                    {
                        "id": selected_record.id,
                        "premise": selected_record.premise,
                        "hook": selected_record.hook,
                        "scores": selected_record.scores,
                        "rationale": selected_record.rationale,
                        "source_run": selected_record.source_run,
                    }
                )
                if selected_record is not None
                else None
            )
        if job_type == "story_generation":
            trace_metadata = {
                "project_id": project.id,
                "job_id": job.id,
                "job_type": job_type,
                "attempt": current_attempt,
            }
            draft, critique = director.develop_story(brief, selected_idea, trace_metadata=trace_metadata)
        elif job_type == "creative_package_generation":
            trace_metadata = {
                "project_id": project.id,
                "job_id": job.id,
                "job_type": job_type,
                "attempt": current_attempt,
            }
            package = director.run(brief, idea_count=20, trace_metadata=trace_metadata)
        elif job_type == "visual_bible_generation":
            with session_scope() as session:
                story = session.scalar(
                    select(StoryVersion)
                    .where(
                        StoryVersion.project_id == project.id,
                        StoryVersion.approval_status == "approved",
                    )
                    .order_by(StoryVersion.version.desc())
                )
                if story is None:
                    raise RuntimeError("an approved StorySpec is required before Visual Bible generation")
                bible = director.generate_visual_bible(
                    StorySpec.model_validate(story.payload),
                    trace_metadata={"project_id": project.id, "job_id": job.id, "job_type": job_type, "attempt": current_attempt},
                )
                generate_visual_bible(session, project_id=project.id, visual_bible=bible)
        else:
            with session_scope() as session:
                story = session.scalar(
                    select(StoryVersion)
                    .where(
                        StoryVersion.project_id == project.id,
                        StoryVersion.approval_status == "approved",
                    )
                    .order_by(StoryVersion.version.desc())
                )
                bible_record = session.scalar(
                    select(VisualBibleVersion)
                    .where(
                        VisualBibleVersion.project_id == project.id,
                        VisualBibleVersion.approval_status == "approved",
                    )
                    .order_by(VisualBibleVersion.version.desc())
                )
                if story is None or bible_record is None:
                    raise RuntimeError("approved StorySpec and Visual Bible are required before storyboard generation")
                shot_specs = director.generate_shot_specs(
                    StorySpec.model_validate(story.payload),
                    normalize_visual_bible(bible_record.payload),
                    trace_metadata={"project_id": project.id, "job_id": job.id, "job_type": "shot_spec_generation", "attempt": current_attempt},
                )
                generate_storyboard(session, project_id=project.id, shot_specs=shot_specs)
        with session_scope() as session:
            if job_type == "story_generation":
                persist_story_draft(
                    session,
                    project_id=project.id,
                    story=draft.story,
                    critique=critique.model_dump(mode="json"),
                    provider=job.provider or (director.story_writer.stage.provider_names[0] if director.story_writer.stage.provider_names else None),
                    model=job.model,
                )
            elif job_type == "creative_package_generation":
                persist_creative_package(
                    session,
                    project_id=project.id,
                    package=package,
                    persist_story=False,
                    provider=job.provider,
                    model=job.model,
                )
            completed = complete_generation_job(session, job_id=job_id, attempt=current_attempt)
            return {"job_id": completed.id, "status": completed.status, "attempt": completed.attempt}
    except Exception as exc:
        with session_scope() as session:
            failed = fail_generation_job(
                session,
                job_id=job_id,
                attempt=current_attempt,
                error_code=getattr(
                    exc,
                    "code",
                    "asset_generation_failed"
                    if job_type in ASSET_JOB_TYPES
                    else "render_failed"
                    if job_type in RENDER_JOB_TYPES
                    else "creative_generation_failed",
                ),
                error_message=str(exc),
            )
            if job_type in RENDER_JOB_TYPES:
                render = session.get(Render, job.request_json.get("render_id"))
                if render is not None:
                    render.status = "failed"
            return {"job_id": failed.id, "status": failed.status, "attempt": failed.attempt}
