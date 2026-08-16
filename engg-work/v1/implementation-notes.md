# Implementation walkthrough: AI Micro-Story Studio V1

This document explains the implementation in runtime order. It is intended for an engineer who wants to read the system from the outside in: start the local stack, follow a creator action through the API and durable job system, then inspect the provider, artifact, renderer, and release boundaries.

## Evidence and scope

- **Verified:** The current repository tree, `engg-work/v1/PRD.md`, `tasks/plan.md`, `tasks/todo.md`, migrations `0001` through `0005`, Docker/Compose entrypoints, API routes, application commands/queries, persistence models, provider adapters, worker dispatch, renderer, frontend actions, and `tests/test_task11_contracts.py`.
- **Verified current additions:** `start.sh`/Compose Watch development reload, the legacy timeline `attempt` normalizer, pre-flush attempt protection, and LangSmith tracing configuration/metadata for the creative Deep Agent.
- **Documented intent:** The PRD defines a human-gated pipeline: project → ideas → approved StorySpec → approved VisualBible/storyboard → selected media → approved narration/captions → approved preview → final render → manual publication → metrics.
- **Limits:** This checkout has no committed base; the implementation is being described from the current source tree. Static checks and SQLite fixtures do not prove PostgreSQL migrations, Docker startup, Celery delivery, live provider behavior, LangSmith ingestion, browser behavior, or external publishing.

## 1. System in one view

The product is a single-creator local studio for producing short vertical story videos. The important boundary is that the creative agent stops at typed creative artifacts; it does not own persistence, retries, rendering, or publication state.

```text
Browser / Next.js workspace
        │ REST requests and workspace polling
        ▼
FastAPI API
        │ validates contracts, writes durable state, dispatches jobs
        ├──────────────► PostgreSQL
        │                 projects, versions, jobs, approvals, metrics
        └──────────────► Redis → Celery worker
                                  │
                                  ├─ creative Deep Agent → NIM / Groq
                                  ├─ Cloudflare image generation
                                  ├─ Pexels search and download
                                  ├─ Gemini TTS
                                  ├─ Groq Whisper alignment
                                  └─ Remotion / FFmpeg rendering
                                           │
                                           ▼
                                  local artifact storage
```

The web app reads a workspace projection. Postgres is the source of truth for workflow state. Redis and Celery coordinate work but do not decide whether a generation succeeded. Images, audio, captions, and videos are stored as local artifacts; database rows retain URIs and provenance metadata.

## 2. Starting the local system and reload behavior

### 2.1 Entry point

`start.sh` is the development startup command:

```text
./start.sh
  └─ docker compose up --build --watch
```

It uses strict Bash mode and `exec`, so signals reach Docker Compose and the attached service logs remain visible.

### 2.2 Compose services

`docker-compose.yml` defines:

- `postgres`: PostgreSQL 16 with a health check and named `postgres-data` volume.
- `redis`: Redis 7 with a ping health check.
- `api`: FastAPI/Uvicorn on port `8000`, with `--reload` in development.
- `worker`: Celery worker with FFmpeg, Node/npm, and the Remotion package installed.
- `web`: Next.js development server on port `3000`.
- `renderer`: Remotion Studio on port `3001`.
- `artifact-data`: shared named volume mounted by API and worker at `/var/lib/ai-micro-story-studio/artifacts`.

### 2.3 Compose Watch rules

The current Compose Watch rules solve the earlier “new changes are not reloading” problem without a custom watcher:

- API `services/api/app` and shared `studio` source are synchronized into `/app`; Uvicorn reloads the process.
- Worker source and shared `studio` source trigger a worker image rebuild/restart. Celery is not given a custom in-process watcher.
- Web `apps/web/app` is synchronized into `/app/app`; Next.js dev mode refreshes the page.
- Renderer `packages/renderer/src` is synchronized into `/app/src`; Remotion Studio reloads the source.
- Requirements, package manifests, Dockerfiles, and other image inputs trigger rebuilds.

