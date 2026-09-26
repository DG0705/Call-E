"""Utterance accumulation for live phone audio.

Inbound RTP arrives as 20 ms PCM frames, but the voice turn pipeline
(``VoiceSessionManager.process_audio_input``) consumes one complete caller
utterance per call. This module owns that provider-neutral framing detail:
it collects PCM frames and emits one utterance ``AudioChunk`` when trailing
silence (energy VAD) or the maximum utterance length is reached.

Each queued frame is consumed exactly once, so a finalized transcript is
never sent to the agent runtime twice.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from voice_service.audio import (
    PCM_DEFAULT_CHANNELS,
    PCM_DEFAULT_SAMPLE_RATE,
    PCM_DEFAULT_SAMPLE_WIDTH,
    AudioChunk,
)


@dataclass(frozen=True)
class UtteranceConfig:
    """Tunable framing bounds for one caller utterance."""

    sample_rate: int = PCM_DEFAULT_SAMPLE_RATE
    min_utterance_ms: int = 400
    max_utterance_ms: int = 15_000
    end_silence_ms: int = 800
    silence_rms_threshold: float = 400.0


def frame_rms_energy(frame: AudioChunk) -> float:
    """Return the RMS energy of one 16-bit mono PCM frame."""
    if (
        frame.format != "pcm"
        or frame.sample_width != 2
        or frame.channels != 1
        or len(frame.data) % 2
    ):
        raise ValueError("Utterance framing requires 16-bit mono PCM audio.")
    samples = struct.unpack(f"<{len(frame.data) // 2}h", frame.data)
    if not samples:
        return 0.0
    return (sum(sample * sample for sample in samples) / len(samples)) ** 0.5


@dataclass
class UtteranceAccumulator:
    """Collect PCM frames into utterances with energy-based end detection."""

    config: UtteranceConfig = field(default_factory=UtteranceConfig)

    def __post_init__(self) -> None:
        self._samples: list[int] = []
        self._speech_samples = 0
        self._silence_samples = 0
        self._sample_rate: int | None = None

    def feed(self, frame: AudioChunk) -> AudioChunk | None:
        """Consume one PCM frame; return a completed utterance, if any."""
        energy = frame_rms_energy(frame)
        if self._sample_rate is None:
            self._sample_rate = frame.sample_rate
        samples = struct.unpack(f"<{len(frame.data) // 2}h", frame.data)
        self._samples.extend(samples)
        if energy >= self.config.silence_rms_threshold:
            self._speech_samples += len(samples)
            self._silence_samples = 0
        else:
            self._silence_samples += len(samples)
        if self._utterance_complete():
            return self._emit()
        return None

    def flush(self) -> AudioChunk | None:
        """Emit buffered speech, if it meets the minimum utterance length."""
        if self._speech_ms() >= self.config.min_utterance_ms:
            return self._emit()
        self._reset()
        return None

    @property
    def buffered_ms(self) -> float:
        """Return how much audio is currently buffered, in milliseconds."""
        rate = self._sample_rate or self.config.sample_rate
        return len(self._samples) / rate * 1000.0

    def _utterance_complete(self) -> bool:
        total_ms = self.buffered_ms
        if total_ms >= self.config.max_utterance_ms and self._speech_samples:
            return True
        if self._speech_samples == 0:
            if total_ms >= self.config.max_utterance_ms:
                self._reset()
            return False
        silence_ms = self._silence_samples / (
            self._sample_rate or self.config.sample_rate
        ) * 1000.0
        return (
            self._speech_ms() >= self.config.min_utterance_ms
            and silence_ms >= self.config.end_silence_ms
        )

    def _speech_ms(self) -> float:
        rate = self._sample_rate or self.config.sample_rate
        return self._speech_samples / rate * 1000.0

    def _emit(self) -> AudioChunk:
        rate = self._sample_rate or self.config.sample_rate
        chunk = AudioChunk(
            data=struct.pack(f"<{len(self._samples)}h", *self._samples),
            format="pcm",
            sample_rate=rate,
            channels=PCM_DEFAULT_CHANNELS,
            sample_width=PCM_DEFAULT_SAMPLE_WIDTH,
            metadata={"utterance_frames": True},
        )
        self._reset()
        return chunk

    def _reset(self) -> None:
        self._samples = []
        self._speech_samples = 0
        self._silence_samples = 0
        self._sample_rate = None
