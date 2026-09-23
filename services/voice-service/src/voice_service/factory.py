"""Factories for selecting configured voice STT and TTS providers."""

from voice_service.config import STTSettings, TTSSettings
from voice_service.stt import MockSTTProvider, STTProvider
from voice_service.stt_providers import DeepgramSTTProvider
from voice_service.tts import MockTTSProvider, TTSProvider
from voice_service.tts_providers import ElevenLabsTTSProvider


class VoiceProviderConfigurationError(ValueError):
    """Raised when voice provider settings are incomplete or unsupported."""


class STTProviderFactory:
    """Construct the configured speech-to-text provider."""

    @staticmethod
    def create(settings: STTSettings) -> STTProvider:
        """Return mock or Deepgram, failing fast when a real key is missing."""
        if settings.provider == "mock":
            return MockSTTProvider(default_transcript=settings.default_transcript)
        if settings.provider != "deepgram":
            raise VoiceProviderConfigurationError(
                f"Unsupported VOICE_STT_PROVIDER '{settings.provider}'. "
                "Use 'mock' or 'deepgram'."
            )
        if settings.deepgram_api_key is None:
            raise VoiceProviderConfigurationError(
                "DEEPGRAM_API_KEY must be set when VOICE_STT_PROVIDER is 'deepgram'. "
                "Use VOICE_STT_PROVIDER='mock' for local development without credentials."
            )
        return DeepgramSTTProvider(
            api_key=settings.deepgram_api_key,
            model=settings.deepgram_model or "nova-2",
            default_language=settings.deepgram_language or "en",
        )


class TTSProviderFactory:
    """Construct the configured text-to-speech provider."""

    @staticmethod
    def create(settings: TTSSettings) -> TTSProvider:
        """Return mock or ElevenLabs, failing fast when a real key is missing."""
        if settings.provider == "mock":
            return MockTTSProvider()
        if settings.provider != "elevenlabs":
            raise VoiceProviderConfigurationError(
                f"Unsupported VOICE_TTS_PROVIDER '{settings.provider}'. "
                "Use 'mock' or 'elevenlabs'."
            )
        if settings.elevenlabs_api_key is None:
            raise VoiceProviderConfigurationError(
                "ELEVENLABS_API_KEY must be set when VOICE_TTS_PROVIDER is 'elevenlabs'. "
                "Use VOICE_TTS_PROVIDER='mock' for local development without credentials."
            )
        return ElevenLabsTTSProvider(
            api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model_id or "eleven_multilingual_v2",
        )
