# voice-service

Provider-neutral real-time voice engine for Call-E. Owns the tenant-scoped voice
session lifecycle (turn-based audio in / audio out) and delegates speech, agent
reasoning, knowledge, memory, and tools to replaceable providers:

- `STTProvider` — speech-to-text boundary (`voice_service.stt`).
- `TTSProvider` — text-to-speech boundary (`voice_service.tts`).
- `AgentRuntimeClient` — agent runtime boundary (`voice_service.agent_runtime`),
  satisfied by the `agent-service` runtime and by the bundled HTTP client.

The service never instantiates providers in routes; `VoiceSessionManager`
(`voice_service.session`) owns the flow and is wired in `create_voice_app`
(`voice_service.app`).

## Run locally

```powershell
uv run uvicorn voice_service.main:app --reload
```

The default `mock` STT/TTS providers need no credentials, no network, and no
telephony stack. Set `VOICE_STT_PROVIDER` / `VOICE_TTS_PROVIDER` in the
environment when real providers are configured.

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

## Current scope and limitations

- Turn-based JSON API for development. No telephony, SIP, Asterisk, WebRTC,
  barge-in, or call recording/transfer/escalation yet.
- Mock STT/TTS providers only; provider factories reject unknown configurations.
- Persistence defaults to MongoDB (`voice_sessions` collection, tenant-scoped
  index) via `create_voice_database`; `InMemoryVoiceSessionStore` is available
  for tests and local demos.
