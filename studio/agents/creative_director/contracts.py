from __future__ import annotations

from typing import Literal

from pydantic import Field

from studio.domain.schemas.contracts import Contract, IdeaCandidate, IdeaScores, StorySpec


class IdeaCandidateOutput(Contract):
    premise: str = Field(min_length=1)
    hook: str = Field(min_length=1)
    scores: IdeaScores
    rationale: str = Field(min_length=1)


class IdeaBatchOutput(Contract):
    ideas: list[IdeaCandidateOutput] = Field(min_length=1, max_length=30)


class AlternateEnding(Contract):
    label: str = Field(min_length=1)
    text: str = Field(min_length=1)


class StoryDraftOutput(Contract):
    story: StorySpec
    alternate_endings: list[AlternateEnding] = Field(default_factory=list, max_length=3)


class CritiqueScores(Contract):
    predictability: float = Field(ge=0, le=10)
    logic: float = Field(ge=0, le=10)
    pacing: float = Field(ge=0, le=10)
    originality: float = Field(ge=0, le=10)
    visual_potential: float = Field(ge=0, le=10)
    editing_need: float = Field(ge=0, le=10)


class StoryCritiqueOutput(Contract):
    summary: str = Field(min_length=1)
    strengths: list[str] = Field(min_length=1)
    issues: list[str] = Field(default_factory=list)
    scores: CritiqueScores
    recommendation: Literal["accept", "revise"]


class CreativePackage(Contract):
    run_id: str = Field(min_length=1)
    candidates: list[IdeaCandidate] = Field(min_length=1, max_length=30)
    selected_idea_id: str = Field(min_length=1)
    story: StorySpec
    alternate_endings: list[AlternateEnding] = Field(default_factory=list, max_length=3)
    critique: StoryCritiqueOutput
    revision_count: int = Field(ge=0, le=2)
    providers_used: list[str] = Field(min_length=1)
