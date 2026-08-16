# AI Micro-Story Studio — V1 Product Requirements Document

**Status:** Implementation baseline for V1  
**Updated:** 15 August 2026  
**Primary creator:** Single creator in V1; creative collaborators come after audience validation  
**Content niche:** Cinematic micro-fiction with high-concept hooks and twist/payoff endings  
**Primary channels:** YouTube Shorts + Instagram Reels; cross-posting expansion later  
**Build cadence:** Weekend side project, ~3.5 hours Saturday + ~3.5 hours Sunday  
**Validation mode:** Free-first providers; no local AI model inference

## 1. Executive Summary

AI Micro-Story Studio is an AI-assisted content-production product for creating original short-form fictional videos. V1 is designed around a deliberate split: a bounded agentic creative layer explores ideas and develops stories, while the production system remains deterministic, observable, resumable, and human-controlled.

**The V1 engineering objective is not a throwaway prototype.** The frontend, backend, data model, job system, provider abstractions, artifact model, and rendering contract should be sound enough to survive into later versions. What stays intentionally small is product scope: one creator, one content format, manual publishing, local infrastructure, and free/low-cost hosted AI providers.

> **Core architecture principle: Agentic creativity ends at an approved StorySpec/VisualBible boundary. Production state, retries, file management, job execution, rendering, publishing state, and metrics remain deterministic.**

## 2. Product Vision and Content Positioning

Build a small AI-assisted story studio where creative judgment is separated from repetitive production work. Initially the AI system supplies most ideation and drafting while the creator supplies taste and approval. If the format validates, human writers and creative friends can contribute premises, characters, plot beats, dialogue, and twists while the studio handles production.

### 2.1 V1 Niche

> **Viewer promise: Give us roughly one minute and we will show you a strange, cinematic story with a strong hook and a satisfying payoff.**

V1 explores three closely related sub-genres without changing the overall channel identity:

- Mystery / suspense — immediate anomaly, escalating clues, reveal.
- Sci-fi / what-if — one speculative rule, human consequence, twist.
- Psychological / emotional twist — apparent meaning changes at the end.

**Recommended initial mix:** ~50% mystery/suspense, ~30% sci-fi/what-if, ~20% psychological/emotional. The mix is a test, not a permanent brand constraint.

### 2.2 What the Niche Is Not

- Not 'AI videos' — AI is production infrastructure, not the audience proposition.
- Not generic faceless automation, scraped Reddit stories, motivational clips, or mass-produced news summaries.
- Not a random multi-genre channel that alternates between mythology, comedy, tech, horror, and motivation.
- Not an attempt to maximize upload count. The content must feel authored and intentionally directed.

## 3. V1 Goals and Validation

| Goal | V1 outcome |
| --- | --- |
| End-to-end product | Create a project in the UI and progress through idea → story → visuals → narration → render → final export. |
| Creative quality | Generate many candidate premises, aggressively filter them, and produce stories with strong hooks, escalation, and payoff. |
| Human control | Creator can compare, edit, approve, reject, and regenerate at every expensive/creative boundary. |
| Media workflow | Use free-first stock/generated images, remote TTS, optional motion assets, captions, music/SFX, and deterministic composition. |
| Engineering quality | Async jobs, durable state, provider abstractions, artifact versioning, retries, and clear stage status. |
| Real-world validation | Publish initial videos quickly, then reach ~30 videos before major architecture/product expansion. |
| Cost validation | Keep API spend near zero until the content itself shows signs of traction. |

### 3.1 What Counts as Success

- The system produces publishable videos without manual timeline editing.
- A new story can reuse the same application and rendering pipeline without code changes.
- Individual scenes, narration, or story versions can be regenerated without restarting the project.
- At least 10–15 real videos are published; the broader experiment continues toward ~30.
- We can identify which hook structures, genres, endings, and visual treatments correlate with stronger audience response.

## 4. Explicit V1 Non-Goals

- Autonomous publishing to YouTube/Instagram.
- Multi-tenant creator SaaS, billing, organizations, permissions, or subscriptions.
- A full NLE/video editor or Canva/CapCut replacement.
- Self-hosted AI inference or GPU infrastructure.
- Kubernetes, Prefect, distributed workflow engines, or graph-runtime infrastructure.
- Fine-tuning/custom model training.
- Large-scale character/lore memory across hundreds of episodes.
- Automatic trend scraping from many platforms.
- Advanced analytics/recommendation agents.
- Guaranteed recurring fictional universe in the first content batch.
- Monetization infrastructure; monetization is validated through platforms/audience first.

