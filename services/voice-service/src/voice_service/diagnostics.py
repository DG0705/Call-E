"""Best-effort startup verification for real speech providers.

The live call path already survives provider failures (a TTS 401 never hangs
up a call), but a silent misconfiguration otherwise only shows up as a caller
hearing nothing. These checks run once at startup and log a crystal-clear
diagnosis — they never raise and never block the service from booting.
"""

import logging

import httpx


logger = logging.getLogger("voice_service.diagnostics")

_ELEVENLABS_VOICES_URL = "https://api.elevenlabs.io/v1/voices"


async def verify_elevenlabs(
    *,
    api_key: str,
    voice_id: str | None,
    timeout_seconds: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Validate the ElevenLabs key and voice, logging the exact outcome.

    Returns True only when the key is accepted and (when a voice id is
    configured) that voice is available to the key. Any failure is logged with
    enough detail to fix the configuration and returns False; it never raises.
    """
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout_seconds)
    try:
        response = await http.get(
            _ELEVENLABS_VOICES_URL,
            headers={"xi-api-key": api_key, "Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "TTS_PROVIDER_UNREACHABLE provider=elevenlabs — could not reach the "
            "ElevenLabs API to verify credentials (%s). Calls still attempt TTS "
            "at runtime.",
            exc.__class__.__name__,
        )
        return False
    finally:
        if owns_client:
            await http.aclose()

    if response.status_code in (401, 403):
        logger.error(
            "TTS_PROVIDER_ERROR provider=elevenlabs status=%s — the API key was "
            "REJECTED. Every call will be SILENT until this is fixed. Verify "
            "ELEVENLABS_API_KEY (regenerate it at elevenlabs.io) and that the "
            "account is active.",
            response.status_code,
        )
        return False
    if response.status_code >= 400:
        logger.error(
            "TTS_PROVIDER_ERROR provider=elevenlabs status=%s — credential "
            "verification failed. Calls will be silent until resolved.",
            response.status_code,
        )
        return False

    if not voice_id:
        logger.warning(
            "TTS_VOICE_UNSET provider=elevenlabs — the key is valid but no "
            "ELEVENLABS_VOICE_ID is set, so per-agent voice_id must be supplied "
            "or synthesis will fail."
        )
        return True

    try:
        payload = response.json()
        available = {
            voice.get("voice_id")
            for voice in payload.get("voices", [])
            if isinstance(voice, dict)
        }
    except ValueError:
        logger.warning(
            "TTS_VOICE_UNKNOWN provider=elevenlabs — key accepted but the voice "
            "list could not be parsed; skipping voice availability check."
        )
        return True

    if voice_id not in available:
        logger.error(
            "TTS_VOICE_UNAVAILABLE provider=elevenlabs voice_id=%s — this voice "
            "is NOT available to the configured API key, so synthesis will fail "
            "with 401/404. Pick a voice owned by or shared with this account.",
            voice_id,
        )
        return False

    logger.info(
        "TTS_PROVIDER_OK provider=elevenlabs voice_id=%s — key accepted and "
        "voice is available.",
        voice_id,
    )
    return True


async def verify_deepgram(*, api_key: str) -> bool:
    """Validate the Deepgram key against its project listing endpoint."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {api_key}"},
            )
    except httpx.HTTPError as exc:
        logger.warning(
            "STT_PROVIDER_UNREACHABLE provider=deepgram — could not reach the "
            "Deepgram API to verify credentials (%s).",
            exc.__class__.__name__,
        )
        return False

    if response.status_code in (401, 403):
        logger.error(
            "STT_PROVIDER_ERROR provider=deepgram status=%s — the API key was "
            "REJECTED. Transcription will fail on every turn (callers hear the "
            "'I didn't catch that' fallback). Verify DEEPGRAM_API_KEY.",
            response.status_code,
        )
        return False
    if response.status_code >= 400:
        logger.error(
            "STT_PROVIDER_ERROR provider=deepgram status=%s — credential "
            "verification failed.",
            response.status_code,
        )
        return False

    logger.info("STT_PROVIDER_OK provider=deepgram — key accepted.")
    return True
