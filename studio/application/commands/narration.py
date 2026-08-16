from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.domain.constants import ApprovalStatus, ProjectStage, ProjectStatus
from studio.domain.services.transitions import advance_project_stage, transition_project_status
from studio.persistence.models import CaptionTrack, NarrationVersion, Project
from studio.persistence.operations import approve_version, next_version, new_id, utc_now
from studio.providers.audio import AudioArtifact, WordTiming
from studio.storage.local import LocalArtifactStorage


class NarrationRecordNotFoundError(LookupError):
    pass


def _project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise NarrationRecordNotFoundError(f"project {project_id} not found")
    return project


def persist_narration(
    session: Session,
    *,
    project_id: str,
    result: AudioArtifact,
    voice: str,
    storage: LocalArtifactStorage,
) -> NarrationVersion:
    _project(session, project_id)
    narration_id = new_id()
    audio_uri = storage.put(f"projects/{project_id}/narration/{narration_id}.wav", result.content)
    narration = NarrationVersion(
        id=narration_id,
        project_id=project_id,
        version=next_version(session, NarrationVersion, project_id),
        provider=result.provider,
        model=result.model,
        voice=voice,
        audio_uri=audio_uri,
        duration_sec=result.duration_sec,
        approval_status=ApprovalStatus.DRAFT.value,
    )
    session.add(narration)
    session.flush()
    return narration


def list_narrations(session: Session, *, project_id: str) -> list[NarrationVersion]:
    return list(
        session.scalars(
            select(NarrationVersion)
            .where(NarrationVersion.project_id == project_id)
            .order_by(NarrationVersion.version.desc())
        )
    )


def get_narration(session: Session, *, narration_version_id: str) -> NarrationVersion:
    narration = session.get(NarrationVersion, narration_version_id)
    if narration is None:
        raise NarrationRecordNotFoundError(f"narration {narration_version_id} not found")
    return narration


def approve_narration(
    session: Session,
    *,
    project_id: str,
    narration_version_id: str,
) -> NarrationVersion:
    narration = session.scalar(
        select(NarrationVersion).where(
            NarrationVersion.id == narration_version_id,
            NarrationVersion.project_id == project_id,
        )
    )
    project = _project(session, project_id)
    if narration is None:
        raise NarrationRecordNotFoundError(f"narration {narration_version_id} not found")
    approved = approve_version(session, narration)
    if list(ProjectStage).index(ProjectStage(project.current_stage)) < list(ProjectStage).index(ProjectStage.NARRATION):
        project.current_stage = advance_project_stage(project.current_stage, ProjectStage.NARRATION)
    project.status = transition_project_status(project.status, ProjectStatus.ACTIVE)
    session.flush()
    return approved


def persist_caption_track(
    session: Session,
    *,
    narration_version_id: str,
    word_timings: list[WordTiming],
    storage: LocalArtifactStorage,
) -> CaptionTrack:
    narration = get_narration(session, narration_version_id=narration_version_id)
    if not word_timings:
        raise ValueError("caption alignment returned no word timings")
    _validate_timings(word_timings)
    words = [timing.as_dict() for timing in word_timings]
    track = session.scalar(
        select(CaptionTrack).where(CaptionTrack.narration_version_id == narration_version_id)
    )
    if track is None:
        track = CaptionTrack(id=new_id(), narration_version_id=narration_version_id, word_timings=words)
        session.add(track)
    else:
        track.word_timings = words
        track.updated_at = utc_now()
    base = f"projects/{narration.project_id}/narration/{narration.id}/captions"
    track.json_uri = storage.put(
        f"{base}.json",
        json.dumps({"narration_version_id": narration.id, "word_timings": words}, indent=2).encode("utf-8"),
    )
    track.srt_uri = storage.put(f"{base}.srt", format_srt(word_timings).encode("utf-8"))
    session.flush()
    return track


def format_srt(word_timings: list[WordTiming]) -> str:
    return "\n\n".join(
        f"{index}\n{_srt_timestamp(timing.start_sec)} --> {_srt_timestamp(timing.end_sec)}\n{timing.word}"
        for index, timing in enumerate(word_timings, start=1)
    ) + "\n"


def _validate_timings(word_timings: list[WordTiming]) -> None:
    previous_end = 0.0
    for timing in word_timings:
        if not timing.word.strip() or timing.start_sec < 0 or timing.end_sec <= timing.start_sec:
            raise ValueError("caption timings must contain non-empty words with positive ranges")
        if timing.start_sec < previous_end:
            raise ValueError("caption timings must be ordered and non-overlapping")
        previous_end = timing.end_sec


def _srt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_value, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d},{milliseconds:03d}"