## 5. System Architecture

```
                         ┌──────────────────────────┐
                         │       Next.js Studio      │
                         │ ideas • story • scenes    │
                         │ preview • approvals       │
                         └────────────┬─────────────┘
                                      │ REST/SSE
                                      ▼
                         ┌──────────────────────────┐
                         │         FastAPI          │
                         │ domain/API/application   │
                         └────────┬─────────┬───────┘
                                  │         │
                              Postgres    Redis
                                  │         │
                                  │       Celery
                                  │         │
                                  │         ▼
                                  │  ┌────────────────┐
                                  │  │ Worker Runtime │
                                  │  └───────┬────────┘
                                  │          │
                  ┌───────────────┼──────────┼────────────────┐
                  ▼               ▼          ▼                ▼
           Creative Deep       Media      Caption         Renderer
              Agent          Providers   Alignment     Remotion/FFmpeg
           NIM / Groq       CF/Pexels/    Groq/CF
                             Gemini
                  │               │          │                │
                  └───────────────┴──────────┴────────────────┘
                                      │
                                      ▼
                              Artifact Storage
                         local filesystem in V1
                         GCS/S3-compatible later
```

### 5.1 Why This Is Not Overengineering

A frontend, durable database, async worker, and provider layer are justified because the workflow is inherently interactive and long-running. The creator needs to compare alternatives, approve story versions, inspect multiple scene assets, regenerate individual failures, and monitor video-generation jobs that can outlive an HTTP request.

- Postgres is the source of truth for project/job state.
- Redis/Celery handles asynchronous execution but never owns durable workflow state.
- Local filesystem stores binary artifacts in V1; storage can move to GCS/S3 later without changing domain contracts.
- The application remains deployable later because web/API/worker boundaries already exist.

## 6. Frontend Product

**Stack:** Next.js + TypeScript + a small component system. No separate design system project is required in V1.

| Screen | Purpose | Required V1 interactions |
| --- | --- | --- |
| Projects | Entry point and progress overview | Create project; view stage/status; open project. |
| Ideation | Compare generated premises | Generate batch; sort by score; inspect rationale; choose/shortlist. |
| Story Studio | Develop the selected story | Read/edit hook and narration; inspect critic notes; regenerate/revise; approve. |
| Visual Bible | Lock visual identity | Edit style; character descriptions; approve reference images. |
| Storyboard | Control scene production | Edit scene prompt/duration; choose stock vs generated image; regenerate; select asset; animate optional scene. |
| Audio | Narration review | Generate/re-generate voice; playback; approve; view caption alignment. |
| Render | Preview/finalize video | Start preview render; playback; see stage failures; render final. |
| Metrics | Record learning | Enter publication URL/date and basic performance snapshots manually. |

### 6.1 UX Principles

- Never hide expensive generation behind a single opaque 'Make Video' button.
- Show the creator what was generated, why it was selected, and what can be regenerated.
- Every generated artifact is versioned; selecting a new version does not delete previous candidates.
- A failed asset/job should expose a retryable error, not reset the whole project.
- Approval states are explicit and auditable.

## 7. Backend and Worker Architecture

**Backend stack:** Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, Redis, Celery.

### 7.1 Service Responsibilities

| Component | Owns | Does not own |
| --- | --- | --- |
| FastAPI | HTTP APIs, validation, auth placeholder, state transitions, job creation, read models | Long-running AI/media generation |
| Celery worker | Execute generation/render tasks; bounded retries; stage progress | Durable project truth |
| Postgres | Projects, versions, approvals, jobs, providers, publications, metrics | Binary image/audio/video blobs |
| Redis | Celery broker/result coordination and transient cache | Permanent workflow state |
| Filesystem | Generated images, audio, stock downloads, captions, preview/final renders | Business state |
| Remotion package | Deterministic frame composition and final timeline | Creative decisions |

### 7.2 API Shape

