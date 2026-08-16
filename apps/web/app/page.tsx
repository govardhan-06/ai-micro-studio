"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type ScoreMap = {
  hook: number;
  novelty: number;
  emotional_pull: number;
  twist_payoff: number;
  visual_potential: number;
  short_form_fit: number;
};

type Project = {
  id: string;
  title: string;
  status: string;
  genre: string | null;
  current_stage: string;
  created_at: string;
  updated_at: string;
};

type Idea = {
  id: string;
  project_id: string;
  premise: string;
  hook: string;
  scores: ScoreMap;
  rationale: string;
  source_run: string;
  is_selected: boolean;
  created_at: string;
  updated_at: string;
};

type Scene = {
  id: string;
  order: number;
  duration_sec: number;
  narration: string;
  visual_intent: string;
  asset_strategy: string;
  visual_prompt: string;
  motion: string;
  caption_emphasis: string[];
  sfx: string[];
};

type StorySpec = {
  id: string;
  working_title: string;
  genre: string;
  target_duration_sec: number;
  premise: string;
  hook: string;
  narration: string;
  ending_type: string;
  tone: string[];
  scenes: Scene[];
};

type Story = {
  id: string;
  project_id: string;
  version: number;
  story: StorySpec;
  critique: {
    summary: string;
    strengths: string[];
    issues: string[];
    scores: Record<string, number>;
    recommendation: "accept" | "revise";
  } | null;
  provider: string | null;
  model: string | null;
  rejection_reason: string | null;
  approval_status: string;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
};

type VisualBible = {
  style: { lighting: string; lens_language: string; render_style: string; aspect_ratio: string; description?: string; palette: string[]; camera_language: string[] };
  characters: { id: string; role: string; age: string; presentation: string; ethnicity: string; face: string; hair: string; build: string; clothing: string; accessories: string[]; immutable_traits: string[]; appearance?: string; reference_asset_ids: string[] }[];
  locations: { id: string; name: string; architecture_geometry: string; time: string; weather: string; lighting: string; persistent_props: string[]; immutable_traits: string[]; description?: string; continuity_notes?: string; reference_asset_ids: string[] }[];
};

type VisualBibleVersion = {
  id: string;
  project_id: string;
  version: number;
  visual_bible: VisualBible;
  reference_assets: Asset[];
  approval_status: string;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
};

type Asset = {
  id: string;
  project_id: string;
  scene_id: string | null;
  asset_type: string;
  provider: string | null;
  model: string | null;
  local_uri: string;
  content_url: string;
  prompt: string | null;
  metadata: Record<string, any>;
  status: string;
  created_at: string;
  updated_at: string;
};

type StoryboardScene = {
  id: string;
  project_id: string;
  story_version_id: string;
  order: number;
  narration: string;
  duration_sec: number;
  asset_strategy: string;
  visual_intent: string | null;
  visual_prompt: string | null;
  motion: string | null;
  caption_emphasis: string[];
  sfx: string[];
  shot_spec: ShotSpec | null;
  assets: Asset[];
  selected_asset_id: string | null;
  created_at: string;
  updated_at: string;
};

type ShotSpec = {
  location_id: string;
  character_ids: string[];
  action: string;
  expression: string;
  composition: string;
  camera: string;
  temporary_props: string[];
  lighting: string;
  continuity_source: string[];
  readable_text_metadata: { requested: boolean; text: string | null; surface: string | null; placement: string | null };
  text_overlay: { text: string; x: number; y: number; font_size: number; color: string; start_sec: number; end_sec: number | null } | null;
};

type CaptionTrack = {
  id: string;
  narration_version_id: string;
  word_timings: { word: string; start_sec: number; end_sec: number }[];
  srt_url: string | null;
  json_url: string | null;
  created_at: string;
  updated_at: string;
};

type Narration = {
  id: string;
  project_id: string;
  version: number;
  provider: string;
  model: string | null;
  voice: string | null;
  audio_url: string;
  duration_sec: number;
  approval_status: string;
  approved_at: string | null;
  caption_track: CaptionTrack | null;
  created_at: string;
  updated_at: string;
};

type Render = {
  id: string;
  project_id: string;
  story_version_id: string | null;
  render_type: "preview" | "final";
  uri: string | null;
  content_url: string | null;
  status: Job["status"];
  duration_sec: number | null;
  preview_approved_at: string | null;
  created_at: string;
  updated_at: string;
};

type MetricSnapshot = {
  id: string;
  publication_id: string;
  captured_at: string;
  views: number;
  retention: number | null;
  likes: number;
  comments: number;
  shares_saves: number;
  followers_gained: number;
  created_at: string;
  updated_at: string;
};

type Publication = {
  id: string;
  project_id: string;
  platform: string;
  url: string | null;
  external_id: string | null;
  published_at: string | null;
  metrics: MetricSnapshot[];
  created_at: string;
  updated_at: string;
};

type Job = {
  id: string;
  project_id: string;
  type: string;
  stage: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  provider: string | null;
  model: string | null;
  attempt: number;
  max_attempts: number;
  progress: number;
  idempotency_key: string;
  latency_ms: number | null;
  outcome: string | null;
  usage: Record<string, unknown> | null;
  cost_usd: number | null;
  regeneration_count: number;
  timeline: {
    occurred_at: string;
    project_id: string;
    job_id: string;
    provider: string | null;
    model: string | null;
    stage: string;
    attempt: number;
    status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
    outcome: string;
    latency_ms: number | null;
    usage: Record<string, unknown> | null;
    cost_usd: number | null;
    regeneration_count: number;
    error_code: string | null;
    error_message: string | null;
  }[];
  error_code: string | null;
  error_message: string | null;
};

type Workspace = {
  project: Project;
  ideas: Idea[];
  stories: Story[];
  visual_bibles: VisualBibleVersion[];
  scenes: StoryboardScene[];
  narrations: Narration[];
  renders: Render[];
  publications: Publication[];
  jobs: Job[];
};

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message ?? "The studio request failed.");
  }
  return body as T;
}

function score(idea: Idea) {
  return Math.round((Object.values(idea.scores).reduce((sum, value) => sum + value, 0) / 6) * 10) / 10;
}

