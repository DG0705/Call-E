"""Audio payload helpers and codec primitives for the voice service."""

import struct
from typing import Any, Final

from pydantic import BaseModel, Field

from voice_service.models import AudioFormat

PCM_DEFAULT_SAMPLE_RATE = 8000
PCM_DEFAULT_CHANNELS = 1
PCM_DEFAULT_SAMPLE_WIDTH = 2

_ULAW_BIAS: Final = 0x84
_ULAW_CLIP: Final = 32635
_ULAW_BYTES_PER_SAMPLE: Final = 1

_WAV_HEADER = struct.Struct("<4sI4s4sIHHIIHH4sI")


class AudioChunk(BaseModel):
    """Raw audio bytes with the encoding attributes required by providers."""

    data: bytes
    format: AudioFormat
    sample_rate: int = PCM_DEFAULT_SAMPLE_RATE
    channels: int = PCM_DEFAULT_CHANNELS
    sample_width: int = PCM_DEFAULT_SAMPLE_WIDTH
    metadata: dict[str, Any] = Field(default_factory=dict)


def audio_content_type(audio_format: AudioFormat) -> str:
    """Return the HTTP content type for an audio encoding."""
    if audio_format == "wav":
        return "audio/wav"
    if audio_format == "ulaw":
        return "audio/basic"
    return "audio/pcm"


def encode_wav(chunk: AudioChunk) -> AudioChunk:
    """Wrap PCM audio in a WAV container without recoding the payload."""
    if chunk.format != "pcm":
        raise ValueError("encode_wav requires PCM audio.")
    data_size = len(chunk.data)
    block_align = chunk.channels * chunk.sample_width
    byte_rate = chunk.sample_rate * block_align
    header = _WAV_HEADER.pack(
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        chunk.channels,
        chunk.sample_rate,
        byte_rate,
        block_align,
        chunk.sample_width * 8,
        b"data",
        data_size,
    )
    return AudioChunk(
        data=header + chunk.data,
        format="wav",
        sample_rate=chunk.sample_rate,
        channels=chunk.channels,
        sample_width=chunk.sample_width,
        metadata={**chunk.metadata, "wav_encoded_from": "pcm"},
    )


def decode_wav(chunk: AudioChunk) -> AudioChunk:
    """Extract PCM payload from a WAV container for speech-to-text input."""
    if chunk.format != "wav":
        raise ValueError("decode_wav requires WAV audio.")
    data = chunk.data
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Not a RIFF/WAVE stream.")
    offset = 12
    pcm = b""
    sample_rate = PCM_DEFAULT_SAMPLE_RATE
    channels = PCM_DEFAULT_CHANNELS
    sample_width = PCM_DEFAULT_SAMPLE_WIDTH
    try:
        while offset + 8 <= len(data):
            chunk_id = data[offset : offset + 4]
            size = struct.unpack_from("<I", data, offset + 4)[0]
            body = data[offset + 8 : offset + 8 + size]
            if chunk_id == b"fmt ":
                channels = struct.unpack_from("<H", body, 2)[0]
                sample_rate = struct.unpack_from("<I", body, 4)[0]
                sample_width = max(1, struct.unpack_from("<H", body, 14)[0] // 8)
            elif chunk_id == b"data":
                pcm = body
                break
            offset += 8 + size + (size % 2)
    except struct.error as exc:
        raise ValueError("Malformed WAV stream.") from exc
    if not pcm:
        raise ValueError("WAV stream has no data chunk.")
    return AudioChunk(
        data=pcm,
        format="pcm",
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        metadata={**chunk.metadata, "wav_decoded_from": "wav"},
    )


def _highest_set_bit(value: int) -> int:
    exponent = 0
    for bit in range(7, -1, -1):
        if (value >> bit) & 1:
            exponent = bit
            break
    return exponent


_ULAW_EXP_LUT: list[int] = [
    _highest_set_bit(index) if index else 0 for index in range(256)
]


def _linear_to_ulaw(sample: int) -> int:
    sample = max(-32768, min(32767, sample))
    sign = 0x80 if sample < 0 else 0
    if sample < 0:
        sample = -sample
    if sample > _ULAW_CLIP:
        sample = _ULAW_CLIP
    sample += _ULAW_BIAS
    exponent = _ULAW_EXP_LUT[(sample >> 7) & 0xFF]
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa)) & 0xFF


def encode_ulaw(chunk: AudioChunk) -> bytes:
    """Encode 16-bit PCM audio to G.711 mu-law for SIP/RTP endpoints."""
    if chunk.format != "pcm":
        raise ValueError("encode_ulaw requires PCM audio.")
    if chunk.sample_width != 2:
        raise ValueError("encode_ulaw requires 16-bit little-endian samples.")
    if len(chunk.data) % 2:
        raise ValueError("PCM payload must contain whole 16-bit samples.")
    samples = struct.unpack(f"<{len(chunk.data) // 2}h", chunk.data)
    return bytes(_linear_to_ulaw(sample) for sample in samples)


def ulaw_payload_size(sample_count: int) -> int:
    """Return the number of bytes a mu-law payload needs for samples."""
    return sample_count * _ULAW_BYTES_PER_SAMPLE