```http
POST   /api/v1/projects
GET    /api/v1/projects
GET    /api/v1/projects/{project_id}

POST   /api/v1/projects/{id}/ideas:generate
POST   /api/v1/projects/{id}/ideas/{idea_id}:select

POST   /api/v1/projects/{id}/story:generate
POST   /api/v1/projects/{id}/story:revise
POST   /api/v1/projects/{id}/story/{version_id}:approve

POST   /api/v1/projects/{id}/visual-bible:generate
PATCH  /api/v1/projects/{id}/visual-bible
POST   /api/v1/projects/{id}/storyboard:generate

POST   /api/v1/scenes/{scene_id}/assets:generate
POST   /api/v1/scenes/{scene_id}/assets:search-stock
POST   /api/v1/scenes/{scene_id}/assets/{asset_id}:select

POST   /api/v1/projects/{id}/narration:generate
POST   /api/v1/projects/{id}/captions:align

POST   /api/v1/projects/{id}/renders:preview
POST   /api/v1/projects/{id}/renders:final

GET    /api/v1/jobs/{job_id}
GET    /api/v1/projects/{id}/events      # SSE progress stream

POST   /api/v1/projects/{id}/publications
POST   /api/v1/publications/{id}/metrics
```

## 8. Creative Deep Agent

The initial creative stage is intentionally agentic because creativity/idea quality is the largest V1 uncertainty. Use one bounded Creative Director deep agent with specialized subagents. The deep agent explores broadly but must produce typed artifacts.

```
CreativeDirector
    │
    ├── IdeaExplorer
    │     └── broad premise generation + variation
    │
    ├── StoryWriter
    │     └── hook + narration + alternate endings
    │
    └── StoryCritic
          └── pacing + predictability + logic + originality + visual potential

                     ↓
               CreativePackage
                     ↓
                HUMAN GATE
                     ↓
                 StorySpec
```

### 8.1 Creative Agent Responsibilities

- Generate a broad batch (e.g. 20–30) of original concepts rather than a single answer.
- Score candidates on hook strength, novelty, emotional pull, twist/payoff potential, visual potential, and 45–60 second fit.
- Develop top candidates into scripts and alternate endings.
- Critique predictability, logical gaps, exposition, pacing, generic AI phrasing, and derivative concepts.
- Return structured outputs only; the application owns persistence and workflow state.

### 8.2 Hard Boundary

> **The Deep Agent must not own: Celery retries, DB writes outside explicit tools, asset filesystem layout, render scheduling, caption calculations, publication, or workflow completion. Those are deterministic application concerns.**

## 9. LLM / Agent Model Strategy

All model inference is remote. NVIDIA NIM is the preferred experimentation platform for the creative agent, with Groq as a strong free-tier fallback and benchmark. Model selection is configuration and can change without changing domain logic.

| Use | V1 provider | Fallback / later | Notes |
| --- | --- | --- | --- |
| Creative Director | NVIDIA NIM hosted API model selected by bake-off | Groq GPT-OSS 120B | Needs reasoning/tool use and strong prose. |
| High-volume ideation/scoring | NVIDIA NIM or Groq GPT-OSS 20B | Other open models | Cheap/fast batch generation. |
| Structured story output | NIM / GPT-OSS 120B | Provider swap | Pydantic/JSON schema enforced. |
| Safety/originality checks | LLM rubric + human review | Dedicated classifiers later | Do not treat automated originality judgment as proof. |

### 9.1 Model Bake-Off

Before locking the creative model, run the same 10 prompts through 2–3 viable hosted models and blind-score:

- Hook
- Originality
- Narrative coherence
- Twist/payoff
- Emotional pull
- Visual potential
- Amount of editing required

## 10. Free-First Media Provider Strategy

> **V1 cost rule: Do not weaken the architecture to save money. Use provider abstractions so the same product can run on free validation providers now and higher-quality paid providers after evidence.**

| Capability | Free-first V1 | Paid/scale option | Decision |
| --- | --- | --- | --- |
| Generated images | Cloudflare Workers AI FLUX.1 Schnell | Gemini 3.1 Flash Image / stronger FLUX/Qwen provider | Primary free generated-image lane. |
| Stock photos/video | Pexels API | Keep Pexels + optional premium library | Prefer stock when a scene does not need unique fiction-specific imagery. |
| Narration | Gemini 3.1 Flash TTS free tier where available for account/project | Same / ElevenLabs benchmark | Expressive remote narration; no local TTS. |
| Caption alignment | Groq Whisper Large V3 Turbo free-plan quota | Same paid endpoint | Word timestamps for captions. |
| Music/SFX | Pixabay/local curated library | Licensed premium/custom music later | Cache permitted assets and provenance. |
| AI video | Disabled by default in FREE_V1 | Veo 3.1 Lite/Fast; Wan/LTX through hosted providers | Not a blocker for validation. |
| HF Inference Providers | Optional experimentation only | Provider-routing convenience | Free-user credits are too small to be the core free strategy. |