This is development behavior. The Dockerfiles still copy source into images, so the same images can be built without relying on a host bind mount.

### 2.4 Environment and migrations

The Compose anchor `x-app-environment` passes provider settings, database/broker URLs, artifact settings, publishing mode, and LangSmith settings into API and worker containers. The existing `.env` supplies local secrets; the walkthrough never prints those values.

The startup script does not run Alembic migrations. Schema creation/update is represented by the ordered migration chain and must be performed separately with the repository’s Alembic configuration before runtime acceptance.

Migration order:

1. `0001_initial`: core project, creative, media, job, render, publication, and metric tables.
2. `0002_creative_workspace_fields`: idea selection and story critique.
3. `0003_task7_asset_job_requests`: durable async job request payloads.
4. `0004_task10_preview_approval`: explicit render preview approval timestamp.
5. `0005_task11_observability`: rejection reason and job observability/timeline fields.

## 3. Runtime control flow

The generic asynchronous path is:

```text
browser action
  → FastAPI route
  → Pydantic request validation
  → application command
  → GenerationJob creation and commit
  → Celery dispatch through Redis
  → worker validates current attempt/status
  → provider or renderer side effect
  → local artifact/database persistence
  → job completion or failure transition
  → workspace response and polling/SSE snapshot
```

The key ordering rule is in `studio/application/workflows/dispatch.py::enqueue_generation_job`: the job is committed before Celery dispatch. If dispatch fails, the job is marked failed with `dispatch_unavailable` and the API returns a service error containing the job ID.

The worker entrypoint is `services/worker/app/celery_app.py::run_generation_job`. It loads the job, determines the attempt, calls `start_generation_job`, and then routes by `job.type`:

- `creative_package_generation`
- `story_generation`
- `visual_bible_generation`
- `storyboard_generation`
- `scene_asset_generation`
- `scene_stock_search`
- `narration_generation`
- `caption_alignment`
- `render_preview`
- `render_final`

Before executing a stage, the worker verifies that the job is still queued for the expected attempt. A stale delivery does not get to mutate a newer retry attempt.

## 4. Domain contracts and state machines

### 4.1 Typed contracts

`studio/domain/schemas/contracts.py` contains domain-facing Pydantic contracts:

- `IdeaScores`: six scores, each in the range `0–10`.
- `IdeaCandidate`: premise, hook, scores, rationale, and source run.
- `StoryScene`: contiguous scene order, positive duration up to 60 seconds, narration, visual intent, asset strategy, prompt, motion, captions, and SFX.
- `StorySpec`: title, genre, target duration, premise, hook, narration, ending, tone, and scenes. Scene IDs must be unique, scene orders must be `1..N`, and total scene duration cannot exceed 180 seconds.
- `VisualBible`: style, characters, and locations. Character and location IDs must be unique.
- `GenerationJobContract`: basic job state, attempt limits, progress, errors, and timestamps.

`studio/application/contracts.py` adds API request/response contracts. `APIContract` forbids unknown fields and strips surrounding string whitespace. The API contracts additionally cover visual edits, scene edits, narration, captions, rendering, publications, metrics, assets, and the combined `CreativeWorkspaceResponse`.

### 4.2 Legal transitions

`studio/domain/services/transitions.py` is the shared transition gate:

- Approval: draft → approved/rejected, rejected → draft, approved → superseded.
- Jobs: queued → running/succeeded/failed/cancelled; running → succeeded/failed/cancelled; terminal states remain terminal.
- Project stage: monotonic order from ideation through complete.
- Project status: draft → active/completed/archived, with archived terminal.

Commands call these functions before changing state. The API maps invalid transitions to conflict responses where appropriate.

## 5. Durable data model

`studio/persistence/models.py` maps the workflow to SQLAlchemy tables.

