# voice-service

Provider-neutral real-time voice engine for Call-E. Owns the tenant-scoped voice
session lifecycle (turn-based audio in / audio out), telephony call lifecycle,
and delegates speech, agent reasoning, knowledge, memory, and tools to
replaceable providers:

- `STTProvider` — speech-to-text boundary (`voice_service.stt`).
- `TTSProvider` — text-to-speech boundary (`voice_service.tts`).
- `AgentRuntimeClient` — agent runtime boundary (`voice_service.agent_runtime`),
  satisfied by the `agent-service` runtime and by the bundled HTTP client.
- `TelephonyProvider` — telephony boundary (`voice_service.telephony`),
  satisfied by `MockTelephonyProvider` and the `AsteriskAdapter`.

The service never instantiates providers in routes; `VoiceSessionManager`
(`voice_service.session`) owns the voice flow, `TelephonyService`
(`voice_service.telephony.service`) owns the call flow, and both are wired in
`create_voice_app` (`voice_service.app`).

## Run locally

```powershell
uv run uvicorn voice_service.main:app --reload
```

The default `mock` STT/TTS/telephony providers need no credentials, no network,
and no telephony stack. Set `VOICE_STT_PROVIDER` / `VOICE_TTS_PROVIDER` in the
environment when real providers are configured, and
`TELEPHONY_PROVIDER=mock|asterisk` to choose the telephony backend.

## Development session flow

```powershell
# 1. Open a voice session for one tenant + agent conversation
POST /api/v1/voice/sessions
{"tenant_id":"tenant-1","agent_id":"agent-1","conversation_id":"conversation-1"}

# 2. Send one audio utterance; get back transcript + synthesized audio
POST /api/v1/voice/sessions/{session_id}/turn
{"tenant_id":"tenant-1","audio_base64":"<pcm/wav>","audio_format":"pcm"}

# 3. Close the session
POST /api/v1/voice/sessions/{session_id}/end
{"tenant_id":"tenant-1"}
```

Audio flows: input `wav` is decoded to PCM before STT; synthesized output follows
the session's `output_audio_format` (`pcm` default, `wav`, or `ulaw`). Turn
responses return `audio_base64` plus `content_type`.

The agent runtime is the single source of truth for LLM, knowledge grounding,
tools, and conversation memory; the voice session only carries the real-time
lifecycle state (`created` → `processing` → `active`, or `ended` / `failed`).

## Telephony

The telephony integration lives in `voice_service.telephony` and composes the
voice engine through its existing interface only:

```
TelephonyProvider -> VoiceSessionManager -> STTProvider
                                      -> AgentRuntime
                                      -> TTSProvider
TelephonyProvider
```

A `TelephonyCall` (`telephony/models.py`) records call metadata in the
tenant-scoped `calls` collection; raw audio is never stored and phone numbers
are never logged. The `TelephonyService` (`telephony/service.py`) persists call
records, publishes normalized lifecycle events, and connects calls to voice
sessions via `metadata["session_id"]`.

Lifecycle events (`call.created.v1`, `call.ringing.v1`, `call.answered.v1`,
`call.started.v1`, `call.ended.v1`, `call.failed.v1`) are produced by
`telephony/events.py` and published through an `EventPublisher`; the default
`LoggingEventPublisher` writes them to the structured `telephony_event` log
field. RabbitMQ is the intended future transport for these asynchronous events
and is not part of the synchronous audio path.

### Providers

- `MockTelephonyProvider` (`telephony/mock_provider.py`) simulates the full
  call lifecycle and exposes `queue_audio` / `sent_audio` test helpers. This is
  the default and the engine of the mock end-to-end test.
- `AsteriskAdapter` (`telephony/asterisk/`) is the Asterisk/SIP implementation
  behind the boundary. It converts the internal audio representation (PCM,
  8 kHz, mono, 16-bit little-endian) to G.711 mu-law via
  `telephony/asterisk/media.py` at the adapter boundary. Real inbound media
  streaming (RTP/ARI) and human transfer are not implemented yet; outbound
  origination, answering, hangup, and play-media are mapped onto an ARI HTTP
  foundation (`telephony/asterisk/transport.py`).

  Configuration: `TELEPHONY_PROVIDER=asterisk`, `ASTERISK_URL`,
  `ASTERISK_USERNAME`, `ASTERISK_PASSWORD`. Credentials are never logged.

### Telephony development endpoints

```powershell
# Originate an outbound call (mock by default)
POST /api/v1/telephony/calls
{"tenant_id":"tenant-1","agent_id":"agent-1","destination_number":"+15550002"}

# Inspect one call (tenant-scoped)
GET /api/v1/telephony/calls/{call_id}?tenant_id=tenant-1

# Hang up a call
POST /api/v1/telephony/calls/{call_id}/hangup
{"tenant_id":"tenant-1"}
```

### Development Asterisk

A dev-only Asterisk image and config placeholders are included:

```powershell
docker compose -f docker-compose.yml -f docker-compose.asterisk.yml up -d asterisk
```

`services/voice-service/telephony/asterisk/config/` contains placeholder
`pjsip.conf`, `extensions.conf`, and `modules.conf` files with no credentials;
replace them with your PBX provisioning and set `TELEPHONY_PROVIDER=asterisk`
against a reachable `ASTERISK_URL` to exercise the adapter.

## Current scope and limitations

- Turn-based JSON API for development. No barge-in, call recording storage, or
  human transfer/escalation yet; `TelephonyProvider.transfer` is a placeholder.
- Inbound media streaming from a real phone (RTP/ARI) is not implemented; the
  inbound call flow is exercised end-to-end via the mock provider.
- Mock STT/TTS/telephony providers only; provider factories reject unknown
  configurations.
- Persistence defaults to MongoDB (`voice_sessions` and `calls` collections,
  both with tenant-scoped indexes) via `create_voice_database`;
  `InMemoryVoiceSessionStore` / `InMemoryCallStore` are available for tests and
  local demos.
