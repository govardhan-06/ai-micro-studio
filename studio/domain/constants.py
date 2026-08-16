from enum import Enum


class ApprovalStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ProjectStage(str, Enum):
    IDEATION = "ideation"
    STORY = "story"
    VISUAL_BIBLE = "visual_bible"
    STORYBOARD = "storyboard"
    MEDIA = "media"
    NARRATION = "narration"
    RENDER = "render"
    METRICS = "metrics"
    COMPLETE = "complete"