### 10.1 Image Selection Policy

```
For each scene:

1. Can a stock clip/image communicate the scene without losing story specificity?
      YES → search Pexels and shortlist candidates
      NO  → generated image

2. Does the scene require a recurring character?
      YES → use VisualBible + approved reference assets
      NO  → independent prompt is acceptable

3. Does true generated motion materially improve the scene?
      YES → optional paid video generation after validation
      NO  → Remotion camera/motion treatment
```

### 10.2 Free Provider Caveats

- Free tiers and quotas are not SLAs. Provider adapters must expose quota/rate-limit failures cleanly.
- NVIDIA hosted catalog access is suitable for prototyping; production guarantees may require a paid/enterprise arrangement later.
- Hugging Face free-user routed inference credit is small, so HF should not be treated as the primary free media backend.
- Gemini preview TTS may require retry handling and can change; wrap it behind TTSProvider.
- Cloudflare free Workers AI quota resets daily; generation should surface quota exhaustion rather than silently switching quality.
- Pexels usage must comply with API terms and attribution/linking requirements; cache searches/downloads responsibly.

## 11. Provider Abstractions

```
LLMProvider
  generate(...)
  generate_structured(schema, ...)
  invoke_tools(...)

ImageProvider
  generate(prompt, references?, aspect_ratio?, seed?)
  edit(image, prompt, references?)

StockMediaProvider
  search_photos(query, orientation, count)
  search_videos(query, orientation, count)
  download(asset)

TTSProvider
  synthesize(text, voice, direction) -> AudioArtifact

TranscriptionProvider
  align(audio) -> WordTiming[]

VideoGenerationProvider
  generate(prompt, first_frame?, references?, duration?)

ArtifactStorage
  put/read/delete
  local://... in V1
  gs://... later
```

Provider-specific request/response objects must not leak into domain entities. Normalize them into internal artifact and generation-result types.

## 12. Core Domain Contracts

### 12.1 StorySpec

```json
{
  "id": "story_001",
  "working_title": "The Last Message",
  "genre": "mystery",
  "target_duration_sec": 54,
  "premise": "...",
  "hook": "...",
  "narration": "...",
  "ending_type": "twist",
  "tone": ["cinematic", "tense", "intimate"],
  "scenes": [
    {
      "id": "scene_01",
      "order": 1,
      "duration_sec": 5.2,
      "narration": "...",
      "visual_intent": "...",
      "asset_strategy": "generated_image",
      "visual_prompt": "...",
      "motion": "slow_push_in",
      "caption_emphasis": ["..."],
      "sfx": ["phone_buzz"]
    }
  ]
}
```

### 12.2 VisualBible

```json
{
  "style": {
    "description": "cinematic near-realism, low-key lighting",
    "palette": ["charcoal", "cold blue", "warm practical lights"],
    "camera_language": ["close-ups", "shallow depth of field"]
  },
  "characters": [
    {
      "id": "char_01",
      "role": "protagonist",
      "appearance": "...",
      "clothing": "...",
      "reference_asset_ids": ["asset_ref_1"]
    }
  ],
  "locations": [
    {
      "id": "loc_01",
      "description": "small apartment bedroom at night",
      "continuity_notes": "..."
    }
  ]
}
```

### 12.3 GenerationJob

```json
{
  "id": "...",
  "project_id": "...",
  "type": "scene_image_generation",
  "status": "queued | running | succeeded | failed | cancelled",
  "provider": "cloudflare",
  "model": "@cf/black-forest-labs/flux-1-schnell",
  "attempt": 1,
  "max_attempts": 3,
  "progress": 0.0,
  "error_code": null,
  "error_message": null,
  "created_at": "...",
  "started_at": null,
  "completed_at": null
}
```

## 13. Data Model

| Entity | Key fields / relationship |
| --- | --- |
| Project | id, title, status, niche/genre, current_stage, timestamps |
| IdeaCandidate | project_id, premise, hook, scores, rationale, source_run |
| StoryVersion | project_id, version, StorySpec, model/provider, approval status |
| VisualBibleVersion | project_id, version, JSON payload, approval status |
| Scene | project_id, story_version_id, order, narration, duration, strategy |
| Asset | scene_id/project_id, type, provider, model, local URI, prompt, metadata, status |
| AssetSelection | scene_id, selected_asset_id, selected_at |
| NarrationVersion | project_id, provider/model/voice, audio URI, duration, approval |
| CaptionTrack | narration_version_id, word timings, SRT/JSON URI |
| GenerationJob | project_id, type, provider/model, status, attempt, error, timestamps |
| Render | project_id, story version, preview/final, URI, status, duration |
| Publication | project_id, platform, URL/external id, published_at |
| MetricSnapshot | publication_id, captured_at, views, retention, likes, comments, shares/saves, followers gained |

