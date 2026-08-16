"""Speech and text provider configuration loaded from the service environment."""

import os
from dataclasses import dataclass

DEFAULT_STT_TRANSCRIPT = "Mock transcription of customer audio."


@dataclass(frozen=True, slots=True)
class STTSettings:
    """Configuration for selecting a speech-to-text provider at startup."""

    provider: str = "mock"
    default_transcript: str = DEFAULT_STT_TRANSCRIPT


@dataclass(frozen=True, slots=True)
class TTSSettings:
    """Configuration for selecting a text-to-speech provider at startup."""

    provider: str = "mock"


def load_stt_settings() -> STTSettings:
    """Load speech-to-text provider settings without supplying credentials."""
    return STTSettings(
        provider=os.getenv("VOICE_STT_PROVIDER", "mock").strip().lower(),
        default_transcript=os.getenv(
            "VOICE_STT_DEFAULT_TRANSCRIPT", DEFAULT_STT_TRANSCRIPT
        ).strip(),
    )


def load_tts_settings() -> TTSSettings:
    """Load text-to-speech provider settings without supplying credentials."""
    return TTSSettings(
        provider=os.getenv("VOICE_TTS_PROVIDER", "mock").strip().lower()
    )