| Record | Purpose | Important invariants |
| --- | --- | --- |
| `Project` | Creator workspace and current stage | Status and stage use the domain transition rules |
| `IdeaCandidate` | Retained creative candidate | `is_selected` marks the current choice; candidates are not deleted |
| `StoryVersion` | Typed StorySpec payload and critique | Versioned per project; approval/rejection state is explicit |
| `VisualBibleVersion` | Versioned visual direction | Approval is explicit and previous versions remain |
| `Scene` | Editable storyboard scene | Unique order per story version; duration is positive |
| `Asset` | Generated or downloaded scene/media candidate | Stores URI, provider/model, prompt, metadata, and status |
| `AssetSelection` | Current selected asset per scene | One row per scene; selection does not delete candidates |
| `NarrationVersion` | Audio version and approval | Versioned per project; points to local WAV artifact |
| `CaptionTrack` | Word timings and caption artifact URIs | One track per narration version |
| `GenerationJob` | Durable async execution state | Attempt and max-attempt checks; request and timeline JSON retained |
| `Render` | Preview/final render metadata | Final workflow requires an approved successful preview |
| `Publication` | Manual publication record | Requires a successful final render |
| `MetricSnapshot` | Append-only manual performance sample | Counts are non-negative; retention is API-bounded `0–100` |

`studio/persistence/database.py` normalizes legacy `postgres://`/`postgresql://` URLs to psycopg URLs, creates SQLAlchemy engines/session factories, and rolls back sessions on exceptions.

`studio/storage/local.py::LocalArtifactStorage` stores bytes atomically through a temporary file and `os.replace`. It validates URI schemes and prevents artifact keys from escaping the configured storage root.

## 6. Project and workspace read flow

The main browser read is:

```text
GET /api/v1/projects/{project_id}/workspace
  → main.get_workspace_route
  → project/idea/story/visual/scene/narration/render/publication queries
  → response helper functions
  → CreativeWorkspaceResponse
```

`services/api/app/main.py::get_workspace_route` builds one response containing the project, all retained creative versions, scenes with assets/selections, narration/caption summaries, renders, publications with metrics, and jobs.

The browser currently uses workspace polling rather than the SSE endpoint: `apps/web/app/page.tsx::HomePage` polls every 1.5 seconds while any job is queued or running. The API also exposes `GET /api/v1/projects/{project_id}/events`; `studio/application/workflows/progress.py::project_event_stream` polls the same project snapshot, emits a `project` event when the serialized snapshot changes, and emits heartbeat comments otherwise.

### Legacy timeline compatibility

The original job creation path recorded the first queued event before SQLAlchemy applied the model’s Python default, allowing old rows to contain `attempt: null`. The current implementation has three protections:

1. `get_or_create_generation_job` explicitly sets `attempt=1` before recording the queued event.
2. `record_generation_job_event` falls back to `1` if a new in-memory job has no attempt yet.
3. `normalize_generation_job_timeline` copies timeline events for read responses and changes only a missing/null attempt to `1`.

Both `_job_response` and `project_event_snapshot` use the normalizer. Historical JSON is not rewritten, but neither REST nor SSE can fail Pydantic validation because of the old value.

## 7. Creator flow: project to approved story

### 7.1 Create a project

```text
POST /api/v1/projects
  → ProjectCreateRequest
  → application.commands.projects::create_project
  → Project row with draft/ideation defaults
  → ProjectResponse
```

The frontend creates a project from the sidebar and selects it as the active workspace. `Project` is not automatically marked active; approval of a story/visual/narration stage advances status through the transition helpers.

### 7.2 Generate ideas

```text
Generate ideas button
  → POST /api/v1/projects/{id}/ideas/generate
  → GenerationJob(type=creative_package_generation)
  → Celery worker
  → CreativeDirector.run
  → persist_creative_package(persist_story=False)
  → retained IdeaCandidate rows
```

The route uses a caller-provided `run_key` in the request. `build_idempotency_key` hashes project, stage, version, and canonicalized request JSON, so key ordering does not change identity. A new run key is a regeneration; it creates a new job and keeps prior candidates.

### 7.3 Creative Director

`studio/agents/creative_director/director.py::CreativeDirector` composes three typed stages:

1. `IdeaExplorer`: generates a broad batch of scored candidates.
2. `StoryWriter`: turns the selected candidate into a StoryDraft with alternate endings.
3. `StoryCritic`: evaluates predictability, logic, pacing, originality, visual potential, and editing need.

`CreativeDirector.run` selects the candidate with the highest sum of idea scores, writes a draft, critiques it, and revises up to `max_revisions=2` while the critic recommends `revise`. The result is a typed `CreativePackage`; the agent does not write the database.

`services/worker/app/celery_app.py` is the persistence boundary. For a package job it calls `persist_creative_package(..., persist_story=False)`, retaining ideas only. For a story-generation job it loads the selected idea, calls `CreativeDirector.develop_story`, and persists a new draft through `persist_story_draft`.

### 7.4 LangSmith tracing

The project already uses LangChain-backed `ChatOpenAI` objects inside `deepagents.create_deep_agent`. Compose passes `LANGSMITH_TRACING`, `LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` into the worker.

`DeepAgentStage.invoke` passes LangChain invocation configuration:

- run name: `creative-director-{stage}`
- tags: `creative-director`, stage name, provider
- metadata: project ID, job ID, job type, attempt, business run ID, creative stage, provider, and model

The worker supplies job context, while `CreativeDirector.run` adds the generated business `run_id`. Fallback providers use the same metadata shape, so a failed primary and fallback attempt remain distinguishable in LangSmith. Tracing is environment-controlled and does not change the structured-output or provider fallback contract.

### 7.5 Select, revise, approve, or reject

- `POST /api/v1/projects/{id}/ideas/{idea_id}/select` marks exactly one project candidate selected.
- `PATCH /api/v1/projects/{id}/stories/{story_version_id}` calls `revise_story`, creates a new draft version, and retains the source version.
- `POST /api/v1/projects/{id}/stories/{story_version_id}/approve` calls `approve_story`, applies the approval transition, advances the project to `story`, and marks it active.
- `POST /api/v1/projects/{id}/stories/{story_version_id}/reject` requires a non-empty reason and stores it on `StoryVersion.rejection_reason`.

The frontend edits a local draft and sends the full `StorySpec` on save. Pydantic validation is repeated at the API boundary, so scene order, IDs, durations, and total duration remain enforced even when the browser is modified manually.

## 8. Creator flow: visual direction and storyboard

### 8.1 Visual Bible

```text
approved StorySpec
  → POST /api/v1/projects/{id}/visual-bible/generate
  → GenerationJob(type=visual_bible_generation)
  → worker generate_visual_bible
  → _approved_story + derive_visual_bible
  → VisualBibleVersion draft
```

`studio/application/commands/visuals.py::derive_visual_bible` is deterministic. It derives a visual treatment from genre/tone, creates a protagonist character, and creates one location per story scene. It does not call an LLM.

The creator can patch the versioned VisualBible and approve it. Approval advances the project to `visual_bible` only if it has not already passed that stage.

### 8.2 Storyboard

`generate_storyboard` requires both an approved StorySpec and an approved VisualBible. It is idempotent for a story version: if scenes already exist, it returns them rather than duplicating them. Otherwise it maps each `StoryScene` to a `Scene` row containing narration, duration, strategy, intent, prompt, motion, caption emphasis, and SFX.

The browser can patch scene duration, prompt, and asset strategy. The scene route validates that at least one field changes and that duration remains within the domain range.

## 9. Creator flow: scene assets

### 9.1 Generate or search

```text
scene control
  → POST /api/v1/scenes/{scene_id}/assets:generate
      or /assets:search-stock
  → scene-scoped GenerationJob
  → worker run_scene_asset_job
  → provider adapter
  → local artifact write
  → Asset rows
```

For generated images, `CloudflareFluxProvider.generate` sends an authenticated JSON request to the Cloudflare Workers AI endpoint and normalizes the base64 image into `GeneratedImage` with provider/model/request metadata.

For stock, `PexelsProvider.search` requests photo/video candidates, chooses an orientation-compatible source, and `download` retrieves the selected bytes. `persist_stock_media` retains source URL, download URL, photographer/license metadata, dimensions, media type, and query.