## 14. End-to-End Product Flow

1. Create a new Story Project and choose broad genre or let the Creative Director explore the V1 mix.
1. Creative Director generates and evaluates a large premise batch.
1. UI presents top candidates plus scores/rationale; creator selects one.
1. Deep Agent develops story, runs critic, produces revisions/alternate ending if useful.
1. Creator edits/approves the StorySpec.
1. System generates VisualBible: style, recurring character descriptions, locations, reference assets.
1. Creator approves visual direction/reference assets.
1. Storyboard is created from StorySpec with scene durations and asset strategies.
1. Scene media is produced asynchronously: Pexels search and/or Cloudflare-generated images, preferably in parallel.
1. Creator reviews/selects/regenerates scene assets.
1. Remote TTS generates narration; creator previews and approves.
1. Whisper alignment produces word timings and caption track.
1. Optional video generation may be manually enabled only for selected scenes when paid credits are allowed.
1. Remotion deterministically composes media, captions, motion, narration, music, and SFX into preview.
1. Creator reviews preview and fixes only affected stages/assets.
1. Final render is exported.
1. Creator publishes manually and records publication metadata/metrics.

## 15. Rendering Architecture

Remotion is the deterministic production engine. Generative models supply content assets; they do not control frame-level editing or timeline mechanics.

| Concern | Owned by renderer |
| --- | --- |
| Canvas | 9:16, 1080×1920, 30 fps default |
| Timeline | Exact scene start/end frames derived from StorySpec |
| Image motion | Push/pan/zoom/parallax-like treatments and restrained effects |
| Video clips | Trim/fit/crop/transition generated or stock motion assets |
| Captions | Word/phrase timing, emphasis, safe-area layout, style |
| Audio | Narration, background music ducking, SFX placement, normalization |
| Transitions | Small reusable set; no random effects |
| Brand | Typography, end treatment, subtle repeatable visual identity |
| Output | Preview and final H.264 MP4 |

## 16. Workflow State, Retries, and Idempotency

- Every long-running action creates a GenerationJob row before execution.
- Jobs use idempotency keys derived from project/stage/version/request parameters where appropriate.
- A retry creates/updates attempts without deleting successful upstream artifacts.
- Provider rate-limit/quota errors are distinguished from invalid prompts, moderation errors, and transient server failures.
- User-triggered regeneration creates a new asset version; it does not overwrite the currently selected asset.
- Stage completion is derived from durable application state, not Celery result backend state.
- The UI receives progress using server-sent events (SSE) or bounded polling; V1 should prefer SSE unless implementation friction is material.

## 17. Repository Structure

```
story-studio/
├── apps/
│   └── web/                       # Next.js / TypeScript
│
├── services/
│   ├── api/                       # FastAPI application
│   └── worker/                    # Celery entrypoints
│
├── studio/
│   ├── domain/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── application/
│   │   ├── commands/
│   │   ├── queries/
│   │   └── workflows/
│   ├── agents/
│   │   └── creative_director/
│   ├── providers/
│   │   ├── llm/
│   │   ├── image/
│   │   ├── stock/
│   │   ├── tts/
│   │   ├── transcription/
│   │   └── video/
│   ├── persistence/
│   └── storage/
│
├── packages/
│   └── renderer/                  # Remotion / React
│
├── prompts/
├── migrations/
├── docker-compose.yml
├── .env.example
├── tests/
└── engg-work/
```

## 18. Environment / Provider Profiles

### 18.1 FREE_V1 Profile

```env
APP_MODE=validation

LLM_PRIMARY=nvidia_nim
LLM_FALLBACK=groq

IMAGE_PRIMARY=cloudflare_flux_schnell
STOCK_PRIMARY=pexels

TTS_PRIMARY=gemini_tts
TRANSCRIPTION_PRIMARY=groq_whisper

VIDEO_GENERATION_ENABLED=false

ARTIFACT_STORAGE=local
DATABASE_URL=postgresql://...
REDIS_URL=redis://...

PUBLISHING_MODE=manual
```

### 18.2 Future Paid Profile

