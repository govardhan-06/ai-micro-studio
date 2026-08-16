from __future__ import annotations

import os
import posixpath
import tempfile
from pathlib import Path
from urllib.parse import urlparse


class LocalArtifactStorage:
    scheme = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes) -> str:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".artifact-", delete=False) as temporary:
                temporary.write(data)
                temporary_path = temporary.name
            os.replace(temporary_path, path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
        return f"{self.scheme}://{self._normalise_key(key)}"

    def read(self, uri: str) -> bytes:
        return self._path_for_uri(uri).read_bytes()

    def path_for_uri(self, uri: str) -> Path:
        return self._path_for_uri(uri)

    def delete(self, uri: str) -> None:
        try:
            self._path_for_uri(uri).unlink()
        except FileNotFoundError:
            pass

    def _path_for_uri(self, uri: str) -> Path:
        parsed = urlparse(uri)
        if parsed.scheme != self.scheme:
            raise ValueError(f"unsupported artifact URI scheme: {parsed.scheme or '<missing>'}")
        key = posixpath.join(parsed.netloc, parsed.path.lstrip("/"))
        return self._path_for_key(key)

    def _path_for_key(self, key: str) -> Path:
        normalised = self._normalise_key(key)
        path = (self.root / normalised).resolve()
        if self.root not in path.parents:
            raise ValueError("artifact key escapes storage root")
        return path

    @staticmethod
    def _normalise_key(key: str) -> str:
        if not key or "\\" in key:
            raise ValueError("artifact key must be a non-empty POSIX path")
        normalised = posixpath.normpath(key)
        if normalised in {"", "."} or normalised.startswith("../") or normalised == "..":
            raise ValueError("artifact key must stay inside storage root")
        if normalised.startswith("/"):
            raise ValueError("artifact key must be relative")
        return normalised


def create_artifact_storage(root: str | Path | None = None) -> LocalArtifactStorage:
    return LocalArtifactStorage(root or os.getenv("ARTIFACT_ROOT", "/tmp/ai-micro-story-studio-artifacts"))
