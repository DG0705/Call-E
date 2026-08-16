"""Codec conversion at the Asterisk adapter boundary.

The voice engine keeps a single internal representation: PCM, 8 kHz, mono,
16-bit little-endian (see :mod:`voice_service.audio`). Telephony adapters
convert to the codec required by the remote endpoint here, so codec handling
never spreads into the application.
"""

import struct
from typing import Final

from voice_service.audio import AudioChunk

_ULAW_BIAS: Final = 0x84
_ULAW_CLIP: Final = 32635
_ULAW_BYTES_PER_SAMPLE: Final = 1


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