```env
APP_MODE=production

LLM_PRIMARY=<winning production provider>

IMAGE_PRIMARY=gemini_image
IMAGE_FALLBACK=<hosted FLUX/Qwen>

TTS_PRIMARY=gemini_tts
TTS_FALLBACK=elevenlabs

VIDEO_GENERATION_ENABLED=true
VIDEO_PRIMARY=veo_3_1_lite
VIDEO_FALLBACK=<hosted Wan/LTX>

ARTIFACT_STORAGE=gcs
PUBLISHING_MODE=manual_or_controlled
```

## 19. Quality Gates

### 19.1 Story Gate

- Hook creates unanswered curiosity within the first 1–2 seconds.
- Premise is explainable in one sentence and not overloaded with subplots.
- Every beat either reveals information, increases tension/emotion, or changes interpretation.
- Ending pays off setup; twist is not random.
- Narration avoids exposition-heavy or generic AI phrasing.
- Concept does not intentionally copy recognizable characters, dialogue, plots, or distinctive elements from an existing work.

### 19.2 Visual Gate

- Recurring character appearance is acceptably consistent across chosen assets.
- No obvious anatomical/visual generation failures that distract from the story.
- Stock media matches story context and does not create misleading real-person implications.
- Visual variety is sufficient to avoid slideshow fatigue.
- The first frame is visually strong enough to support the hook.

### 19.3 Final Video Gate

- Narration/captions are synchronized.
- Captions are readable on a phone and respect safe areas.
- No dead air, accidental blank frames, broken crops, or missing assets.
- Music/SFX support rather than overpower narration.
- Pacing is tight enough for short-form consumption.
- Creator explicitly approves final preview before export/publishing.

## 20. Content Safety, Rights, and Provenance

- All stories should be original or sufficiently transformed original concepts; do not scrape and lightly rewrite copyrighted stories.
- Store asset source/provider, generation prompt, external source URL/id, and license/provenance metadata when available.
- Pexels/Pixabay assets must be used according to their current platform terms; avoid misleading use of identifiable people/brands.
- Music/SFX library entries should record source and license information.
- Realistic synthetic media must be disclosed when platform rules require it.
- Do not rely on an LLM originality score as legal clearance; human editorial review remains required.

## 21. Validation Metrics

| Metric | Why it matters |
| --- | --- |
| Viewed vs swiped / opening retention | Tests the hook + first frame. |
| Average % viewed / completion | Primary measure of story retention. |
| Rewatches | Especially important for twist/reveal formats. |
| Shares / saves | Strong signal of memorable content. |
| Comments | Shows emotion, theories, confusion, or demand for continuation. |
| Followers/subscribers gained per video | Measures audience conversion. |
| Production time per video | Determines whether weekend cadence is sustainable. |
| API/provider cost per video | Ensures quality improvements remain economically sensible. |
| Regenerations per stage | Shows where model/provider quality is wasting creator time. |

### 21.1 Decision Rule Around ~30 Videos

| Observed signal | Action |
| --- | --- |
| One genre repeatedly wins | Narrow channel positioning around it. |
| One hook/ending structure wins | Create reusable creative heuristics, not copy-paste stories. |
| Good retention but slow production | Automate the repeated production bottleneck. |
| Strong visual response but weak stories | Invest in creative model/prompts/human writing, not more renderer effects. |
| Good stories but poor first-second retention | Improve packaging/first frame/hook delivery. |
| No meaningful audience response after repeated iteration | Pivot format/niche or stop; do not solve with infrastructure. |

## 22. Implementation Plan

> **Delivery philosophy: Build the correct product boundaries now, but reach real content quickly. 'Fast' means fewer features, not weak engineering.**

### Weekend 1 — Product Skeleton + Creative Pipeline

| Saturday | Sunday |
| --- | --- |
| Monorepo; Docker Compose; Postgres/Redis; FastAPI project/domain skeleton; Next.js project shell; StorySpec/Idea/Job schema; provider interfaces. | Creative Director Deep Agent; NIM/Groq adapters; ideation + scoring + story/critic flow; UI for projects/ideas/story; persistence + approval flow. |

**Exit:** A user can create a project in the web UI, generate/compare ideas, develop a story, and approve a durable StorySpec.

### Weekend 2 — Media + First Published Videos

| Saturday | Sunday |
| --- | --- |
| VisualBible/storyboard; Cloudflare image provider; Pexels search/download; Gemini TTS; Whisper alignment; async job UI/SSE. | Remotion template; scene review/regeneration; narration/caption integration; music/SFX; preview/final render; produce several videos and publish initial batch manually. |