function jobLabel(job: Job) {
  if (job.type === "story_generation") {
    if (job.status === "running") return "Writing and critiquing selected premise";
    if (job.status === "queued") return "Selected premise queued for story development";
    if (job.status === "succeeded") return "Story draft ready";
  }
  if (job.type === "visual_bible_generation") {
    if (job.status === "running") return "Building visual direction from approved story";
    if (job.status === "queued") return "Visual direction queued";
    if (job.status === "succeeded") return "Visual Bible draft ready";
  }
  if (job.type === "storyboard_generation") {
    if (job.status === "running") return "Deriving storyboard scenes from approved story";
    if (job.status === "queued") return "Storyboard queued";
    if (job.status === "succeeded") return "Storyboard ready";
  }
  if (job.type === "scene_asset_generation") {
    if (job.status === "running") return "Generating scene image";
    if (job.status === "queued") return "Scene image queued";
    if (job.status === "succeeded") return "Scene image candidates ready";
  }
  if (job.type === "scene_stock_search") {
    if (job.status === "running") return "Searching and downloading stock candidates";
    if (job.status === "queued") return "Stock search queued";
    if (job.status === "succeeded") return "Stock candidates ready";
  }
  if (job.type === "narration_generation") {
    if (job.status === "running") return "Generating remote narration audio";
    if (job.status === "queued") return "Narration queued";
    if (job.status === "succeeded") return "Narration audio ready";
  }
  if (job.type === "caption_alignment") {
    if (job.status === "running") return "Aligning words to narration";
    if (job.status === "queued") return "Caption alignment queued";
    if (job.status === "succeeded") return "Caption timings ready for review";
  }
  if (job.type === "render_preview") {
    if (job.status === "running") return "Rendering preview for review";
    if (job.status === "queued") return "Preview render queued";
    if (job.status === "succeeded") return "Preview ready for approval";
  }
  if (job.type === "render_final") {
    if (job.status === "running") return "Exporting final video";
    if (job.status === "queued") return "Final export queued";
    if (job.status === "succeeded") return "Final video ready to publish";
  }
  if (job.status === "failed") return `Failed · attempt ${job.attempt}/${job.max_attempts}`;
  if (job.status === "running") return "Generating creative package";
  if (job.status === "queued") return "Queued for generation";
  return "Generation complete";
}

