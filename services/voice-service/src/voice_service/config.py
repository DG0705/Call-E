"""Speech and text provider configuration loaded from the service environment."""

import os
from dataclasses import dataclass

DEFAULT_STT_TRANSCRIPT = "Mock transcription of customer audio."


@dataclass(frozen=True, slots=True)
class STTSettings:
    """Configuration for selecting a speech-to-text provider at startup."""

    provider: str = "mock"
    default_transcript: str = DEFAULT_STT_TRANSCRIPT
    deepgram_api_key: str | None = None
    deepgram_model: str | None = None
    deepgram_language: str | None = None


@dataclass(frozen=True, slots=True)
class TTSSettings:
    """Configuration for selecting a text-to-speech provider at startup."""

    provider: str = "mock"
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model_id: str | None = None


def load_stt_settings() -> STTSettings:
    """Load speech-to-text provider settings without supplying credentials."""
    return STTSettings(
        provider=os.getenv("VOICE_STT_PROVIDER", "mock").strip().lower(),
        default_transcript=os.getenv(
            "VOICE_STT_DEFAULT_TRANSCRIPT", DEFAULT_STT_TRANSCRIPT
        ).strip(),
        deepgram_api_key=_optional_environment_value("DEEPGRAM_API_KEY"),
        deepgram_model=_optional_environment_value("DEEPGRAM_MODEL"),
        deepgram_language=_optional_environment_value("DEEPGRAM_LANGUAGE"),
    )


def load_tts_settings() -> TTSSettings:
    """Load text-to-speech provider settings without supplying credentials."""
    return TTSSettings(
        provider=os.getenv("VOICE_TTS_PROVIDER", "mock").strip().lower(),
        elevenlabs_api_key=_optional_environment_value("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_optional_environment_value("ELEVENLABS_VOICE_ID"),
        elevenlabs_model_id=_optional_environment_value("ELEVENLABS_MODEL_ID"),
    )


def _optional_environment_value(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None