**Exit:** StorySpec → approved media → publishable 1080×1920 MP4 works end-to-end from the product UI.

### Weekend 3+ — Content First

**Default allocation:** ~20% engineering / ~80% producing and learning from actual content.

- Fix only repeated or high-impact workflow defects.
- Add paid video generation only if lack of true motion is clearly limiting content quality.
- Do not add cloud deployment until local execution is materially inconvenient or collaboration requires it.
- Do not add creator collaboration UX until creative friends are actually joining.

## 23. Testing and Engineering Quality

| Layer | V1 tests |
| --- | --- |
| Domain | StorySpec/VisualBible validation; legal state transitions; score ranges; scene durations. |
| Provider adapters | Contract tests with mocked HTTP; response normalization; quota/rate-limit/moderation/transient failure mapping. |
| Agent | Structured-output parsing; bounded iteration; evaluation fixtures for premises/stories. |
| Persistence | Migrations; selected asset/version durability; job transitions. |
| Workers | Idempotency; retry policy; resume without regenerating successful upstream stages. |
| Renderer | Fixture StorySpec renders successfully; captions/audio/assets present; duration tolerance. |
| API | Happy paths + invalid transitions + job lifecycle. |
| Frontend | Critical approval/regenerate/render flows; meaningful loading/error states. |

## 24. Observability

- Structured logs with project_id, job_id, provider, model, stage, attempt, latency, and outcome.
- Persist provider/model used for every generated artifact.
- Track approximate usage/cost metadata where providers expose it.
- Track regeneration count and creator rejection reasons where feasible.
- A basic internal job timeline in the UI is sufficient; no observability SaaS is required for V1.

## 25. Key Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Stories feel generic | Generate broadly; use critic; human selection; later add human writers. Do not mask weak writing with visual effects. |
| Free provider quality is inconsistent | Provider interfaces + manual regeneration + ability to upgrade one stage without architecture changes. |
| Character consistency is poor | VisualBible/reference assets; minimize number of characters; upgrade image provider after validation. |
| Stock footage makes fiction feel generic | Use only where semantically neutral; generate story-specific visuals for key beats. |
| Media jobs fail/rate-limit | Async durable jobs, classified errors, bounded retries, cached successful artifacts. |
| Engineering consumes weekends | Definition of Done tied to published videos; 20/80 engineering/content rule after end-to-end works. |
| Content becomes repetitive AI slop | Human gate, original concepts, creative rubric, varied visual/structural execution. |
| Free tiers change | Treat providers as replaceable infrastructure; never hard-code business logic to one vendor. |

## 26. V1 Definition of Done

- Next.js frontend supports project, ideation, story approval, storyboard/media review, narration, render, and metrics workflows.
- FastAPI/Postgres application persists all project and version state.
- Celery worker executes long-running generation/render jobs with durable status and bounded retries.
- Creative Deep Agent produces typed candidate/story artifacts using NVIDIA NIM with Groq fallback.
- Cloudflare generated images and Pexels stock media are integrated behind provider interfaces.
- Remote TTS and caption alignment are integrated; no model inference runs locally.
- Remotion produces a consistent vertical preview/final render from approved artifacts.
- Individual story/media stages can be regenerated without destroying prior versions.
- Publishing remains manual and gated by final human approval.
- Initial real videos are live, and the project is collecting content performance + production metrics.

## 27. Post-Validation Roadmap

| Phase | Additions | Trigger |
| --- | --- | --- |
| V1.1 Quality | Nano Banana/stronger image provider; selective Veo/Wan/LTX; better visual continuity; premium voice benchmark | Audience signal exists and media quality is a demonstrated bottleneck. |
| V1.2 Analytics | Automatic platform metric ingestion; format/genre analysis | Enough content exists for analytics to affect decisions. |
| V2 Creative Studio | Contributor accounts/brief intake; human writers; story comments/approvals | Creative friends actively join. |
| V2 Serialized IP | Character bible, lore, recurring world memory, episode continuity | Audience responds to recurring characters/worlds. |
| Scale Infra | GCS/object storage, managed Postgres/Redis, cloud workers, deployment | Collaboration/volume/reliability requires it. |
| Controlled Publishing | Platform API integrations, scheduling, approval policies | Manual publishing becomes a repeated bottleneck. |

### 27.1 Future Human Creative Workflow

