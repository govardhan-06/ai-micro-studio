from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from studio.agents.creative_director.contracts import (
    CreativePackage,
    StoryCritiqueOutput,
    StoryDraftOutput,
)
from studio.agents.creative_director.graph import build_creative_graph
from studio.providers.llm.groq import GroqProvider
from studio.providers.llm.nvidia_nim import NvidiaNIMProvider
from studio.providers.llm.openai_compatible import OpenAICompatibleLLMProvider


IDEA_EXPLORER_PROMPT = """You are IdeaExplorer. Return only the requested typed output. Generate a broad batch of short-form story premises. Score each idea for hook, novelty, emotional pull, twist/payoff, visual potential, and short-form fit. Avoid generic phrasing and explain the selection rationale."""
STORY_WRITER_PROMPT = """You are StoryWriter. Return only the requested typed output. Turn the selected premise into a coherent 45-60 second StorySpec with an immediate hook, concrete visual direction for every scene, and up to three alternate endings. Keep narration performable and avoid exposition."""
STORY_CRITIC_PROMPT = """You are StoryCritic. Return only the requested typed output. Inspect the supplied StorySpec for predictability, logical gaps, pacing, generic phrasing, originality, visual potential, and editing need. Recommend accept or revise and list concrete issues."""


@dataclass
class CreativeDirector:
    graph: Any
    story_writer: Any
    max_revisions: int = 2

    @classmethod
    def from_env(cls) -> "CreativeDirector":
        providers = _providers_from_env()
        return cls(
            graph=build_creative_graph(
                providers,
                idea_prompt=IDEA_EXPLORER_PROMPT,
                story_prompt=STORY_WRITER_PROMPT,
                critic_prompt=STORY_CRITIC_PROMPT,
                max_revisions=2,
            ),
            # The worker uses this existing read-only metadata surface when recording a story job.
            story_writer=SimpleNamespace(
                stage=SimpleNamespace(provider_names=tuple(provider.name for provider in providers))
            ),
        )

    def run(
        self,
        brief: str,
        *,
        idea_count: int = 20,
        run_id: str | None = None,
        trace_metadata: dict[str, Any] | None = None,
    ) -> CreativePackage:
        run_id = run_id or str(uuid4())
        trace_metadata = _trace_metadata(
            trace_metadata,
            run_id=run_id,
            mode="creative_package",
            job_type="creative_package_generation",
        )
        state = self._invoke_graph(
            {
                "mode": "creative_package",
                "brief": brief,
                "idea_count": idea_count,
                "run_id": run_id,
                "trace_metadata": trace_metadata,
            },
            mode="creative_package",
            trace_metadata=trace_metadata,
        )
        result = state.get("result")
        if not isinstance(result, CreativePackage):
            raise TypeError("creative package graph returned an invalid result")
        return result

    def develop_story(
        self,
        brief: str,
        candidate,
        *,
        trace_metadata: dict[str, Any] | None = None,
    ) -> tuple[StoryDraftOutput, StoryCritiqueOutput]:
        run_id = str(uuid4())
        trace_metadata = _trace_metadata(
            trace_metadata,
            run_id=run_id,
            mode="story_generation",
            job_type="story_generation",
        )
        state = self._invoke_graph(
            {
                "mode": "story_generation",
                "brief": brief,
                "selected_idea": candidate,
                "run_id": run_id,
                "trace_metadata": trace_metadata,
            },
            mode="story_generation",
            trace_metadata=trace_metadata,
        )
        result = state.get("result")
        if not isinstance(result, tuple) or len(result) != 2:
            raise TypeError("story graph returned an invalid result")
        draft, critique = result
        if not isinstance(draft, StoryDraftOutput) or not isinstance(critique, StoryCritiqueOutput):
            raise TypeError("story graph returned invalid typed outputs")
        return draft, critique

    def _invoke_graph(
        self,
        state: dict[str, Any],
        *,
        mode: str,
        trace_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        job_type = str(trace_metadata["job_type"])
        return self.graph.invoke(
            state,
            config={
                "run_name": f"creative-director-graph-{mode}",
                "tags": ["creative-director", "langgraph", mode, job_type],
                "metadata": trace_metadata,
            },
        )


def _trace_metadata(
    trace_metadata: dict[str, Any] | None,
    *,
    run_id: str,
    mode: str,
    job_type: str,
) -> dict[str, Any]:
    metadata = {**(trace_metadata or {}), "run_id": run_id, "mode": mode}
    metadata["job_type"] = metadata.get("job_type") or job_type
    metadata["thread_id"] = metadata.get("thread_id") or metadata.get("job_id") or run_id
    return metadata


def _providers_from_env() -> tuple[OpenAICompatibleLLMProvider, ...]:
    nim_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    nim_model = os.environ.get("NIM_MODEL", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not nim_key or not nim_model:
        raise RuntimeError("NVIDIA_API_KEY and NIM_MODEL are required for the primary Creative Director")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY is required for the configured Creative Director fallback")
    return (
        NvidiaNIMProvider(model=nim_model, api_key=nim_key, base_url=os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")),
        GroqProvider(model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"), api_key=groq_key, base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")),
    )
