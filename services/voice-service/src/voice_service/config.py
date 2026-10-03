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


@dataclass(frozen=True, slots=True)
class TurnSettings:
    """Bounded per-turn durations (seconds) for the live-call pipeline.

    These are safety bounds against silently hung turns, not latency targets:
    exceeding any bound fails that stage fast with a spoken fallback instead
    of leaving the caller in silence.
    """

    turn_timeout: float = 30.0
    stt_timeout: float = 8.0
    runtime_timeout: float = 20.0
    tts_timeout: float = 15.0


@dataclass(frozen=True, slots=True)
class UtteranceSettings:
    """Tunable end-of-speech detection for conversational phone audio."""

    end_silence_ms: int = 400
    min_utterance_ms: int = 400
    max_utterance_ms: int = 15_000


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


def load_turn_settings() -> TurnSettings:
    """Load bounded per-turn durations from the service environment."""
    return TurnSettings(
        turn_timeout=_positive_float("VOICE_TURN_TIMEOUT_SECONDS", 30.0),
        stt_timeout=_positive_float("VOICE_STT_TIMEOUT_SECONDS", 8.0),
        runtime_timeout=_positive_float("VOICE_RUNTIME_TIMEOUT_SECONDS", 20.0),
        tts_timeout=_positive_float("VOICE_TTS_TIMEOUT_SECONDS", 15.0),
    )


def load_utterance_settings() -> UtteranceSettings:
    """Load end-of-speech detection tuning from the service environment."""
    return UtteranceSettings(
        end_silence_ms=_positive_int("VOICE_END_SILENCE_MS", 400),
        min_utterance_ms=_positive_int("VOICE_MIN_UTTERANCE_MS", 400),
        max_utterance_ms=_positive_int("VOICE_MAX_UTTERANCE_MS", 15_000),
    )


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _optional_environment_value(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None
