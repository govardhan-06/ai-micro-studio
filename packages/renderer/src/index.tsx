import {
  AbsoluteFill,
  Audio,
  Composition,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  registerRoot,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type Caption = {
  word: string;
  start_sec: number;
  end_sec: number;
};

type Scene = {
  id: string;
  order: number;
  duration_sec: number;
  duration_in_frames: number;
  narration: string;
  motion: string;
  asset_path: string;
  asset_kind: "image" | "video";
  sfx: string[];
};

type RenderManifest = {
  schema_version: 1;
  project_id: string;
  render_id: string;
  render_type: "preview" | "final";
  width: 1080;
  height: 1920;
  fps: 30;
  duration_sec: number;
  duration_in_frames: number;
  scenes: Scene[];
  narration_path: string;
  narration_duration_sec: number;
  captions: Caption[];
  music_path: string | null;
  sfx_paths: Record<string, string>;
};

const EMPTY_MANIFEST: RenderManifest = {
  schema_version: 1,
  project_id: "preview",
  render_id: "preview",
  render_type: "preview",
  width: 1080,
  height: 1920,
  fps: 30,
  duration_sec: 1,
  duration_in_frames: 30,
  scenes: [],
  narration_path: "",
  narration_duration_sec: 1,
  captions: [],
  music_path: null,
  sfx_paths: {},
};

function motionStyle(motion: string, progress: number) {
  const name = motion.toLowerCase();
  const scale = name.includes("zoom_out")
    ? interpolate(progress, [0, 1], [1.1, 1.02])
    : name.includes("push") || name.includes("zoom")
      ? interpolate(progress, [0, 1], [1.02, 1.1])
      : 1.04;
  const translateX = name.includes("pan_left")
    ? interpolate(progress, [0, 1], [18, -18])
    : name.includes("pan_right")
      ? interpolate(progress, [0, 1], [-18, 18])
      : 0;
  const translateY = name.includes("pan_up")
    ? interpolate(progress, [0, 1], [14, -14])
    : name.includes("pan_down")
      ? interpolate(progress, [0, 1], [-14, 14])
      : 0;
  return {
    transform: `translate(${translateX}px, ${translateY}px) scale(${scale})`,
  };
}

function SceneLayer({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, Math.max(1, scene.duration_in_frames - 1)], [0, 1]);
  const style = {
    ...motionStyle(scene.motion, progress),
    height: "100%",
    objectFit: "cover" as const,
    width: "100%",
  };
  const source = staticFile(scene.asset_path);

  return scene.asset_kind === "video" ? (
    <OffthreadVideo src={source} muted style={style} />
  ) : (
    <Img src={source} style={style} />
  );
}

function CaptionOverlay({ captions }: { captions: Caption[] }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = frame / fps;
  const activeIndex = captions.findIndex((caption) => time >= caption.start_sec && time < caption.end_sec);
  if (activeIndex < 0) return null;

  const first = Math.max(0, activeIndex - 2);
  const visible = captions.slice(first, Math.min(captions.length, activeIndex + 3));
  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "flex-end",
        paddingBottom: 170,
        paddingLeft: 90,
        paddingRight: 90,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(7, 11, 20, 0.72)",
          borderRadius: 18,
          color: "#ffffff",
          fontFamily: "Arial, sans-serif",
          fontSize: 62,
          fontWeight: 800,
          lineHeight: 1.08,
          maxWidth: 900,
          padding: "18px 26px",
          textAlign: "center",
          textShadow: "0 3px 8px rgba(0, 0, 0, 0.8)",
        }}
      >
        {visible.map((caption, index) => (
          <span
            key={`${caption.start_sec}-${caption.word}-${index}`}
            style={{ color: first + index === activeIndex ? "#ffd166" : "#ffffff" }}
          >
            {caption.word}{index === visible.length - 1 ? "" : " "}
          </span>
        ))}
      </div>
    </AbsoluteFill>
  );
}

function StoryVideo(manifest: RenderManifest) {
  let startFrame = 0;
  const sceneLayers = manifest.scenes.map((scene) => {
    const from = startFrame;
    startFrame += scene.duration_in_frames;
    return (
      <Sequence key={scene.id} from={from} durationInFrames={scene.duration_in_frames}>
        <AbsoluteFill style={{ backgroundColor: "#101522" }}>
          <SceneLayer scene={scene} />
        </AbsoluteFill>
      </Sequence>
    );
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#101522" }}>
      {sceneLayers}
      <CaptionOverlay captions={manifest.captions} />
      {manifest.narration_path ? <Audio src={staticFile(manifest.narration_path)} /> : null}
      {manifest.music_path ? <Audio loop src={staticFile(manifest.music_path)} volume={0.12} /> : null}
      {Object.entries(manifest.sfx_paths).map(([name, path]) =>
        manifest.scenes.map((scene, index) => {
          if (!scene.sfx.includes(name)) return null;
          const from = manifest.scenes
            .slice(0, index)
            .reduce((total, previous) => total + previous.duration_in_frames, 0);
          return (
            <Sequence key={`${name}-${scene.id}`} from={from} durationInFrames={scene.duration_in_frames}>
              <Audio src={staticFile(path)} volume={0.35} />
            </Sequence>
          );
        }),
      )}
    </AbsoluteFill>
  );
}

function RemotionRoot() {
  return (
    <Composition
      id="StoryVideo"
      component={StoryVideo}
      durationInFrames={EMPTY_MANIFEST.duration_in_frames}
      fps={EMPTY_MANIFEST.fps}
      width={EMPTY_MANIFEST.width}
      height={EMPTY_MANIFEST.height}
      defaultProps={EMPTY_MANIFEST}
      calculateMetadata={({ props }: { props: RenderManifest }) => ({
        durationInFrames: props.duration_in_frames,
        fps: props.fps,
        width: props.width,
        height: props.height,
      })}
    />
  );
}

registerRoot(RemotionRoot);
