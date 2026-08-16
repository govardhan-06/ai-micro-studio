from __future__ import annotations

import mimetypes
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.persistence.models import Asset, AssetSelection, Scene
from studio.persistence.operations import new_id, select_asset
from studio.providers.media import DownloadedStockMedia, GeneratedImage
from studio.storage.local import LocalArtifactStorage


class AssetRecordNotFoundError(LookupError):
    pass


def _scene(session: Session, scene_id: str) -> Scene:
    scene = session.get(Scene, scene_id)
    if scene is None:
        raise AssetRecordNotFoundError(f"scene {scene_id} not found")
    return scene


def _asset_uri(
    storage: LocalArtifactStorage,
    *,
    project_id: str,
    scene_id: str,
    asset_id: str,
    content_type: str,
    content: bytes,
) -> str:
    extension = mimetypes.guess_extension(content_type) or ".bin"
    return storage.put(f"projects/{project_id}/scenes/{scene_id}/assets/{asset_id}{extension}", content)


def persist_generated_image(
    session: Session,
    *,
    scene_id: str,
    prompt: str,
    result: GeneratedImage,
    storage: LocalArtifactStorage,
) -> Asset:
    scene = _scene(session, scene_id)
    asset_id = new_id()
    metadata = dict(result.metadata)
    metadata.update({"content_type": result.content_type, "provenance": {"provider": result.provider, "model": result.model}})
    asset = Asset(
        id=asset_id,
        project_id=scene.project_id,
        scene_id=scene.id,
        asset_type="generated_image",
        provider=result.provider,
        model=result.model,
        local_uri=_asset_uri(storage, project_id=scene.project_id, scene_id=scene.id, asset_id=asset_id, content_type=result.content_type, content=result.content),
        prompt=prompt,
        metadata_json=metadata,
        status="available",
    )
    session.add(asset)
    session.flush()
    return asset


def persist_stock_media(
    session: Session,
    *,
    scene_id: str,
    query: str,
    downloads: Iterable[DownloadedStockMedia],
    storage: LocalArtifactStorage,
) -> list[Asset]:
    scene = _scene(session, scene_id)
    assets = []
    for download in downloads:
        candidate = download.candidate
        asset_id = new_id()
        metadata = dict(candidate.metadata)
        metadata.update(
            {
                "external_id": candidate.external_id,
                "source_url": candidate.source_url,
                "download_url": candidate.download_url,
                "width": candidate.width,
                "height": candidate.height,
                "duration_sec": candidate.duration_sec,
                "content_type": download.content_type,
                "provenance": {"provider": candidate.provider, "license": candidate.metadata.get("license")},
                "request": {"query": query, "media_type": candidate.media_type},
            }
        )
        asset = Asset(
            id=asset_id,
            project_id=scene.project_id,
            scene_id=scene.id,
            asset_type=f"stock_{candidate.media_type}",
            provider=candidate.provider,
            model=None,
            local_uri=_asset_uri(storage, project_id=scene.project_id, scene_id=scene.id, asset_id=asset_id, content_type=download.content_type, content=download.content),
            prompt=query,
            metadata_json=metadata,
            status="available",
        )
        session.add(asset)
        assets.append(asset)
    session.flush()
    return assets


def list_scene_assets(session: Session, *, scene_id: str) -> tuple[list[Asset], AssetSelection | None]:
    _scene(session, scene_id)
    assets = list(session.scalars(select(Asset).where(Asset.scene_id == scene_id).order_by(Asset.created_at.desc())))
    return assets, session.get(AssetSelection, scene_id)


def select_scene_asset(session: Session, *, scene_id: str, asset_id: str) -> AssetSelection:
    _scene(session, scene_id)
    return select_asset(session, scene_id=scene_id, asset_id=asset_id)
