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
