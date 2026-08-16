from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .manifest import RenderManifest


class RendererError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedVideo:
    content: bytes
    duration_sec: float


def render_manifest(manifest: RenderManifest, *, renderer_root: str | Path | None = None) -> RenderedVideo:
    root = Path(renderer_root or os.getenv("RENDERER_ROOT", Path(__file__).resolve().parents[2] / "packages/renderer"))
    if not (root / "src/index.tsx").is_file():
        raise RendererError(f"renderer entrypoint not found: {root / 'src/index.tsx'}")

    with tempfile.TemporaryDirectory(prefix="ai-micro-story-render-") as directory:
        workdir = Path(directory)
        public_dir = workdir / "public"
        public_dir.mkdir()
        staged = _stage_manifest(manifest, public_dir)
        props_path = workdir / "manifest.json"
        props_path.write_text(staged.model_dump_json(), encoding="utf-8")
        output_path = workdir / "render.mp4"
        completed = subprocess.run(
            [
                "npx",
                "--no-install",
                "remotion",
                "render",
                "src/index.tsx",
                "StoryVideo",
                str(output_path),
                "--props",
                str(props_path),
                "--public-dir",
                str(public_dir),
                "--codec",
                "h264",
                "--audio-codec",
                "aac",
                "--concurrency",
                "1",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-2000:]
            raise RendererError(f"Remotion render failed: {detail}")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RendererError("Remotion did not produce a non-empty MP4")
        duration_sec = _probe_video(output_path, expected_duration=manifest.duration_sec, renderer_root=root)
        return RenderedVideo(content=output_path.read_bytes(), duration_sec=duration_sec)


def _stage_manifest(manifest: RenderManifest, public_dir: Path) -> RenderManifest:
    payload: dict[str, Any] = manifest.model_dump(mode="json")
    for index, scene in enumerate(payload["scenes"]):
        scene["asset_path"] = _stage_file(scene["asset_path"], public_dir, f"scene-{index}")
    payload["narration_path"] = _stage_file(payload["narration_path"], public_dir, "narration")
    if payload["music_path"]:
        payload["music_path"] = _stage_file(payload["music_path"], public_dir, "music")
    payload["sfx_paths"] = {
        name: _stage_file(path, public_dir, f"sfx-{index}")
        for index, (name, path) in enumerate(payload["sfx_paths"].items())
    }
    return RenderManifest.model_validate(payload)


def _stage_file(source: str, public_dir: Path, name: str) -> str:
    source_path = Path(source)
    if not source_path.is_file():
        raise RendererError(f"render input is missing: {source}")
    suffix = source_path.suffix or ".bin"
    destination = public_dir / f"{name}{suffix}"
    shutil.copy2(source_path, destination)
    return destination.relative_to(public_dir).as_posix()


def _probe_video(path: Path, *, expected_duration: float, renderer_root: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        ffprobe = next(
            (str(candidate) for candidate in (renderer_root / "node_modules").glob("@remotion/compositor-*/ffprobe") if candidate.is_file()),
            None,
        )
    if ffprobe is None:
        raise RendererError("ffprobe is required to validate render output")
    probe_env = os.environ.copy()
    probe_library_dir = str(Path(ffprobe).parent)
    for variable in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"):
        probe_env[variable] = os.pathsep.join(
            part for part in (probe_library_dir, probe_env.get(variable, "")) if part
        )
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=probe_env,
    )
    if completed.returncode != 0:
        raise RendererError(f"ffprobe failed: {completed.stderr.strip()[-1000:]}")
    try:
        probe = json.loads(completed.stdout)
        streams = probe["streams"]
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        audio = next(stream for stream in streams if stream.get("codec_type") == "audio")
        duration = float(probe["format"]["duration"])
        frame_rate = float(Fraction(video["avg_frame_rate"]))
    except (KeyError, StopIteration, TypeError, ValueError, ZeroDivisionError) as exc:
        raise RendererError("render output is missing a valid video and audio stream") from exc
    if video.get("codec_name") != "h264":
        raise RendererError("render output is not H.264")
    if (video.get("width"), video.get("height")) != (1080, 1920):
        raise RendererError("render output is not 1080x1920")
    if abs(frame_rate - 30) > 0.01:
        raise RendererError("render output is not 30 fps")
    if audio.get("codec_type") != "audio" or duration < expected_duration - 0.2 or duration > expected_duration + 0.5:
        raise RendererError("render output duration or audio stream is outside tolerance")
    return duration
