"""Tests for utterance accumulation (no network, no providers)."""

import struct

import pytest

from voice_service.audio import AudioChunk
from voice_service.utterance import (
    UtteranceAccumulator,
    UtteranceConfig,
    frame_rms_energy,
)


def pcm_frame(samples: list[int], sample_rate: int = 8000) -> AudioChunk:
    return AudioChunk(
        data=struct.pack(f"<{len(samples)}h", *samples),
        format="pcm",
        sample_rate=sample_rate,
    )


def speech_frame(amplitude: int = 4000) -> AudioChunk:
    samples = [amplitude if index % 2 == 0 else -amplitude for index in range(160)]
    return pcm_frame(samples)


def silence_frame() -> AudioChunk:
    return pcm_frame([0] * 160)


def test_frame_energy_separates_speech_from_silence() -> None:
    assert frame_rms_energy(silence_frame()) == 0.0
    assert frame_rms_energy(speech_frame()) > 1000.0


def test_frame_energy_rejects_non_pcm() -> None:
    with pytest.raises(ValueError):
        frame_rms_energy(AudioChunk(data=b"ab", format="ulaw"))


def test_silence_only_never_emits() -> None:
    accumulator = UtteranceAccumulator()

    for _ in range(200):
        assert accumulator.feed(silence_frame()) is None

    assert accumulator.flush() is None


def test_speech_then_silence_emits_exactly_once() -> None:
    accumulator = UtteranceAccumulator(
        config=UtteranceConfig(
            min_utterance_ms=100, end_silence_ms=200, max_utterance_ms=15000
        )
    )

    for _ in range(10):
        assert accumulator.feed(speech_frame()) is None
    utterance = None
    for _ in range(30):
        utterance = accumulator.feed(silence_frame())
        if utterance is not None:
            break

    assert utterance is not None
    assert utterance.format == "pcm"
    assert len(utterance.data) == (10 + 10) * 320
    # Buffered frames are consumed exactly once: nothing left to flush.
    assert accumulator.feed(silence_frame()) is None
    assert accumulator.flush() is None


def test_short_burst_below_minimum_is_dropped() -> None:
    accumulator = UtteranceAccumulator(
        config=UtteranceConfig(
            min_utterance_ms=400, end_silence_ms=200, max_utterance_ms=15000
        )
    )

    accumulator.feed(speech_frame())
    for _ in range(30):
        assert accumulator.feed(silence_frame()) is None
    assert accumulator.flush() is None


def test_max_length_flushes_long_utterance() -> None:
    accumulator = UtteranceAccumulator(
        config=UtteranceConfig(
            min_utterance_ms=100, end_silence_ms=60_000, max_utterance_ms=400
        )
    )

    utterance = None
    for _ in range(30):
        utterance = accumulator.feed(speech_frame())
        if utterance is not None:
            break

    assert utterance is not None
    assert len(utterance.data) == 20 * 320


def test_flush_returns_buffered_speech() -> None:
    accumulator = UtteranceAccumulator(
        config=UtteranceConfig(
            min_utterance_ms=100, end_silence_ms=60_000, max_utterance_ms=60_000
        )
    )

    for _ in range(10):
        accumulator.feed(speech_frame())

    flushed = accumulator.flush()

    assert flushed is not None
    assert len(flushed.data) == 10 * 320
    assert accumulator.flush() is None


def feed_frames(accumulator: UtteranceAccumulator, frames: list[AudioChunk]) -> AudioChunk | None:
    completed: AudioChunk | None = None
    for frame in frames:
        result = accumulator.feed(frame)
        if result is not None:
            completed = result
    return completed


def test_endpoint_short_question() -> None:
    accumulator = UtteranceAccumulator(
        config=UtteranceConfig(
            min_utterance_ms=400, end_silence_ms=400, max_utterance_ms=15000
        )
    )
    speech_ms = 0
    completed = None
    for _ in range(200):
        frame = speech_frame() if speech_ms < 600 else silence_frame()
        completed = accumulator.feed(frame)
        if completed is not None:
            break
        speech_ms += 20 if speech_ms < 600 else 0

    assert completed is not None
    # 600 ms speech + ~400 ms end silence: endpointing follows speech end.
    total_ms = len(completed.data) / 320 * 20
    assert 900 <= total_ms <= 1200


def test_endpoint_pause_in_sentence_does_not_split() -> None:
    accumulator = UtteranceAccumulator(
        config=UtteranceConfig(
            min_utterance_ms=400, end_silence_ms=800, max_utterance_ms=15000
        )
    )
    frames = (
        [speech_frame() for _ in range(20)]
        + [silence_frame() for _ in range(15)]
        + [speech_frame() for _ in range(20)]
        + [silence_frame() for _ in range(45)]
    )

    completed = feed_frames(accumulator, frames)

    assert completed is not None
    # 300 ms mid-sentence pause stays below the 800 ms threshold: one utterance.
    assert len(completed.data) / 320 * 20 >= 1400


def test_endpoint_longer_sentence_completes() -> None:
    accumulator = UtteranceAccumulator(
        config=UtteranceConfig(
            min_utterance_ms=400, end_silence_ms=400, max_utterance_ms=15000
        )
    )
    frames = [speech_frame() for _ in range(150)] + [silence_frame() for _ in range(25)]

    completed = feed_frames(accumulator, frames)

    assert completed is not None
    assert len(completed.data) / 320 * 20 >= 3000


def test_utterance_settings_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voice_service.config import load_utterance_settings

    monkeypatch.setenv("VOICE_END_SILENCE_MS", "350")
    monkeypatch.setenv("VOICE_MIN_UTTERANCE_MS", "200")
    monkeypatch.setenv("VOICE_MAX_UTTERANCE_MS", "10000")

    settings = load_utterance_settings()

    assert settings.end_silence_ms == 350
    assert settings.min_utterance_ms == 200
    assert settings.max_utterance_ms == 10000


def test_utterance_settings_reject_non_positive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voice_service.config import load_utterance_settings

    monkeypatch.setenv("VOICE_END_SILENCE_MS", "0")
    monkeypatch.setenv("VOICE_END_SILENCE_MS", "not-a-number")

    assert load_utterance_settings().end_silence_ms == 800


def test_turn_settings_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voice_service.config import load_turn_settings

    monkeypatch.setenv("VOICE_TURN_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("VOICE_STT_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("VOICE_RUNTIME_TIMEOUT_SECONDS", "25")
    monkeypatch.setenv("VOICE_TTS_TIMEOUT_SECONDS", "12")

    settings = load_turn_settings()

    assert settings.turn_timeout == 45.0
    assert settings.stt_timeout == 10.0
    assert settings.runtime_timeout == 25.0
    assert settings.tts_timeout == 12.0
