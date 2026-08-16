"""Factories for selecting configured voice STT and TTS providers."""

from voice_service.config import STTSettings, TTSSettings
from voice_service.stt import MockSTTProvider, STTProvider
from voice_service.tts import MockTTSProvider, TTSProvider


class VoiceProviderConfigurationError(ValueError):
    """Raised when voice provider settings are incomplete or unsupported."""


class STTProviderFactory:
    """Construct the configured speech-to-text provider."""

    @staticmethod
    def create(settings: STTSettings) -> STTProvider:
        """Return the mock provider, rejecting unsupported configurations."""
        if settings.provider == "mock":
            return MockSTTProvider(default_transcript=settings.default_transcript)
        raise VoiceProviderConfigurationError(
            f"Unsupported VOICE_STT_PROVIDER '{settings.provider}'. Use 'mock'."
        )


class TTSProviderFactory:
    """Construct the configured text-to-speech provider."""

    @staticmethod
    def create(settings: TTSSettings) -> TTSProvider:
        """Return the mock provider, rejecting unsupported configurations."""
        if settings.provider == "mock":
            return MockTTSProvider()
        raise VoiceProviderConfigurationError(
            f"Unsupported VOICE_TTS_PROVIDER '{settings.provider}'. Use 'mock'."
        )