export default function HomePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState("mystery");
  const [sort, setSort] = useState<"score" | "created">("score");
  const [draftStory, setDraftStory] = useState<Story | null>(null);
  const [draftVisualBible, setDraftVisualBible] = useState<VisualBibleVersion | null>(null);
  const [draftScenes, setDraftScenes] = useState<StoryboardScene[]>([]);
  const [stockType, setStockType] = useState<"photo" | "video">("photo");
  const [publicationPlatform, setPublicationPlatform] = useState("manual");
  const [publicationUrl, setPublicationUrl] = useState("");
  const [publicationDate, setPublicationDate] = useState("");
  const [metricDraft, setMetricDraft] = useState({ views: "", retention: "", likes: "", comments: "", shares_saves: "", followers_gained: "" });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);

  const loadProjects = async () => {
    const next = await api<Project[]>("/api/v1/projects");
    setProjects(next);
    if (!projectId && next[0]) setProjectId(next[0].id);
  };

  const loadWorkspace = async (id: string) => {
    const next = await api<Workspace>(`/api/v1/projects/${id}/workspace`);
    setWorkspace(next);
    setError("");
  };

  useEffect(() => {
    loadProjects().catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!projectId) {
      setWorkspace(null);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await api<Workspace>(`/api/v1/projects/${projectId}/workspace`);
        if (cancelled) return;
        setWorkspace(next);
        if (next.jobs.some((job) => job.status === "queued" || job.status === "running")) {
          timer = window.setTimeout(poll, 1500);
        }
      } catch (reason) {
        if (!cancelled) setError((reason as Error).message);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [projectId, refresh]);

  const latestStory = workspace?.stories[0] ?? null;
  const latestVisualBible = workspace?.visual_bibles[0] ?? null;
  const approvedStory = workspace?.stories.find((story) => story.approval_status === "approved") ?? null;
  const latestPreview = workspace?.renders.find((render) => render.render_type === "preview") ?? null;
  const latestFinal = workspace?.renders.find((render) => render.render_type === "final") ?? null;
  useEffect(() => setDraftStory(latestStory), [latestStory?.id, latestStory?.updated_at, latestStory?.approval_status]);
  useEffect(() => setDraftVisualBible(latestVisualBible), [latestVisualBible?.id, latestVisualBible?.updated_at, latestVisualBible?.approval_status]);
  useEffect(() => {
    setDraftScenes(workspace?.scenes.filter((scene) => scene.story_version_id === approvedStory?.id) ?? []);
  }, [workspace?.scenes, approvedStory?.id]);

  const orderedIdeas = useMemo(() => {
    if (!workspace) return [];
    return [...workspace.ideas].sort((a, b) => (sort === "score" ? score(b) - score(a) : a.created_at.localeCompare(b.created_at)));
  }, [workspace, sort]);

  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy("");
    }
  };

  const createProject = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    await run("create", async () => {
      const project = await api<Project>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), genre: genre || null }),
      });
      setProjects((current) => [project, ...current]);
      setProjectId(project.id);
      setTitle("");
      setNotice("Project created. Start with a creative pass when the brief is ready.");
    });
  };

  const generateIdeas = () => run("generate", async () => {
    if (!workspace) return;
    const job = await api<{ job: Job }>(`/api/v1/projects/${workspace.project.id}/ideas/generate`, {
      method: "POST",
      body: JSON.stringify({ run_key: crypto.randomUUID() }),
    });
    setNotice(job.job.status === "queued" ? "Creative pass queued. This page will update as it runs." : "Creative pass started.");
    setRefresh((value) => value + 1);
  });

  const selectIdea = (ideaId: string) => run("select", async () => {
    if (!workspace) return;
    await api<Idea>(`/api/v1/projects/${workspace.project.id}/ideas/${ideaId}/select`, { method: "POST" });
    await loadWorkspace(workspace.project.id);
    setRefresh((value) => value + 1);
    setNotice("Candidate selected for the next story edit.");
  });

  const saveRevision = () => run("save", async () => {
    if (!workspace || !draftStory) return;
    await api<Story>(`/api/v1/projects/${workspace.project.id}/stories/${draftStory.id}`, {
      method: "PATCH",
      body: JSON.stringify({ story: draftStory.story }),
    });
    await loadWorkspace(workspace.project.id);
    setNotice("New draft version saved. Earlier versions remain available.");
  });

  const approveStory = () => run("approve", async () => {
    if (!workspace || !draftStory) return;
    await api<Story>(`/api/v1/projects/${workspace.project.id}/stories/${draftStory.id}/approve`, { method: "POST" });
    await loadWorkspace(workspace.project.id);
    setNotice("Story approved. Visual direction is ready for the next gate.");
  });

  const generateVisualBible = () => run("visual-bible", async () => {
    if (!workspace) return;
    await api<{ job: Job }>(`/api/v1/projects/${workspace.project.id}/visual-bible/generate`, {
      method: "POST",
      body: JSON.stringify({ run_key: crypto.randomUUID() }),
    });
    setRefresh((value) => value + 1);
    setNotice("Visual Bible generation queued.");
  });

  const generateVisualReferences = () => run("visual-references", async () => {
    if (!workspace) return;
    await api<{ job: Job }>(`/api/v1/projects/${workspace.project.id}/visual-bible/references:generate`, {
      method: "POST",
      body: JSON.stringify({ run_key: crypto.randomUUID() }),
    });
    setRefresh((value) => value + 1);
    setNotice("Canonical character and location references queued.");
  });

  const saveVisualBible = () => run("save-visual-bible", async () => {
    if (!workspace || !draftVisualBible) return;
    await api<VisualBibleVersion>(`/api/v1/projects/${workspace.project.id}/visual-bible`, {
      method: "PATCH",
      body: JSON.stringify({ visual_bible: draftVisualBible.visual_bible }),
    });
    await loadWorkspace(workspace.project.id);
    setNotice("New Visual Bible draft saved. Earlier versions remain available.");
  });

  const approveVisualBible = () => run("approve-visual-bible", async () => {
    if (!workspace || !draftVisualBible) return;
    await api<VisualBibleVersion>(
      `/api/v1/projects/${workspace.project.id}/visual-bible/${draftVisualBible.id}/approve`,
      { method: "POST" },
    );
    await loadWorkspace(workspace.project.id);
    setNotice("Visual direction approved. Derive the editable storyboard when ready.");
  });

  const generateStoryboard = () => run("storyboard", async () => {
    if (!workspace) return;
    await api<{ job: Job }>(`/api/v1/projects/${workspace.project.id}/storyboard/generate`, {
      method: "POST",
      body: JSON.stringify({ run_key: crypto.randomUUID() }),
    });
    setRefresh((value) => value + 1);
    setNotice("Storyboard generation queued.");
  });

  const generateNarration = () => run("narration", async () => {
    if (!workspace || !approvedStory) return;
    await api<{ job: Job }>(`/api/v1/projects/${workspace.project.id}/narration:generate`, {
      method: "POST",
      body: JSON.stringify({
        run_key: crypto.randomUUID(),
        text: approvedStory.story.narration,
        voice: "Kore",
        direction: "Cinematic, intimate short-form narration with clear pacing.",
      }),
    });
    setRefresh((value) => value + 1);
    setNotice("Remote narration queued. Earlier audio versions remain available.");
  });

  const alignCaptions = (narration: Narration) => run(`captions-${narration.id}`, async () => {
    if (!workspace) return;
    await api<{ job: Job }>(`/api/v1/projects/${workspace.project.id}/captions:align`, {
      method: "POST",
      body: JSON.stringify({ run_key: crypto.randomUUID(), narration_version_id: narration.id, language: "en" }),
    });
    setRefresh((value) => value + 1);
    setNotice(`Word alignment queued for narration version ${narration.version}.`);
  });

  const approveNarration = (narration: Narration) => run(`approve-narration-${narration.id}`, async () => {
    if (!workspace) return;
    await api<Narration>(`/api/v1/projects/${workspace.project.id}/narration/${narration.id}/approve`, { method: "POST" });
    await loadWorkspace(workspace.project.id);
    setNotice(`Narration version ${narration.version} approved. Caption alignment remains reviewable below.`);
  });

  const renderPreview = () => run("render-preview", async () => {
    if (!workspace) return;
    await api(`/api/v1/projects/${workspace.project.id}/renders:preview`, {
      method: "POST",
      body: JSON.stringify({ run_key: crypto.randomUUID() }),
    });
    setRefresh((value) => value + 1);
    setNotice("Preview render queued. Review it here before final export.");
  });

  const approvePreview = () => run("approve-preview", async () => {
    if (!workspace || !latestPreview) return;
    await api<Render>(`/api/v1/projects/${workspace.project.id}/renders/${latestPreview.id}/approve-preview`, { method: "POST" });
    await loadWorkspace(workspace.project.id);
    setNotice("Preview approved. Final export is now available.");
  });

  const renderFinal = () => run("render-final", async () => {
    if (!workspace) return;
    await api(`/api/v1/projects/${workspace.project.id}/renders:final`, {
      method: "POST",
      body: JSON.stringify({ run_key: crypto.randomUUID() }),
    });
    setRefresh((value) => value + 1);
    setNotice("Final export queued.");
  });

  const recordPublication = () => run("publication", async () => {
    if (!workspace) return;
    await api<Publication>(`/api/v1/projects/${workspace.project.id}/publications`, {
      method: "POST",
      body: JSON.stringify({
        platform: publicationPlatform,
        url: publicationUrl || null,
        published_at: publicationDate ? new Date(`${publicationDate}T00:00:00`).toISOString() : null,
      }),
    });
    await loadWorkspace(workspace.project.id);
    setPublicationUrl("");
    setPublicationDate("");
    setNotice("Publication recorded manually. Add snapshots as the post earns data.");
  });

  const recordMetrics = (publicationId: string) => run(`metrics-${publicationId}`, async () => {
    await api<MetricSnapshot>(`/api/v1/publications/${publicationId}/metrics`, {
      method: "POST",
      body: JSON.stringify({
        views: Number(metricDraft.views || 0),
        retention: metricDraft.retention ? Number(metricDraft.retention) : null,
        likes: Number(metricDraft.likes || 0),
        comments: Number(metricDraft.comments || 0),
        shares_saves: Number(metricDraft.shares_saves || 0),
        followers_gained: Number(metricDraft.followers_gained || 0),
      }),
    });
    if (projectId) await loadWorkspace(projectId);
    setMetricDraft({ views: "", retention: "", likes: "", comments: "", shares_saves: "", followers_gained: "" });
    setNotice("Metric snapshot recorded.");
  });

  const saveScene = (scene: StoryboardScene) => run(`scene-${scene.id}`, async () => {
    await api<StoryboardScene>(`/api/v1/scenes/${scene.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        duration_sec: scene.duration_sec,
        visual_prompt: scene.visual_prompt,
        asset_strategy: scene.asset_strategy,
      }),
    });
    if (projectId) await loadWorkspace(projectId);
    setNotice(`Scene ${scene.order} saved. Media generation remains a later slice.`);
  });

  const generateSceneAsset = (scene: StoryboardScene) => run(`asset-${scene.id}`, async () => {
    await api<{ job: Job }>(`/api/v1/scenes/${scene.id}/assets:generate`, {
      method: "POST",
      body: JSON.stringify({ run_key: crypto.randomUUID(), prompt: scene.visual_prompt }),
    });
    setRefresh((value) => value + 1);
    setNotice(`Image generation queued for scene ${scene.order}.`);
  });

  const searchStock = (scene: StoryboardScene) => run(`stock-${scene.id}`, async () => {
    await api<{ job: Job }>(`/api/v1/scenes/${scene.id}/assets:search-stock`, {
      method: "POST",
      body: JSON.stringify({
        run_key: crypto.randomUUID(),
        query: scene.visual_intent || scene.visual_prompt || `scene ${scene.order}`,
        media_type: stockType,
        orientation: "portrait",
        per_page: 6,
      }),
    });
    setRefresh((value) => value + 1);
    setNotice(`Pexels ${stockType} search queued for scene ${scene.order}.`);
  });

  const selectAsset = (scene: StoryboardScene, assetId: string) => run(`select-asset-${scene.id}`, async () => {
    await api(`/api/v1/scenes/${scene.id}/assets/${assetId}:select`, { method: "POST" });
    if (projectId) await loadWorkspace(projectId);
    setNotice(`Selected asset for scene ${scene.order}. Earlier candidates remain available.`);
  });

  const retryJob = (jobId: string) => run("retry", async () => {
    await api<Job>(`/api/v1/jobs/${jobId}:retry`, { method: "POST" });
    setRefresh((value) => value + 1);
  });

  const updateStory = (field: keyof StorySpec, value: string | number) => {
    setDraftStory((current) => current && { ...current, story: { ...current.story, [field]: value } });
  };

  const updateScene = (index: number, field: keyof Scene, value: string | number) => {
    setDraftStory((current) => {
      if (!current) return current;
      const scenes = current.story.scenes.map((scene, sceneIndex) => sceneIndex === index ? { ...scene, [field]: value } : scene);
      return { ...current, story: { ...current.story, scenes } };
    });
  };

  const updateVisualStyle = (field: keyof VisualBible["style"], value: string) => {
    setDraftVisualBible((current) => current && {
      ...current,
      visual_bible: {
        ...current.visual_bible,
        style: {
          ...current.visual_bible.style,
          [field]: field === "palette" || field === "camera_language" ? value.split(",").map((item) => item.trim()).filter(Boolean) : value,
        },
      },
    });
  };

  const updateVisualCharacter = (index: number, field: keyof VisualBible["characters"][number], value: string) => {
    setDraftVisualBible((current) => {
      if (!current) return current;
      const characters = current.visual_bible.characters.map((character, characterIndex) => characterIndex === index
        ? { ...character, [field]: field === "reference_asset_ids" ? value.split(",").map((item) => item.trim()).filter(Boolean) : value }
        : character);
      return { ...current, visual_bible: { ...current.visual_bible, characters } };
    });
  };

  const updateVisualLocation = (index: number, field: keyof VisualBible["locations"][number], value: string) => {
    setDraftVisualBible((current) => {
      if (!current) return current;
      const locations = current.visual_bible.locations.map((location, locationIndex) => locationIndex === index ? { ...location, [field]: value } : location);
      return { ...current, visual_bible: { ...current.visual_bible, locations } };
    });
  };

  const updateStoryboardScene = (index: number, field: keyof StoryboardScene, value: string | number) => {
    setDraftScenes((current) => current.map((scene, sceneIndex) => sceneIndex === index ? { ...scene, [field]: value } : scene));
  };

  const updateShotSpec = (index: number, field: keyof ShotSpec, value: ShotSpec[keyof ShotSpec] | undefined) => {
    setDraftScenes((current) => current.map((scene, sceneIndex) => sceneIndex === index && scene.shot_spec
      ? { ...scene, shot_spec: { ...scene.shot_spec, [field]: value } as ShotSpec }
      : scene));
  };

  if (loading) return <main className="shell"><p className="status">Loading your studio…</p></main>;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AI MICRO-STORY STUDIO · V1</p>
          <h1>Make the story earn the frame.</h1>
          <p className="lede">A focused workspace for premise pressure, sharp hooks, and human approval.</p>
        </div>
        <div className="stage-marker" aria-label="Current workflow stage">
          <span>Stage</span>
          <strong>{workspace?.project.current_stage.replace("_", " ") ?? "projects"}</strong>
        </div>
      </header>

      {error && <div className="alert error" role="alert"><strong>Something needs attention.</strong><span>{error}</span><button onClick={() => projectId && loadWorkspace(projectId)}>Retry</button></div>}
      {notice && <div className="alert success" role="status">{notice}</div>}

      <div className="workspace-grid">
        <aside className="sidebar panel">
          <div className="panel-heading"><div><p className="eyebrow">Workspace</p><h2>Projects</h2></div><span className="count">{projects.length}</span></div>
          <ul className="project-list" aria-label="Projects">
            {projects.map((project) => <li key={project.id}><button className={project.id === projectId ? "project-link active" : "project-link"} onClick={() => setProjectId(project.id)}><span>{project.title}</span><small>{project.genre ?? "open brief"}</small></button></li>)}
          </ul>
          <form className="new-project" onSubmit={createProject}>
            <p className="eyebrow">New project</p>
            <label htmlFor="project-title">Working title</label>
            <input id="project-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="The last message" />
            <label htmlFor="project-genre">Genre</label>
            <select id="project-genre" value={genre} onChange={(event) => setGenre(event.target.value)}><option>mystery</option><option>sci-fi</option><option>psychological</option><option>emotional twist</option></select>
            <button className="button primary" type="submit" disabled={busy === "create"}>{busy === "create" ? "Creating…" : "Create project"}</button>
          </form>
        </aside>

        <section className="main-column">
          {!workspace ? <div className="empty panel"><p className="eyebrow">No project open</p><h2>Start with a small, sharp brief.</h2><p>Create a project to begin comparing premises and shaping a story.</p></div> : <>
            <section className="hero panel">
              <div><p className="eyebrow">Project / {workspace.project.genre ?? "unclassified"}</p><h2>{workspace.project.title}</h2><p>Explore broadly, then choose the idea that deserves a story pass.</p></div>
              <button className="button primary" onClick={generateIdeas} disabled={busy === "generate"}>{busy === "generate" ? "Generating…" : "Generate ideas"}</button>
            </section>

            {workspace.jobs.filter((job) => ["creative_package_generation", "story_generation", "visual_bible_generation", "storyboard_generation", "scene_asset_generation", "scene_stock_search", "narration_generation", "caption_alignment", "render_preview", "render_final"].includes(job.type)).map((job) => <div className={`job-card ${job.status}`} key={job.id}><div><span className="job-kicker">{job.type.replaceAll("_", " ")}</span><strong>{jobLabel(job)}</strong><div className="job-observability">{job.outcome ?? job.status} · attempt {job.attempt}/{job.max_attempts} · {job.latency_ms == null ? "latency pending" : `${Math.round(job.latency_ms)} ms`} · regeneration {job.regeneration_count}</div>{job.error_message && <p>{job.error_message}</p>}{(job.timeline ?? []).length > 0 && <details className="job-timeline"><summary>Timeline ({job.timeline.length})</summary><ol>{job.timeline.map((event) => <li key={`${event.occurred_at}-${event.status}-${event.attempt}`}><span>{new Date(event.occurred_at).toLocaleString()}</span><strong>{event.outcome}</strong><small>attempt {event.attempt}{event.latency_ms == null ? "" : ` · ${Math.round(event.latency_ms)} ms`}</small></li>)}</ol></details>}</div>{job.status === "failed" && <button className="button quiet" onClick={() => retryJob(job.id)} disabled={busy === "retry"}>Retry stage</button>}</div>)}

            <section className="panel ideas-panel"><div className="panel-heading"><div><p className="eyebrow">01 · Ideation</p><h2>Premise room</h2></div><label className="sort-control">Sort <select value={sort} onChange={(event) => setSort(event.target.value as "score" | "created")}><option value="score">Highest signal</option><option value="created">Newest first</option></select></label></div>
              {orderedIdeas.length === 0 ? <div className="empty inline"><h3>No candidates yet.</h3><p>Generate a batch to compare hooks, originality, emotion, and visual potential.</p></div> : <div className="idea-grid">{orderedIdeas.map((idea, index) => <article className={idea.is_selected ? "idea-card selected" : "idea-card"} key={idea.id}><div className="idea-top"><span className="rank">{String(index + 1).padStart(2, "0")}</span><span className="signal">{score(idea)} / 10 signal</span></div><h3>{idea.premise}</h3><p className="hook">“{idea.hook}”</p><p>{idea.rationale}</p><div className="score-row">{Object.entries(idea.scores).slice(0, 4).map(([key, value]) => <span key={key}><small>{key.replace("_", " ")}</small><strong>{value}</strong></span>)}</div><button className={idea.is_selected ? "button selected-button" : "button quiet"} onClick={() => selectIdea(idea.id)} disabled={busy === "select"}>{idea.is_selected ? "Selected" : "Select premise"}</button></article>)}</div>}
            </section>

            <section className="panel story-panel"><div className="panel-heading"><div><p className="eyebrow">02 · Story Studio</p><h2>Draft, critique, approve</h2></div>{draftStory && <span className={`approval ${draftStory.approval_status}`}>{draftStory.approval_status}</span>}</div>
              {!draftStory ? <div className="empty inline"><h3>Your first story draft will land here.</h3><p>Run ideation to create a typed StorySpec, then edit it before approval.</p></div> : <div className="story-layout"><div className="story-editor"><div className="version-line"><span>Version {draftStory.version}</span><span>{draftStory.provider ?? "manual draft"}</span></div><label>Working title<input value={draftStory.story.working_title} onChange={(event) => updateStory("working_title", event.target.value)} /></label><div className="two-fields"><label>Genre<input value={draftStory.story.genre} onChange={(event) => updateStory("genre", event.target.value)} /></label><label>Duration (seconds)<input type="number" min={1} max={180} value={draftStory.story.target_duration_sec} onChange={(event) => updateStory("target_duration_sec", Number(event.target.value))} /></label></div><label>Premise<textarea value={draftStory.story.premise} onChange={(event) => updateStory("premise", event.target.value)} rows={2} /></label><label>Hook<textarea value={draftStory.story.hook} onChange={(event) => updateStory("hook", event.target.value)} rows={2} /></label><label>Narration<textarea value={draftStory.story.narration} onChange={(event) => updateStory("narration", event.target.value)} rows={4} /></label><label>Ending type<input value={draftStory.story.ending_type} onChange={(event) => updateStory("ending_type", event.target.value)} /></label><div className="scene-list"><h3>Scenes</h3>{draftStory.story.scenes.map((scene, index) => <div className="scene-editor" key={scene.id}><div className="scene-heading"><span>Scene {scene.order}</span><input aria-label={`Scene ${scene.order} duration`} type="number" min={0.1} max={60} value={scene.duration_sec} onChange={(event) => updateScene(index, "duration_sec", Number(event.target.value))} /></div><label>Narration<textarea value={scene.narration} onChange={(event) => updateScene(index, "narration", event.target.value)} rows={2} /></label><label>Visual intent<textarea value={scene.visual_intent} onChange={(event) => updateScene(index, "visual_intent", event.target.value)} rows={2} /></label><label>Visual prompt<textarea value={scene.visual_prompt} onChange={(event) => updateScene(index, "visual_prompt", event.target.value)} rows={2} /></label></div>)}</div><div className="action-row"><button className="button quiet" onClick={saveRevision} disabled={busy === "save"}>{busy === "save" ? "Saving…" : "Save revision"}</button>{draftStory.approval_status === "draft" && <button className="button primary" onClick={approveStory} disabled={busy === "approve"}>{busy === "approve" ? "Approving…" : "Approve StorySpec"}</button>}</div></div><aside className="critic-card"><p className="eyebrow">Story Critic</p>{draftStory.critique ? <><h3>{draftStory.critique.recommendation === "accept" ? "Ready for your gate" : "Worth another pass"}</h3><p>{draftStory.critique.summary}</p><h4>Strengths</h4><ul>{draftStory.critique.strengths.map((item) => <li key={item}>{item}</li>)}</ul>{draftStory.critique.issues.length > 0 && <><h4>Issues</h4><ul className="issues">{draftStory.critique.issues.map((item) => <li key={item}>{item}</li>)}</ul></>}</> : <p>This manual revision has no stale critique. Run a new creative pass when you want fresh feedback.</p>}</aside></div>}
            </section>

            <section className="panel visual-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">03 · Visual Bible</p><h2>Lock the visual language</h2></div>
                {draftVisualBible && <span className={`approval ${draftVisualBible.approval_status}`}>{draftVisualBible.approval_status}</span>}
              </div>
              {!draftVisualBible ? <div className="empty inline"><h3>No visual direction yet.</h3><p>Approve a StorySpec, then derive a versioned Visual Bible from it.</p><button className="button primary" onClick={generateVisualBible} disabled={!approvedStory || busy === "visual-bible"}>{busy === "visual-bible" ? "Generating…" : "Generate Visual Bible"}</button></div> : <div className="visual-layout">
                <div className="visual-editor">
                  <div className="version-line"><span>Version {draftVisualBible.version}</span><span>Derived from approved story</span></div>
                  <label>Global lighting<textarea value={draftVisualBible.visual_bible.style.lighting} onChange={(event) => updateVisualStyle("lighting", event.target.value)} rows={2} /></label>
                  <div className="two-fields"><label>Lens language<input value={draftVisualBible.visual_bible.style.lens_language} onChange={(event) => updateVisualStyle("lens_language", event.target.value)} /></label><label>Render style<input value={draftVisualBible.visual_bible.style.render_style} onChange={(event) => updateVisualStyle("render_style", event.target.value)} /></label></div>
                  <div className="two-fields"><label>Aspect ratio<input value={draftVisualBible.visual_bible.style.aspect_ratio} onChange={(event) => updateVisualStyle("aspect_ratio", event.target.value)} /></label><label>Style description<textarea value={draftVisualBible.visual_bible.style.description ?? ""} onChange={(event) => updateVisualStyle("description", event.target.value)} rows={2} /></label></div>
                  <div className="visual-list"><h3>Characters</h3>{draftVisualBible.visual_bible.characters.map((character, index) => <div className="visual-item" key={character.id}><strong>{character.id}</strong><label>Role<input value={character.role} onChange={(event) => updateVisualCharacter(index, "role", event.target.value)} /></label><div className="two-fields"><label>Age<input value={character.age} onChange={(event) => updateVisualCharacter(index, "age", event.target.value)} /></label><label>Presentation<input value={character.presentation} onChange={(event) => updateVisualCharacter(index, "presentation", event.target.value)} /></label></div><label>Face<textarea value={character.face} onChange={(event) => updateVisualCharacter(index, "face", event.target.value)} rows={2} /></label><label>Hair / build<input value={`${character.hair} / ${character.build}`} onChange={(event) => updateVisualCharacter(index, "hair", event.target.value)} /></label><label>Clothing<textarea value={character.clothing} onChange={(event) => updateVisualCharacter(index, "clothing", event.target.value)} rows={2} /></label><small>{character.reference_asset_ids.length ? `${character.reference_asset_ids.length} canonical reference(s)` : "Reference not generated"}</small></div>)}</div>
                  <div className="visual-list"><h3>Locations</h3>{draftVisualBible.visual_bible.locations.map((location, index) => <div className="visual-item" key={location.id}><strong>{location.id} · {location.name}</strong><label>Architecture / geometry<textarea value={location.architecture_geometry} onChange={(event) => updateVisualLocation(index, "architecture_geometry", event.target.value)} rows={2} /></label><div className="two-fields"><label>Time<input value={location.time} onChange={(event) => updateVisualLocation(index, "time", event.target.value)} /></label><label>Weather<input value={location.weather} onChange={(event) => updateVisualLocation(index, "weather", event.target.value)} /></label></div><label>Lighting<input value={location.lighting} onChange={(event) => updateVisualLocation(index, "lighting", event.target.value)} /></label><small>{location.reference_asset_ids.length ? `${location.reference_asset_ids.length} canonical reference(s)` : "Reference not generated"}</small></div>)}</div>
                  <div className="action-row"><button className="button quiet" onClick={saveVisualBible} disabled={busy === "save-visual-bible"}>{busy === "save-visual-bible" ? "Saving…" : "Save Visual Bible draft"}</button>{draftVisualBible.approval_status === "draft" && <button className="button primary" onClick={approveVisualBible} disabled={busy === "approve-visual-bible"}>{busy === "approve-visual-bible" ? "Approving…" : "Approve visual direction"}</button>}{draftVisualBible.approval_status === "approved" && <button className="button quiet" onClick={generateVisualReferences} disabled={busy === "visual-references"}>{busy === "visual-references" ? "Generating references…" : "Generate canonical references"}</button>}</div>{draftVisualBible.reference_assets.length > 0 && <div className="asset-grid">{draftVisualBible.reference_assets.map((asset) => <article className="asset-card" key={asset.id}><img src={`${API_BASE}${asset.content_url}`} alt={asset.asset_type} /><small>{asset.asset_type} · {asset.metadata.reference_key ? String(asset.metadata.reference_key) : "reference"}</small></article>)}</div>}
                </div>
              </div>}
            </section>

            <section className="panel storyboard-panel">
              <div className="panel-heading"><div><p className="eyebrow">04 · Storyboard</p><h2>Shape every scene before media</h2></div><button className="button primary" onClick={generateStoryboard} disabled={!draftVisualBible || draftVisualBible.approval_status !== "approved" || draftVisualBible.reference_assets.length === 0 || busy === "storyboard"}>{busy === "storyboard" ? "Generating…" : "Generate storyboard"}</button></div>
              {draftScenes.length === 0 ? <div className="empty inline"><h3>No storyboard scenes yet.</h3><p>Approve the Visual Bible and generate canonical references before deriving scenes.</p></div> : <div className="storyboard-list">{draftScenes.map((scene, index) => <div className="storyboard-item" key={scene.id}><div className="scene-heading"><span>Scene {scene.order}</span><span>{scene.motion ?? "restrained motion"}</span></div><p className="scene-intent">{scene.visual_intent}</p>{scene.shot_spec && <><div className="two-fields"><label>Action<textarea value={scene.shot_spec.action} onChange={(event) => updateShotSpec(index, "action", event.target.value)} rows={2} /></label><label>Composition<textarea value={scene.shot_spec.composition} onChange={(event) => updateShotSpec(index, "composition", event.target.value)} rows={2} /></label></div><label>Camera<input value={scene.shot_spec.camera} onChange={(event) => updateShotSpec(index, "camera", event.target.value)} /></label>{scene.shot_spec.text_overlay && <div className="two-fields"><label>Overlay text<input value={scene.shot_spec.text_overlay.text} onChange={(event) => setDraftScenes((current) => current.map((item, itemIndex) => itemIndex === index && item.shot_spec?.text_overlay ? { ...item, shot_spec: { ...item.shot_spec, text_overlay: { ...item.shot_spec.text_overlay, text: event.target.value } } } : item))} /></label><label>Overlay position<input value={`${scene.shot_spec.text_overlay.x}, ${scene.shot_spec.text_overlay.y}`} onChange={(event) => updateShotSpec(index, "text_overlay", scene.shot_spec?.text_overlay)} /></label></div>}</> }<label>Visual prompt<textarea value={scene.visual_prompt ?? ""} onChange={(event) => updateStoryboardScene(index, "visual_prompt", event.target.value)} rows={3} /></label><div className="two-fields"><label>Duration (seconds)<input type="number" min={0.1} max={60} value={scene.duration_sec} onChange={(event) => updateStoryboardScene(index, "duration_sec", Number(event.target.value))} /></label><label>Asset strategy<select value={scene.asset_strategy} onChange={(event) => updateStoryboardScene(index, "asset_strategy", event.target.value)}><option value="generated_image">Generated image</option><option value="stock_photo">Stock photo</option><option value="stock_video">Stock video</option></select></label></div><div className="asset-controls"><div className="action-row"><button className="button quiet" onClick={() => saveScene(scene)} disabled={busy === `scene-${scene.id}`}>{busy === `scene-${scene.id}` ? "Saving…" : "Save scene"}</button><button className="button primary" onClick={() => generateSceneAsset(scene)} disabled={busy === `asset-${scene.id}`}>{busy === `asset-${scene.id}` ? "Generating…" : "Generate another image"}</button><select aria-label={`Stock media type for scene ${scene.order}`} value={stockType} onChange={(event) => setStockType(event.target.value as "photo" | "video")}><option value="photo">Stock photo</option><option value="video">Stock video</option></select><button className="button quiet" onClick={() => searchStock(scene)} disabled={busy === `stock-${scene.id}`}>{busy === `stock-${scene.id}` ? "Searching…" : "Search stock again"}</button></div><div className="asset-grid">{scene.assets.length === 0 ? <p className="asset-empty">No candidates yet. Generate imagery or search Pexels for this scene.</p> : scene.assets.map((asset) => <article className={asset.id === scene.selected_asset_id ? "asset-card selected" : "asset-card"} key={asset.id}>{asset.asset_type === "stock_video" ? <video controls preload="metadata" src={`${API_BASE}${asset.content_url}`} /> : <img src={`${API_BASE}${asset.content_url}`} alt={String(asset.metadata.alt ?? asset.prompt ?? `Scene ${scene.order} candidate`)} /> }<small>{asset.provider ?? "unknown"} · {asset.asset_type}{asset.metadata.photographer ? ` · ${String(asset.metadata.photographer)}` : ""}</small>{asset.metadata.qa && <small className="issues">{String((asset.metadata.qa as { passed?: boolean }).passed === false ? "QA rejected" : "QA passed")}</small>}<button className={asset.id === scene.selected_asset_id ? "button selected-button" : "button quiet"} onClick={() => selectAsset(scene, asset.id)} disabled={busy === `select-asset-${scene.id}` || (asset.status !== "available" && asset.status !== "qa_rejected" && (asset.metadata.qa as { passed?: boolean } | undefined)?.passed !== false)}>{asset.id === scene.selected_asset_id ? (asset.status === "qa_rejected" || (asset.metadata.qa as { passed?: boolean } | undefined)?.passed === false) ? "Selected despite QA" : "Selected" : (asset.status === "qa_rejected" || (asset.metadata.qa as { passed?: boolean } | undefined)?.passed === false) ? "Select despite QA" : "Select asset"}</button></article>)}</div></div></div>)}</div>}
            </section>

            <section className="panel audio-panel">
              <div className="panel-heading"><div><p className="eyebrow">05 · Audio</p><h2>Hear the story, then align the words</h2></div><button className="button primary" onClick={generateNarration} disabled={!approvedStory || busy === "narration"}>{busy === "narration" ? "Generating…" : workspace.narrations.length > 0 ? "Generate new narration" : "Generate narration"}</button></div>
              {!approvedStory && workspace.narrations.length === 0 ? <div className="empty inline"><h3>Approve a StorySpec first.</h3><p>Remote narration is generated only from the approved story text.</p></div> : workspace.narrations.length === 0 ? <div className="empty inline"><h3>No narration versions yet.</h3><p>Generate audio from the approved story to begin review.</p></div> : <div className="audio-list">{workspace.narrations.map((narration) => <article className="audio-card" key={narration.id}><div className="version-line"><span>Version {narration.version} · {narration.provider} · {narration.voice ?? "default voice"}</span><span className={`approval ${narration.approval_status}`}>{narration.approval_status}</span></div><audio controls preload="metadata" src={`${API_BASE}${narration.audio_url}`}>Your browser does not support audio playback.</audio><p>{narration.duration_sec.toFixed(1)} seconds · {narration.model ?? "remote model"}</p><div className="action-row"><button className="button quiet" onClick={() => alignCaptions(narration)} disabled={busy === `captions-${narration.id}`}>{busy === `captions-${narration.id}` ? "Aligning…" : narration.caption_track ? "Re-align captions" : "Align captions"}</button>{narration.approval_status === "draft" && <button className="button primary" onClick={() => approveNarration(narration)} disabled={busy === `approve-narration-${narration.id}`}>{busy === `approve-narration-${narration.id}` ? "Approving…" : "Approve narration"}</button>}</div>{narration.caption_track ? <div className="caption-review"><div className="version-line"><strong>Caption alignment review</strong><span>{narration.caption_track.word_timings.length} words</span></div><p>{narration.caption_track.word_timings.map((timing) => <span className="timing-chip" key={`${timing.word}-${timing.start_sec}`}>{timing.word} <small>{timing.start_sec.toFixed(2)}–{timing.end_sec.toFixed(2)}s</small></span>)}</p><div className="caption-links">{narration.caption_track.srt_url && <a href={`${API_BASE}${narration.caption_track.srt_url}`} target="_blank" rel="noreferrer">Open SRT</a>}{narration.caption_track.json_url && <a href={`${API_BASE}${narration.caption_track.json_url}`} target="_blank" rel="noreferrer">Open JSON</a>}</div></div> : <p className="asset-empty">Align this narration to review word-level timing.</p>}</article>)}</div>}
            </section>

            <section className="panel release-panel">
              <div className="panel-heading"><div><p className="eyebrow">06 · Render review</p><h2>Approve the cut, then export</h2></div><div className="action-row compact"><button className="button primary" onClick={renderPreview} disabled={busy === "render-preview"}>{busy === "render-preview" ? "Queuing…" : latestPreview ? "Render new preview" : "Render preview"}</button><button className="button quiet" onClick={renderFinal} disabled={!latestPreview?.preview_approved_at || busy === "render-final"}>{busy === "render-final" ? "Queuing…" : "Export final"}</button></div></div>
              {workspace.renders.length === 0 ? <div className="empty inline"><h3>No renders yet.</h3><p>Once media and approved narration are ready, start a preview render.</p></div> : <div className="render-list">{workspace.renders.map((render) => <article className={`render-card ${render.status}`} key={render.id}><div className="version-line"><span>{render.render_type} · {render.status}</span><span>{render.duration_sec ? `${render.duration_sec.toFixed(1)} seconds` : "duration pending"}</span></div>{render.content_url && <video controls preload="metadata" src={`${API_BASE}${render.content_url}`}>Your browser does not support video playback.</video>}<p>{render.status === "failed" ? "This stage failed; retry the matching job above without resetting approved upstream work." : render.render_type === "preview" && !render.preview_approved_at ? "Review playback before allowing final export." : render.preview_approved_at ? `Preview approved ${new Date(render.preview_approved_at).toLocaleString()}.` : "Final export is ready for manual publication."}</p>{render.render_type === "preview" && render.status === "succeeded" && !render.preview_approved_at && <button className="button primary" onClick={approvePreview} disabled={busy === "approve-preview"}>{busy === "approve-preview" ? "Approving…" : "Approve this preview"}</button>}</article>)}</div>}
            </section>

            <section className="panel release-panel">
              <div className="panel-heading"><div><p className="eyebrow">07 · Manual release</p><h2>Publish and learn</h2></div></div>
              {!latestFinal || latestFinal.status !== "succeeded" ? <div className="empty inline"><h3>Finish a final export first.</h3><p>There is no platform automation here. Record a post only after the final video is ready.</p></div> : <><form className="release-form" onSubmit={(event) => { event.preventDefault(); recordPublication(); }}><label>Platform<input value={publicationPlatform} onChange={(event) => setPublicationPlatform(event.target.value)} placeholder="TikTok, Instagram, YouTube…" /></label><label>Publication URL <small>Optional</small><input type="url" value={publicationUrl} onChange={(event) => setPublicationUrl(event.target.value)} placeholder="https://…" /></label><label>Published date <small>Optional</small><input type="date" value={publicationDate} onChange={(event) => setPublicationDate(event.target.value)} /></label><button className="button primary" type="submit" disabled={busy === "publication"}>{busy === "publication" ? "Saving…" : "Record publication"}</button></form><div className="publication-list">{workspace.publications.map((publication) => <article className="publication-card" key={publication.id}><div className="version-line"><strong>{publication.platform}</strong><span>{publication.published_at ? new Date(publication.published_at).toLocaleDateString() : "date not set"}</span></div>{publication.url && <a href={publication.url} target="_blank" rel="noreferrer">Open publication</a>}<p>{publication.metrics.length} metric snapshot{publication.metrics.length === 1 ? "" : "s"}</p><form className="metric-form" onSubmit={(event) => { event.preventDefault(); recordMetrics(publication.id); }}><label>Views<input type="number" min="0" value={metricDraft.views} onChange={(event) => setMetricDraft((current) => ({ ...current, views: event.target.value }))} /></label><label>Retention %<input type="number" min="0" max="100" step="0.1" value={metricDraft.retention} onChange={(event) => setMetricDraft((current) => ({ ...current, retention: event.target.value }))} /></label><label>Likes<input type="number" min="0" value={metricDraft.likes} onChange={(event) => setMetricDraft((current) => ({ ...current, likes: event.target.value }))} /></label><label>Comments<input type="number" min="0" value={metricDraft.comments} onChange={(event) => setMetricDraft((current) => ({ ...current, comments: event.target.value }))} /></label><label>Shares / saves<input type="number" min="0" value={metricDraft.shares_saves} onChange={(event) => setMetricDraft((current) => ({ ...current, shares_saves: event.target.value }))} /></label><label>Followers gained<input type="number" min="0" value={metricDraft.followers_gained} onChange={(event) => setMetricDraft((current) => ({ ...current, followers_gained: event.target.value }))} /></label><button className="button quiet" type="submit" disabled={busy === `metrics-${publication.id}`}>{busy === `metrics-${publication.id}` ? "Saving…" : "Add snapshot"}</button></form>{publication.metrics.length > 0 && <div className="metric-history">{publication.metrics.map((metric) => <small key={metric.id}>{new Date(metric.captured_at).toLocaleDateString()} · {metric.views.toLocaleString()} views · {metric.retention == null ? "—" : `${metric.retention}% retention`} · {metric.likes} likes · {metric.comments} comments</small>)}</div>}</article>)}</div></>}
            </section>
          </>}
        </section>
      </div>
    </main>
  );
}
