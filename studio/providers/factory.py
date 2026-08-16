from __future__ import annotations

import os

from studio.providers.image.cloudflare import CloudflareFluxProvider
from studio.providers.image.vision import CloudflareVisionProvider
from studio.providers.stock.pexels import PexelsProvider
from studio.providers.transcription.cloudflare import CloudflareWhisperProvider
from studio.providers.tts.gemini import GeminiTTSProvider


def create_image_provider() -> CloudflareFluxProvider:
    model = os.getenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-4b")
    if os.getenv("IMAGE_PRIMARY") == "cloudflare_flux_schnell":
        model = "@cf/black-forest-labs/flux-1-schnell"
    return CloudflareFluxProvider(
        api_key=os.getenv("CLOUDFLARE_API_KEY"),
        account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID"),
        base_url=os.getenv("CLOUDFLARE_BASE_URL", "https://api.cloudflare.com/client/v4"),
        model=model,
    )


def create_vision_provider() -> CloudflareVisionProvider:
    return CloudflareVisionProvider(
        api_key=os.getenv("CLOUDFLARE_API_KEY"),
        account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID"),
        base_url=os.getenv("CLOUDFLARE_BASE_URL", "https://api.cloudflare.com/client/v4"),
    )


def create_stock_provider() -> PexelsProvider:
    return PexelsProvider(api_key=os.getenv("PEXELS_API_KEY"))


def create_tts_provider() -> GeminiTTSProvider:
    return GeminiTTSProvider(
        api_key=os.getenv("GEMINI_API_KEY"),
        model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
    )


def create_transcription_provider() -> CloudflareWhisperProvider:
    return CloudflareWhisperProvider(
        api_key=os.getenv("CLOUDFLARE_API_KEY"),
        account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID"),
        model=os.getenv("CLOUDFLARE_WHISPER_MODEL", "@cf/openai/whisper-large-v3-turbo"),
        base_url=os.getenv("CLOUDFLARE_BASE_URL", "https://api.cloudflare.com/client/v4"),
    )
