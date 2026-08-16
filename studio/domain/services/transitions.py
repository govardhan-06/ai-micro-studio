from __future__ import annotations

from enum import Enum
from typing import Union

from studio.domain.constants import ApprovalStatus, JobStatus, ProjectStage, ProjectStatus


class InvalidTransitionError(ValueError):
    pass


def _value(value: Union[str, Enum]) -> str:
    return value.value if isinstance(value, Enum) else value


_APPROVAL_TRANSITIONS = {
    ApprovalStatus.DRAFT.value: {
        ApprovalStatus.DRAFT.value,
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.REJECTED.value,
    },
    ApprovalStatus.REJECTED.value: {ApprovalStatus.REJECTED.value, ApprovalStatus.DRAFT.value},
    ApprovalStatus.APPROVED.value: {ApprovalStatus.APPROVED.value, ApprovalStatus.SUPERSEDED.value},
    ApprovalStatus.SUPERSEDED.value: {ApprovalStatus.SUPERSEDED.value},
}

_JOB_TRANSITIONS = {
    JobStatus.QUEUED.value: {
        JobStatus.QUEUED.value,
        JobStatus.RUNNING.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    },
    JobStatus.RUNNING.value: {
        JobStatus.RUNNING.value,
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    },
    JobStatus.SUCCEEDED.value: {JobStatus.SUCCEEDED.value},
    JobStatus.FAILED.value: {JobStatus.FAILED.value},
    JobStatus.CANCELLED.value: {JobStatus.CANCELLED.value},
}

_STAGE_ORDER = {stage.value: index for index, stage in enumerate(ProjectStage)}

_PROJECT_STATUS_TRANSITIONS = {
    ProjectStatus.DRAFT.value: {ProjectStatus.DRAFT.value, ProjectStatus.ACTIVE.value, ProjectStatus.ARCHIVED.value},
    ProjectStatus.ACTIVE.value: {
        ProjectStatus.ACTIVE.value,
        ProjectStatus.COMPLETED.value,
        ProjectStatus.ARCHIVED.value,
    },
    ProjectStatus.COMPLETED.value: {ProjectStatus.COMPLETED.value, ProjectStatus.ARCHIVED.value},
    ProjectStatus.ARCHIVED.value: {ProjectStatus.ARCHIVED.value},
}


def transition_approval_status(current: Union[str, ApprovalStatus], target: Union[str, ApprovalStatus]) -> str:
    current_value = _value(current)
    target_value = _value(target)
    if target_value not in _APPROVAL_TRANSITIONS.get(current_value, set()):
        raise InvalidTransitionError(f"approval status cannot move from {current_value} to {target_value}")
    return target_value


def transition_job_status(current: Union[str, JobStatus], target: Union[str, JobStatus]) -> str:
    current_value = _value(current)
    target_value = _value(target)
    if target_value not in _JOB_TRANSITIONS.get(current_value, set()):
        raise InvalidTransitionError(f"job status cannot move from {current_value} to {target_value}")
    return target_value


def advance_project_stage(current: Union[str, ProjectStage], target: Union[str, ProjectStage]) -> str:
    current_value = _value(current)
    target_value = _value(target)
    if current_value not in _STAGE_ORDER or target_value not in _STAGE_ORDER:
        raise InvalidTransitionError(f"unknown project stage: {current_value} or {target_value}")
    if _STAGE_ORDER[target_value] < _STAGE_ORDER[current_value]:
        raise InvalidTransitionError(f"project stage cannot move from {current_value} to {target_value}")
    return target_value


def transition_project_status(current: Union[str, ProjectStatus], target: Union[str, ProjectStatus]) -> str:
    current_value = _value(current)
    target_value = _value(target)
    if target_value not in _PROJECT_STATUS_TRANSITIONS.get(current_value, set()):
        raise InvalidTransitionError(f"project status cannot move from {current_value} to {target_value}")
    return target_value