```
Creative friend / writer
        │
        ▼
Creative brief
(premise • characters • beats • twist • dialogue notes)
        │
        ▼
AI-assisted expansion / variants
        │
   HUMAN CREATIVE APPROVAL
        │
        ▼
StorySpec + VisualBible
        │
        ▼
Existing production pipeline
storyboard → assets → voice → captions → render
        │
    FINAL APPROVAL
        │
        ▼
Publish + audience feedback
```

## 28. Decisions Locked for V1

- Niche: cinematic micro-fiction with high-concept hooks and payoff/twist endings.
- Primary V1 sub-genres: mystery/suspense, sci-fi/what-if, psychological/emotional twist.
- Creative front half: one bounded Deep Agent with subagents.
- NVIDIA NIM is preferred for creative-agent experimentation; Groq is fallback/benchmark.
- No local model inference on the Mac; all AI inference is remote.
- Next.js frontend + FastAPI backend + Postgres + Redis/Celery from V1.
- Provider abstractions are first-class architecture.
- FREE_V1: Cloudflare FLUX, Pexels, Gemini TTS, Groq Whisper, Pixabay/local media library.
- AI video generation is disabled by default until the content validates or lack of motion is proven to be a quality bottleneck.
- Remotion/FFmpeg own deterministic rendering.
- Human approvals are mandatory before story production and final publishing.
- Publishing is manual in V1.
- Local app infrastructure is acceptable; cloud deployment is deferred.

## 29. Open Decisions for Initial Engineering Spike

- Which exact NVIDIA NIM model wins the creative bake-off.
- Whether the Deep Agent uses LangChain Deep Agents directly or a narrower custom agent wrapper after testing tool/model compatibility.
- Exact frontend component library.
- Whether SSE or polling is simpler for V1 job progress; SSE is preferred.
- Which Gemini TTS voice/direction produces the strongest cinematic narration.
- Exact caption visual style and Remotion motion presets.
- Final channel/brand name.

## 30. Current Provider Facts and References

Provider availability, pricing, free quotas, and preview-model status can change. The application must treat these as configuration. The following official sources were checked while updating this PRD (15 August 2026).

**NVIDIA NIM LLM docs:** https://docs.nvidia.com/nim/large-language-models/latest/get-started/index.html

**NVIDIA NIM overview:** https://docs.nvidia.com/nim/

**Groq rate limits:** https://console.groq.com/docs/rate-limits

**Groq GPT-OSS 120B:** https://console.groq.com/docs/model/openai/gpt-oss-120b

**Groq Whisper:** https://console.groq.com/docs/speech-to-text

**Cloudflare Workers AI pricing:** https://developers.cloudflare.com/workers-ai/platform/pricing/

**Cloudflare FLUX.1 Schnell:** https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/

**Gemini TTS:** https://ai.google.dev/gemini-api/docs/speech-generation

**Gemini API pricing / Veo:** https://ai.google.dev/gemini-api/docs/pricing

**Gemini deprecations:** https://ai.google.dev/gemini-api/docs/deprecations

**Hugging Face Inference Providers pricing:** https://huggingface.co/docs/inference-providers/en/pricing

**Hugging Face text-to-image:** https://huggingface.co/docs/inference-providers/en/tasks/text-to-image

**Hugging Face text-to-video:** https://huggingface.co/docs/inference-providers/en/tasks/text-to-video

**Pexels API:** https://www.pexels.com/api/documentation/

**Pixabay Content License:** https://pixabay.com/service/license-summary/

## 31. Product Principle

> **Build durable boundaries; buy quality only after evidence. V1 should be a real product, not a script pile. But the product exists to publish and learn. We keep architecture clean, provider-independent, and async where necessary while deliberately delaying expensive media inference, cloud infrastructure, multi-user features, and autonomy that the validation does not require.**

---

## 32. Codex Implementation Guidance

Treat this PRD as the product source of truth. During implementation:

- preserve the locked V1 decisions unless a concrete technical constraint invalidates one;
- verify current external-provider model IDs, quotas, pricing, deprecations, and API contracts before implementing provider adapters;
- keep provider-specific types behind the provider interfaces;
- keep AI/agent decisions out of deterministic workflow/state/rendering concerns;
- prefer the smallest implementation that satisfies the defined V1 contract;
- do not add V2 or scale features while implementing V1;
- create an implementation plan and dependency-aware todo list before coding;
- flag any PRD ambiguity that materially affects architecture or behavior as an explicit decision rather than silently inventing scope.
