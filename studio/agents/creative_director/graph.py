from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar, TypedDict
from uuid import NAMESPACE_URL, uuid5

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from studio.agents.creative_director.contracts import (
    CreativePackage,
    IdeaBatchOutput,
    ShotSpecBatchOutput,
    StoryCritiqueOutput,
    StoryDraftOutput,
    VisualBibleOutput,
)
from studio.domain.schemas.contracts import IdeaCandidate, StorySpec, ShotSpec, VisualBible
from studio.providers.llm.openai_compatible import OpenAICompatibleLLMProvider


OutputT = TypeVar("OutputT", bound=BaseModel)
CreativeMode = Literal[
    "creative_package",
    "story_generation",
    "visual_bible_generation",
    "shot_spec_generation",
]


class ProviderAttempt(TypedDict, total=False):
    stage: str
    provider: str
    model: str
    attempt: int
    outcome: Literal["succeeded", "failed"]
    error: str


class CreativeGraphState(TypedDict, total=False):
    mode: CreativeMode
    brief: str
    idea_count: int
    idea_batch: IdeaBatchOutput | None
    candidates: list[IdeaCandidate]
    selected_idea: IdeaCandidate | None
    story_spec: StorySpec | None
    visual_bible: VisualBible | None
    shot_specs: list[ShotSpec] | None
    draft: StoryDraftOutput | None
    critique: StoryCritiqueOutput | None
    revision_count: int
    run_id: str
    provider_attempts: list[ProviderAttempt]
    trace_metadata: dict[str, Any]
    result: CreativePackage | tuple[StoryDraftOutput, StoryCritiqueOutput] | None


class AgentStage(Protocol, Generic[OutputT]):
    provider_names: tuple[str, ...]

    def invoke(self, prompt: str, *, metadata: dict[str, Any] | None = None) -> OutputT: ...


