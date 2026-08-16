from __future__ import annotations

from typing import Protocol


class ArtifactStorage(Protocol):
    def put(self, key: str, data: bytes) -> str:
        ...

    def read(self, uri: str) -> bytes:
        ...

    def delete(self, uri: str) -> None:
        ...
