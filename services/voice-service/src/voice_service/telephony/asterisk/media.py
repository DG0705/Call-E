"""Codec conversion at the Asterisk adapter boundary.

The voice engine keeps a single internal representation: PCM, 8 kHz, mono,
16-bit little-endian (see :mod:`voice_service.audio`). Telephony adapters
convert to the codec required by the remote endpoint here, so codec handling
never spreads into the application.
"""

from typing import Final

from voice_service.audio import (
    AudioChunk,
    encode_ulaw,
    ulaw_payload_size,
)

_ULAW_BIAS: Final = 0x84
_ULAW_CLIP: Final = 32635
_ULAW_BYTES_PER_SAMPLE: Final = 1

__all__ = [
    "AudioChunk",
    "encode_ulaw",
    "ulaw_payload_size",
    "_ULAW_BIAS",
    "_ULAW_CLIP",
    "_ULAW_BYTES_PER_SAMPLE",
]