@dataclass
class LangGraphStage(Generic[OutputT]):
    response_model: type[OutputT]
    system_prompt: str
    models: tuple[Any, ...]
    stage_name: str
    provider_names: tuple[str, ...]
    provider_models: tuple[str, ...]

    @classmethod
    def from_providers(
        cls,
        response_model: type[OutputT],
        system_prompt: str,
        providers: tuple[OpenAICompatibleLLMProvider, ...],
        *,
        name: str,
    ) -> "LangGraphStage[OutputT]":
        models = tuple(
            ChatOpenAI(
                api_key=provider.api_key,
                base_url=provider.base_url,
                model=provider.model,
                timeout=provider.timeout,
                max_retries=0,
            ).with_structured_output(response_model)
            for provider in providers
        )
        return cls(
            response_model,
            system_prompt,
            models,
            name,
            tuple(provider.name for provider in providers),
            tuple(provider.model for provider in providers),
        )

    def invoke(self, prompt: str, *, metadata: dict[str, Any] | None = None) -> OutputT:
        output, _ = self.invoke_with_attempts(prompt, metadata=metadata)
        return output

    def invoke_with_attempts(
        self,
        prompt: str,
        *,
        config: RunnableConfig | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[OutputT, list[ProviderAttempt]]:
        last_error: Exception | None = None
        attempts: list[ProviderAttempt] = []
        for index, model in enumerate(self.models):
            provider = self.provider_names[index]
            attempt = {
                "stage": self.stage_name,
                "provider": provider,
                "model": self.provider_models[index],
                "attempt": index + 1,
            }
            try:
                result = model.invoke(
                    [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    config=_stage_config(
                        config,
                        metadata=metadata,
                        stage=self.stage_name,
                        provider=provider,
                        model=self.provider_models[index],
                        attempt=index + 1,
                    ),
                )
                output = _validate(result, self.response_model)
                attempts.append({**attempt, "outcome": "succeeded"})
                return output, attempts
            except Exception as exc:  # the configured fallback is the only provider retry
                last_error = exc
                attempts.append({**attempt, "outcome": "failed", "error": type(exc).__name__})
        if last_error is None:
            raise RuntimeError("no LangGraph model configured")
        raise last_error


def _stage_config(
    config: RunnableConfig | None,
    *,
    metadata: dict[str, Any] | None,
    stage: str,
    provider: str,
    model: str,
    attempt: int,
) -> RunnableConfig:
    merged = dict(config or {})
    merged["run_name"] = f"creative-director-{stage}"
    merged["tags"] = [*(merged.get("tags") or []), "creative-director", stage, provider]
    merged["metadata"] = {
        **(merged.get("metadata") or {}),
        **(metadata or {}),
        "creative_stage": stage,
        "provider": provider,
        "model": model,
        "attempt": attempt,
    }
    return merged


def _validate(value: Any, response_model: type[OutputT]) -> OutputT:
    if isinstance(value, response_model):
        return value
    if isinstance(value, dict):
        return response_model.model_validate(value)
    if isinstance(value, str):
        return response_model.model_validate(json.loads(value))
    raise TypeError("LangGraph model did not return a structured response")


def build_creative_graph(
    providers: tuple[OpenAICompatibleLLMProvider, ...],
    *,
    idea_prompt: str,
    story_prompt: str,
    critic_prompt: str,
    max_revisions: int = 2,
):
    if not providers:
        raise ValueError("at least one creative provider is required")
    if not 0 <= max_revisions <= 2:
        raise ValueError("max_revisions must be between 0 and 2")

    stages = {
        "idea_explorer": LangGraphStage.from_providers(
            IdeaBatchOutput,
            idea_prompt,
            providers,
            name="idea-explorer",
        ),
        "story_writer": LangGraphStage.from_providers(
            StoryDraftOutput,
            story_prompt,
            providers,
            name="story-writer",
        ),
        "story_critic": LangGraphStage.from_providers(
            StoryCritiqueOutput,
            critic_prompt,
            providers,
            name="story-critic",
        ),
        "visual_bible_writer": LangGraphStage.from_providers(
            VisualBibleOutput,
            "Return only a canonical Visual Bible. Specify explicit global lighting, lens language, render style, and aspect ratio; canonical character identity fields; and physical location geometry, time, weather, lighting, persistent props, and immutable traits. Reuse one location ID whenever shots occupy the same physical place.",
            providers,
            name="visual-bible-writer",
        ),
        "shot_spec_writer": LangGraphStage.from_providers(
            ShotSpecBatchOutput,
            "Return one validated ShotSpec per StorySpec scene. Use only approved Visual Bible identities and location IDs. Keep temporary props moment-specific, preserve continuity sources, and request readable text only when the story explicitly needs it.",
            providers,
            name="shot-spec-writer",
        ),
    }

    def route_mode(state: CreativeGraphState) -> dict[str, Any]:
        if state.get("mode") not in {
            "creative_package",
            "story_generation",
            "visual_bible_generation",
            "shot_spec_generation",
        }:
            raise ValueError(
                "creative graph mode must be creative_package, story_generation, "
                "visual_bible_generation, or shot_spec_generation"
            )
        return {}

    def idea_explorer(state: CreativeGraphState, config: RunnableConfig) -> dict[str, Any]:
        run_id = state["run_id"]
        idea_count = state.get("idea_count", 20)
        output, attempts = stages["idea_explorer"].invoke_with_attempts(
            f"Brief: {state['brief']}\nGenerate exactly {idea_count} candidate ideas. This is run {run_id}.",
            config=config,
            metadata={**state.get("trace_metadata", {}), "run_id": run_id},
        )
        candidates = [
            IdeaCandidate.model_validate(
                {
                    "id": str(uuid5(NAMESPACE_URL, f"creative-candidate:{run_id}:{index}")),
                    "premise": idea.premise,
                    "hook": idea.hook,
                    "scores": idea.scores,
                    "rationale": idea.rationale,
                    "source_run": run_id,
                }
            )
            for index, idea in enumerate(output.ideas)
        ]
        return {
            "idea_batch": output,
            "candidates": candidates,
            "provider_attempts": [*state.get("provider_attempts", []), *attempts],
        }

    def select_candidate(state: CreativeGraphState) -> dict[str, Any]:
        candidates = state.get("candidates", [])
        if not candidates:
            raise ValueError("idea explorer returned no candidates")
        selected = max(
            enumerate(candidates),
            key=lambda item: (sum(item[1].scores.model_dump().values()), -item[0]),
        )[1]
        return {"selected_idea": selected}

    def story_writer(state: CreativeGraphState, config: RunnableConfig) -> dict[str, Any]:
        selected = state.get("selected_idea")
        if selected is None:
            raise ValueError("story writer requires a selected idea")
        critique = state.get("critique")
        critique_text = critique.model_dump_json() if critique else "No previous critique; create the first draft."
        output, attempts = stages["story_writer"].invoke_with_attempts(
            "\n".join(
                (
                    f"Brief: {state['brief']}",
                    f"Selected idea: {selected.model_dump_json()}",
                    f"Previous critique: {critique_text}",
                )
            ),
            config=config,
            metadata={**state.get("trace_metadata", {}), "run_id": state["run_id"]},
        )
        revision_count = state.get("revision_count", 0)
        if critique is not None and critique.recommendation == "revise":
            revision_count += 1
        return {
            "draft": output,
            "revision_count": revision_count,
            "provider_attempts": [*state.get("provider_attempts", []), *attempts],
        }

    def story_critic(state: CreativeGraphState, config: RunnableConfig) -> dict[str, Any]:
        draft = state.get("draft")
        if draft is None:
            raise ValueError("story critic requires a story draft")
        output, attempts = stages["story_critic"].invoke_with_attempts(
            f"Critique this StorySpec and its alternate endings:\n{draft.model_dump_json()}",
            config=config,
            metadata={**state.get("trace_metadata", {}), "run_id": state["run_id"]},
        )
        return {
            "critique": output,
            "provider_attempts": [*state.get("provider_attempts", []), *attempts],
        }

    def visual_bible_writer(state: CreativeGraphState, config: RunnableConfig) -> dict[str, Any]:
        story = state.get("story_spec")
        if story is None:
            raise ValueError("visual bible writer requires an approved StorySpec")
        output, attempts = stages["visual_bible_writer"].invoke_with_attempts(
            f"Approved StorySpec:\n{story.model_dump_json()}",
            config=config,
            metadata={**state.get("trace_metadata", {}), "run_id": state["run_id"]},
        )
        return {
            "visual_bible": output.visual_bible,
            "provider_attempts": [*state.get("provider_attempts", []), *attempts],
        }

    def shot_spec_writer(state: CreativeGraphState, config: RunnableConfig) -> dict[str, Any]:
        story = state.get("story_spec")
        bible = state.get("visual_bible")
        if story is None or bible is None:
            raise ValueError("shot spec writer requires an approved StorySpec and Visual Bible")
        output, attempts = stages["shot_spec_writer"].invoke_with_attempts(
            f"Approved StorySpec:\n{story.model_dump_json()}\nApproved Visual Bible:\n{bible.model_dump_json()}",
            config=config,
            metadata={**state.get("trace_metadata", {}), "run_id": state["run_id"]},
        )
        return {
            "shot_specs": output.shot_specs,
            "provider_attempts": [*state.get("provider_attempts", []), *attempts],
        }

    def revise_or_finish(state: CreativeGraphState) -> str:
        critique = state.get("critique")
        if critique is None:
            raise ValueError("revision route requires a story critique")
        if critique.recommendation == "revise" and state.get("revision_count", 0) < max_revisions:
            return "revise"
        return "package_result" if state.get("mode") == "creative_package" else "story_result"

    def package_result(state: CreativeGraphState) -> dict[str, Any]:
        selected = state.get("selected_idea")
        draft = state.get("draft")
        critique = state.get("critique")
        candidates = state.get("candidates", [])
        if selected is None or draft is None or critique is None or not candidates:
            raise ValueError("package result requires candidates, selection, draft, and critique")
        providers_used = sorted(
            {attempt["provider"] for attempt in state.get("provider_attempts", []) if attempt.get("outcome") == "succeeded"}
        )
        return {
            "result": CreativePackage(
                run_id=state["run_id"],
                candidates=candidates,
                selected_idea_id=selected.id,
                story=draft.story,
                alternate_endings=draft.alternate_endings,
                critique=critique,
                revision_count=state.get("revision_count", 0),
                providers_used=providers_used,
            )
        }

    def story_result(state: CreativeGraphState) -> dict[str, Any]:
        draft = state.get("draft")
        critique = state.get("critique")
        if draft is None or critique is None:
            raise ValueError("story result requires a draft and critique")
        return {"result": (draft, critique)}

    def visual_bible_result(state: CreativeGraphState) -> dict[str, Any]:
        bible = state.get("visual_bible")
        if bible is None:
            raise ValueError("visual bible result requires a Visual Bible")
        return {"result": bible}

    def shot_spec_result(state: CreativeGraphState) -> dict[str, Any]:
        specs = state.get("shot_specs")
        if not specs:
            raise ValueError("shot spec result requires ShotSpecs")
        return {"result": specs}

    builder = StateGraph(CreativeGraphState)
    builder.add_node("route_mode", route_mode)
    builder.add_node("idea_explorer", idea_explorer)
    builder.add_node("select_candidate", select_candidate)
    builder.add_node("story_writer", story_writer)
    builder.add_node("story_critic", story_critic)
    builder.add_node("visual_bible_writer", visual_bible_writer)
    builder.add_node("shot_spec_writer", shot_spec_writer)
    builder.add_node("revise_or_finish", lambda state: {})
    builder.add_node("package_result", package_result)
    builder.add_node("story_result", story_result)
    builder.add_node("visual_bible_result", visual_bible_result)
    builder.add_node("shot_spec_result", shot_spec_result)
    builder.add_edge(START, "route_mode")
    builder.add_conditional_edges(
        "route_mode",
        lambda state: state["mode"],
        {
            "creative_package": "idea_explorer",
            "story_generation": "story_writer",
            "visual_bible_generation": "visual_bible_writer",
            "shot_spec_generation": "shot_spec_writer",
        },
    )
    builder.add_edge("idea_explorer", "select_candidate")
    builder.add_edge("select_candidate", "story_writer")
    builder.add_edge("story_writer", "story_critic")
    builder.add_edge("story_critic", "revise_or_finish")
    builder.add_conditional_edges(
        "revise_or_finish",
        revise_or_finish,
        {"revise": "story_writer", "package_result": "package_result", "story_result": "story_result"},
    )
    builder.add_edge("package_result", END)
    builder.add_edge("story_result", END)
    builder.add_edge("visual_bible_writer", "visual_bible_result")
    builder.add_edge("visual_bible_result", END)
    builder.add_edge("shot_spec_writer", "shot_spec_result")
    builder.add_edge("shot_spec_result", END)
    return builder.compile()