`studio/application/commands/assets.py` writes one append-only `Asset` per result and stores the bytes through `LocalArtifactStorage`. `select_scene_asset` verifies scene ownership and rejects failed assets before writing the single `AssetSelection` row.

### 9.2 Provider error boundary

Image and stock adapters classify authentication, invalid request, moderation, rate limit, transient, and invalid-response conditions through `MediaProviderError` subclasses. The worker catches provider exceptions in the common failure path, records the code/message on the job, and leaves prior candidates intact.

## 10. Creator flow: narration and captions

### 10.1 Narration

```text
approved StorySpec narration
  → POST /api/v1/projects/{id}/narration:generate
  → GenerationJob(type=narration_generation)
  → worker run_audio_job
  → GeminiTTSProvider.synthesize
  → PCM-to-WAV conversion
  → local artifact + NarrationVersion
```

`GeminiTTSProvider` sends the configured text, voice, and direction to the Gemini Interactions API, decodes base64 PCM, wraps it as 24 kHz mono WAV, and returns `AudioArtifact` with duration and metadata. `persist_narration` appends a version and stores only the URI in Postgres.

The creator explicitly approves a narration version. Approval advances the project to `narration` and supersedes any prior approved version through the shared approval transition.

### 10.2 Caption alignment

```text
approved or retained narration version
  → POST /api/v1/projects/{id}/captions:align
  → GenerationJob(type=caption_alignment)
  → stored WAV bytes
  → GroqWhisperProvider.align
  → WordTiming validation
  → CaptionTrack + JSON/SRT artifacts
```

`GroqWhisperProvider` sends multipart audio with verbose JSON and word timestamps. `persist_caption_track` rejects empty, negative, overlapping, or non-increasing word ranges, then writes deterministic word-level JSON and SRT artifacts. Re-alignment updates the one `CaptionTrack` for that narration version.

The API serves audio, SRT, and JSON artifacts through read-only routes. The frontend exposes playback, timing review, and narration regeneration while retaining previous versions.

## 11. Creator flow: rendering

### 11.1 Render request and final gate

```text
POST /api/v1/projects/{id}/renders:preview|final
  → prepare_render_request
  → approved story/narration/captions check
  → final-only approved-preview check
  → deterministic Render ID
  → GenerationJob(type=render_preview|render_final)
```

`prepare_render_request` selects the latest approved StorySpec and narration, requires a caption track, and calls `build_render_manifest` before queueing. A final request additionally requires a succeeded preview for the same StorySpec with `preview_approved_at` set.

The render ID is a UUID5 derived from project, render type, run key, story version, narration version, music asset, and SFX map. This gives the render layer deterministic identity while the job layer adds the usual canonical idempotency key.

### 11.2 Manifest validation

`studio/rendering/manifest.py::RenderManifest` is fixed to:

- 1080×1920 pixels
- 30 fps
- positive duration and frame count
- one selected available asset per storyboard scene
- approved narration and non-empty captions
- no caption overlap or overrun
- no narration longer than the scene timeline
- no dead air unless music is present

The manifest converts scene durations to integer frame counts and resolves local artifact paths through the storage boundary. Selected assets must be images/photos or videos; unsupported types fail before the renderer is invoked.

### 11.3 Remotion execution and output checks

`studio/rendering/runner.py::render_manifest` stages every input into a temporary public directory, writes the manifest as props, and invokes:

```text
npx --no-install remotion render src/index.tsx StoryVideo ... --codec h264 --audio-codec aac --concurrency 1
```

`packages/renderer/src/index.tsx::StoryVideo` composes scene sequences, uses cover-cropped assets with bounded motion, overlays safe-area captions, and mixes narration, optional music, and scene SFX.

The runner then uses system or bundled `ffprobe` to require a non-empty H.264/AAC MP4, 1080×1920 dimensions, 30 fps, an audio stream, and duration within tolerance. Only after these checks does the worker store the MP4 and complete the durable job.

