from __future__ import annotations

import os

from studio.providers.image.cloudflare import CloudflareFluxProvider
from studio.providers.stock.pexels import PexelsProvider
from studio.providers.transcription.groq import GroqWhisperProvider
from studio.providers.tts.gemini import GeminiTTSProvider


def create_image_provider() -> CloudflareFluxProvider:
    return CloudflareFluxProvider(
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


def create_transcription_provider() -> GroqWhisperProvider:
    return GroqWhisperProvider(
        api_key=os.getenv("GROQ_API_KEY"),
        model=os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"),
        base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
    )