## 12. Creator flow: manual release and metrics

`POST /api/v1/projects/{id}/publications` calls `create_publication`. It refuses to create a record until a successful final render exists, advances the project to `metrics`, and stores platform, optional URL, external ID, and publication date. It does not call a social platform.

`POST /api/v1/publications/{publication_id}/metrics` calls `create_metric_snapshot`. Each snapshot is append-only and stores views, retention, likes, comments, shares/saves, followers gained, and capture time. The frontend displays publication history and lets the creator add snapshots over time.

## 13. API surface by responsibility

`services/api/app/main.py` is intentionally a thin HTTP boundary. Its route groups are:

- health and project listing/creation/read
- workspace projection
- idea listing/generation/selection
- story listing/revision/approval/rejection
- VisualBible generation/revision/approval
- storyboard generation and scene revision
- narration listing/generation/approval and audio retrieval
- caption alignment and SRT/JSON retrieval
- preview/final render submission, listing, approval, and MP4 retrieval
- manual publication and metric snapshot creation/listing
- scene asset listing/generation/stock search/selection/content retrieval
- generic job submission/read/retry
- project SSE events

The response helpers (`_idea_response`, `_story_response`, `_visual_bible_response`, `_scene_response`, `_narration_response`, `_render_response`, `_publication_response`, `_job_response`) translate persistence objects into API contracts. They do not make workflow decisions except where read-time compatibility is required for old timeline JSON.

## 14. Failure, retry, and transaction behavior

### Validation failures

Pydantic rejects malformed payloads before commands run. Commands then enforce project ownership, required approvals, legal transitions, selected assets, and bounded job attempts. API routes map not-found, validation, conflict, and dispatch errors to HTTP responses.

### Duplicate submissions

`build_idempotency_key` hashes canonical JSON with sorted keys. The key includes project, stage, version, and request. The same run key/request returns the existing job without dispatching another task. A new run key is a deliberate regeneration.

### Worker stale deliveries

`start_generation_job`, `complete_generation_job`, `fail_generation_job`, and `update_generation_job_observability` all compare the supplied attempt to the locked job. A late delivery from an older attempt cannot complete or overwrite a newer retry.

### Retry versus regeneration

- Retry: same job/request, increment `attempt`, reset transient execution fields, append `retry_queued`, bounded by `max_attempts`.
- Regeneration: new run key/idempotency request, new job/version/candidate, prior successful artifacts remain.

### Provider/render failures

Provider adapters classify errors; the worker catches exceptions and calls `fail_generation_job`. Render failures additionally mark the related `Render` failed. Failure details include code/message and remain visible through the workspace job card.

### Artifact/database boundary

Artifact writes happen outside or alongside database command operations. The storage layer uses atomic file replacement, but a complete compensation strategy for “artifact write succeeds, DB commit fails” is not visible. This is a runtime follow-up, not something the current static checks prove.

## 15. Important abstractions and ownership boundaries

| Abstraction | Owns | Deliberately does not own |
| --- | --- | --- |
| `domain.schemas` | Typed domain shape and invariants | Persistence, providers, HTTP |
| `domain.services.transitions` | Legal state transitions | Side effects or transactions |
| `application.commands` | Business mutations and prerequisites | HTTP serialization or vendor payloads |
| `application.queries` | Read projections and workspace snapshots | Mutating state |
| `application.workflows.dispatch` | Commit-before-dispatch and Celery adapter | Completion truth |
| `persistence.operations` | Shared versioning, job events, idempotency, transition mechanics | Provider calls |
| `providers/*` | Vendor requests, normalization, classified errors | Domain persistence/retries |
| `LocalArtifactStorage` | Safe URI/path and atomic bytes | Business metadata |
| `RenderManifest` | Validated deterministic render input | Job dispatch and approval decisions |
| `run_generation_job` | Worker execution routing | Durable workflow ownership |
| `DeepAgentStage` | Structured agent invocation and tracing metadata | Persistence, retries, completion state |

## 16. Design decisions

- **Documented intent:** V1 is one creator, one vertical short-video format, manual publishing, free-first hosted providers, local artifacts, and no local model runtime.
- **Verified implementation:** Creative outputs cross into production only as typed `CreativePackage`, `StorySpec`, `VisualBible`, and provider-neutral media artifacts. Agents cannot write database rows or decide job completion.
- **Verified implementation:** Postgres is durable workflow truth; Redis/Celery coordinates execution; job state is persisted before dispatch.
- **Verified implementation:** Versions and candidates are append-only; selection changes a pointer row rather than deleting media.
- **Verified implementation:** Final rendering is gated by successful preview approval for the same approved StorySpec version.
- **Verified implementation:** LangSmith tracing is environment-controlled and attached at the existing LangChain agent invocation boundary rather than through a second tracing system. See the official [LangChain LangSmith tracing documentation](https://docs.langchain.com/langsmith/trace-with-langchain).
- **Verified compatibility choice:** Old `attempt: null` timeline events are normalized on read instead of rewritten through a database migration. New writes are also guarded.
- **Inference:** The application has separate API/worker/renderer containers now because long-running work, browser-facing development, and deterministic rendering have different process lifecycles; this is consistent with the PRD but not an independently measured production requirement.

## 17. Critical code to inspect manually

1. `start.sh` — Verify Compose Watch is available in the local Docker version and that worker source changes cause rebuild/restart rather than stale code execution.
2. `docker-compose.yml::services.api.develop.watch` / `services.worker.develop.watch` — Verify sync targets and rebuild inputs after changing dependencies or shared source.
3. `services/api/app/main.py::get_workspace_route` and `_job_response` — Verify the read projection, nested response construction, and legacy timeline normalization.
4. `studio/application/workflows/dispatch.py::enqueue_generation_job` — Verify commit-before-dispatch and the dispatch-failure transaction boundary.
5. `studio/persistence/operations.py::record_generation_job_event` and `retry_generation_job` — Verify attempt, timeline ordering, latency, and retry/regeneration semantics.
6. `services/worker/app/celery_app.py::run_generation_job` — Verify the stage routing, attempt guards, provider side effects, and failure cleanup.
7. `studio/agents/creative_director/deep_agents.py::DeepAgentStage.invoke` — Verify LangChain config inheritance, fallback provider metadata, and structured-output extraction.
8. `studio/application/commands/visuals.py::generate_storyboard` and `studio/rendering/manifest.py::build_render_manifest` — Verify approved-version and selected-asset alignment.
9. `studio/rendering/runner.py::render_manifest` and `packages/renderer/src/index.tsx::StoryVideo` — Verify staged files, frame boundaries, caption timing, audio mix, and output probing.
10. `studio/application/commands/release.py::create_publication` — Verify the final-render gate and the deliberate absence of external publishing.

## 18. Tests and verification

| Check | What it proves | What it does not prove |
| --- | --- | --- |
| `python3 tests/test_task11_contracts.py` | Five contract checks cover idempotency, observability shape, provider error markers, renderer guards, and critical frontend paths | Full behavior, database, worker, provider, or browser execution |
| Python `py_compile` with temporary cache prefix | Current Python modules parse successfully | Runtime imports and environment configuration |
| `npx tsc --noEmit --incremental false` | Web TypeScript type checking | Browser interaction and API integration |
| Next production build | Web bundle compiles | Live API, browser, or media playback |
| `docker compose config --quiet` | Compose syntax and resolved service configuration | Image build, container startup, health checks, or watch events |
| SQLite model/command fixtures | Selected persistence/state paths can execute in an isolated database | PostgreSQL-specific migrations and Celery/Redis delivery |
| Timeline regression check | REST/SSE snapshots and Pydantic validation accept old null attempts; new event writer falls back to attempt 1 | Repair of old JSON rows, which is intentionally not performed |
| Mocked Deep Agent invocation | LangSmith run name, tags, provider/model, and job metadata reach the existing `agent.invoke` config | Real LangSmith network ingestion or provider quality |
| Remotion fixture/render checks | Manifest/frame/output guards and a fixture MP4 path | Full approved-project flow, browser playback, and worker transaction behavior |

## 19. Known limitations and concrete follow-ups

- Run Alembic against a fresh PostgreSQL database and verify migration drift against the SQLAlchemy models.
- Start the Docker stack with `./start.sh`, exercise API health, Redis/Postgres health, worker delivery, and Compose Watch reload behavior.
- Run a real creative job with configured NIM/Groq credentials and verify the worker persists candidates/story output and LangSmith receives traces in the configured project.
- Run credentialed Cloudflare, Pexels, Gemini, and Groq smoke checks; record quota/error evidence separately from mocked checks.
- Execute the browser journey from project creation through final render, manual publication, and multiple metric snapshots.
- Verify render playback and inspect captions, cropping, audio synchronization, SFX, and safe areas visually.
- Decide whether artifact compensation is needed after observing real worker/database failure behavior.
- T12 content validation remains operational work: publish 10–15 initial videos, continue toward approximately 30, and use measured audience/production evidence before expanding scope.

## 20. Ownership check

1. **Where does the system enter?** `apps/web/app/page.tsx::HomePage` for browser actions, or the corresponding route in `services/api/app/main.py` for HTTP clients.
2. **Which function owns each core decision?** Commands own approvals, prerequisites, versioning, and release gates; the worker only executes; providers only normalize external responses.
3. **Where is state persisted?** SQLAlchemy models in Postgres hold business state, job state, and URIs; `LocalArtifactStorage` holds binary artifacts.
4. **What prevents duplicate execution?** Canonical idempotency keys, database uniqueness, locked job reads, and attempt matching.
5. **What happens if a provider succeeds but local persistence fails?** The job can fail and the DB transaction can roll back; orphan artifact cleanup is not currently visible.
6. **Which failures are retried?** Explicit failed-job retries are bounded by `max_attempts`; provider error classes retain retryability metadata, while provider-specific automatic retry remains outside the application.
7. **What is the human gate before expensive downstream work?** Approved StorySpec, approved VisualBible, selected scene assets, approved narration/captions, and approved successful preview before final export.
8. **How does another provider integrate?** Implement the relevant provider protocol, normalize into `GeneratedImage`, `DownloadedStockMedia`, `AudioArtifact`, `WordTiming`, or the typed creative output, then update the factory/configuration; commands and UI should remain unchanged.
9. **Where does observability live?** Durable job summaries/timeline in `GenerationJob`, structured logs in `record_generation_job_event`, LangSmith traces at Deep Agent invocation, and frontend job-card/SSE projections.
10. **What remains deliberately outside V1?** Autonomous publishing, multi-tenant SaaS, local inference, distributed orchestration, full NLE editing, advanced analytics agents, and content-scale expansion before validation.

## 21. Suggested reading order

For a first pass, read in this order:

1. `engg-work/v1/PRD.md` sections 1, 4, 5, 7, 8, 16, and 23–26 for intent and acceptance boundaries.
2. `docker-compose.yml`, `start.sh`, and the four Dockerfiles for process topology and local startup.
3. `studio/domain/constants.py`, `studio/domain/services/transitions.py`, and `studio/domain/schemas/contracts.py` for invariants.
4. `studio/persistence/models.py`, `studio/persistence/operations.py`, and `studio/application/workflows/dispatch.py` for durable job truth.
5. `services/api/app/main.py` and `studio/application/commands/*` for HTTP-to-business flow.
6. `services/worker/app/celery_app.py` for execution routing and failure behavior.
7. `studio/agents/creative_director/*` and `studio/providers/*` for external integrations.
8. `studio/rendering/manifest.py`, `studio/rendering/runner.py`, and `packages/renderer/src/index.tsx` for final media output.
9. `apps/web/app/page.tsx` for the creator’s complete UI journey.
10. `tests/test_task11_contracts.py` and `tasks/todo.md` for current proof and remaining gates.
