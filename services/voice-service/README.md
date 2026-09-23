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
  behind the boundary. Codec conversion stays at this boundary: outbound PCM
  (8 kHz, mono, 16-bit little-endian) is encoded to G.711 mu-law via
  `telephony/asterisk/media.py`, and inbound mu-law RTP is decoded back to
  internal PCM by `telephony/asterisk/rtp_ingress.py`, which queues decoded
  frames per ARI channel for `receive_audio`. Outbound origination,
  answering, hangup, and external-media channel creation are mapped onto an
  ARI HTTP foundation (`telephony/asterisk/transport.py`); human transfer is
  not implemented.

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
- Inbound RTP from a real phone is decoded to PCM per channel
  (`rtp_ingress.py`); bridging the phone leg to the ARI external-media
  channel and outbound RTP playback still require live Asterisk wiring (see
  "Remaining live-call blockers" below).
- Provider factories fail fast: selecting `deepgram`/`elevenlabs`/`groq`/
  `asterisk` without its required credentials raises a configuration error
  at startup instead of silently using mocks. Mocks are used only when
  `provider=mock`.
- Persistence defaults to MongoDB (`voice_sessions` and `calls` collections,
  both with tenant-scoped indexes) via `create_voice_database`;
  `InMemoryVoiceSessionStore` / `InMemoryCallStore` are available for tests and
  local demos.

---

# How to run a real Kaari phone call

This section documents the complete architecture, configuration, and steps to
run a real phone call with the Kaari AI Sales Agent using real STT/TTS providers
and Asterisk telephony.

## Architecture

```
CALLER (SIP/Softphone)
    ↓ (SIP/RTP)
ASTERISK (PJSIP + ARI)
    ↓ (ARI REST + RTP media)
CALL-E VOICE-SERVICE (AsteriskAdapter)
    ↓
  ┌─────────────────────────────────────────────────────┐
  │ VoiceSessionManager                                 │
  │  • STTProvider  → Deepgram (real) or Mock           │
  │  • AgentRuntime → agent-service (Groq LLM)          │
  │  • TTSProvider  → ElevenLabs (real) or Mock         │
  └─────────────────────────────────────────────────────┘
    ↓
ASTERISK (media playback)
    ↓ (RTP)
CALLER
```

The Kaari agent (`kaari-planters` / `kaari-sales-agent`) is seeded on startup.
It uses the product catalog, pricing engine, and lead creation tools to handle
sales enquiries over the phone.

## Required environment variables

Create a `.env` file in the repo root (or export in your shell) with:

```env
# Core infrastructure (set strong local values)
MONGO_INITDB_ROOT_USERNAME=call_e
MONGO_INITDB_ROOT_PASSWORD=change_me
RABBITMQ_DEFAULT_USER=call_e
RABBITMQ_DEFAULT_PASS=change_me

# Agent service (Groq LLM)
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.1-70b-versatile
AGENT_SERVICE_SEED=true

# Voice service (real STT/TTS)
VOICE_STT_PROVIDER=deepgram
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPGRAM_MODEL=nova-3
DEEPGRAM_LANGUAGE=en

VOICE_TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=your_voice_id
ELEVENLABS_MODEL_ID=eleven_multilingual_v2

# Telephony (Asterisk)
TELEPHONY_PROVIDER=asterisk
ASTERISK_URL=http://asterisk:8088
ASTERISK_USERNAME=call-e-user
ASTERISK_PASSWORD=your_ari_password

# Dev inbound routing (extension that reaches Kaari)
KAARI_DEV_EXTENSION=1000
```

**Never commit real credentials.** The `.env` file is gitignored. Use
`.env.example` as a template.

## Provider configuration

### STT: Deepgram
- Set `VOICE_STT_PROVIDER=deepgram`
- Provide `DEEPGRAM_API_KEY`, `DEEPGRAM_MODEL` (e.g., `nova-3`), `DEEPGRAM_LANGUAGE`
- The voice engine sends 8 kHz PCM (mu-law decoded) to Deepgram

### TTS: ElevenLabs
- Set `VOICE_TTS_PROVIDER=elevenlabs`
- Provide `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID` (e.g., `eleven_multilingual_v2`)
- Requests `pcm_8000` output; the adapter wraps to PCM/WAV/μ-law as needed

### LLM: Groq
- Set `LLM_PROVIDER=groq`
- Provide `GROQ_API_KEY` and `GROQ_MODEL` (e.g., `llama-3.1-70b-versatile`)
- Used by agent-service runtime for the Kaari agent

## Asterisk setup

A development Asterisk image is provided via docker-compose:

```powershell
docker compose -f docker-compose.yml -f docker-compose.asterisk.yml up -d
```

This starts Asterisk with the configs from
`services/voice-service/telephony/asterisk/config/`:
- `pjsip.conf` — SIP endpoint `call-e-dev-phone` (username `dev-phone`,
  password **must be set locally**; default placeholder `CHANGE_ME_LOCAL_ONLY`)
- `extensions.conf` — routes inbound calls to the `call-e` ARI app
- `modules.conf` — loads `res_pjsip.so` and `res_ari.so`
- `ari.conf` — ARI user `call-e-user` (password **must be set locally**)
- `http.conf` — ARI HTTP on `0.0.0.0:8088`

**Important:** Before running, create a local override for `pjsip.conf` and
`ari.conf` with your own passwords, or mount them at runtime. Do not commit
real credentials.

Configure your softphone (e.g., Zoiper, Linphone) to register:
- SIP server: `localhost:5060` (or your Asterisk host)
- Username: `dev-phone`
- Password: your local `pjsip.conf` password

## Call routing

The development inbound route maps a single extension to the Kaari agent:

- Caller dials extension **1000** (or the value of `KAARI_DEV_EXTENSION`)
- Asterisk hands the channel to the `call-e` ARI application
- Voice service answers, creates a voice session, plays the agent greeting:
  > "Hello, thank you for calling Kaari Planters. I would be happy to help you find the right planters. What are you looking for today?"

You can also override the target tenant/agent via the dev inbound HTTP route:

```powershell
POST /api/v1/telephony/dev/inbound
{
  "caller_number": "+919876543210",
  "destination_number": "9999",
  "tenant_id": "kaari-planters",
  "agent_id": "kaari-sales-agent",
  "conversation_id": "conv-1"
}
```

## Expected conversation

A typical multi-turn Kaari enquiry:

1. **Greeting** (agent): "Hello, thank you for calling Kaari Planters..."
2. **Customer**: "I need planters for my office, about 10 of them, around 2 feet tall."
3. **Agent** (searches Neo/Linea collections): "I found several options... The DEW planter in Neo collection..."
4. **Customer**: "How much is the 40-inch DEW?"
5. **Agent** (calculates retail price with 30% discount for 10 units): "For 10 units, the unit price is ₹14,600 with a 30% standard retail discount..."
6. **Customer**: "Okay, I want to proceed. My name is John, phone +91-9876543210."
7. **Agent** (creates sales lead): "I've created your enquiry. A Kaari sales team member will contact you shortly. The lead ID is..."

Pricing policy (verifiable in the call):
- 1–3 units: 20–25% indicative retail discount
- 4–19 units: 30% exact discount
- 20+ units: bulk quote required, human confirmation (never invents a bulk price)

Safety guarantees (enforced by the agent):
- Never claims stock availability (products are made to order)
- Never promises delivery timelines
- Colour/texture customization available per catalog

## Mock development mode (no paid APIs)

For local development without real provider credentials, all providers default
to `mock`:

```powershell
# Start only core services
docker compose up -d mongodb rabbitmq
# Start agent-service + voice-service
uv run uvicorn agent_service.main:app --reload
uv run uvicorn voice_service.main:app --reload
```

Run the end-to-end smoke test (uses all mocks):

```powershell
uv run pytest services/agent-service/tests/test_kaari.py::test_kaari_mvp_smoke_test -v
```

This validates the full chain without any external dependencies.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Call rings but no greeting | TTS failed or Asterisk media not playing | Check `ELEVENLABS_API_KEY` and Asterisk ARI connection; logs show `audio_synthesized` event |
| "Agent configuration unavailable" | Kaari agent not seeded | Ensure `AGENT_SERVICE_SEED=true` and MongoDB reachable; check `call_started` event |
| STT returns empty transcript | Audio format mismatch | Verify Asterisk sends μ-law 8 kHz; voice engine expects PCM/WAV/μ-law |
| Groq errors / timeout | `GROQ_API_KEY` missing or model name wrong | Check `LLM_PROVIDER=groq` + valid key/model; startup fails fast with a clear error if unset |
| Asterisk ARI 401/403 | `ASTERISK_USERNAME`/`PASSWORD` mismatch | Match `ari.conf` and `voice-service` env vars |
| SIP registration fails | `pjsip.conf` password mismatch | Update local `pjsip.conf` with your softphone password |

Logs to watch (structured JSON, IDs only — never audio, transcripts, or secrets):
- `voice_service.events` — `session_created`, `turn_started`,
  `transcription_completed`, `runtime_response_generated`, `tts_started`,
  `synthesis_completed`/`audio_synthesized`, `turn_failed`, `session_ended`
- `voice_service.telephony.events` — `call_created`, `call_ringing`,
  `call_answered`, `media_channel_established`, `audio_packet_received`,
  `transcript_produced`, `agent_response_produced`, `audio_returned`,
  `call_started`, `call_ended`, `call_failed`
- `agent_service.runtime.events` — `agent_turn_started`, `tool_called`,
  `tool_completed`, `response_generated`

## Inspecting results

After a call ends:
- Conversation transcript: query MongoDB `conversations` collection (`tenant_id=kaari-planters`, `agent_id=kaari-sales-agent`)
- Sales lead: query MongoDB `leads` collection (same tenant)
- Call record: `calls` collection with `tenant_id=kaari-planters`

## Real-provider mode vs Mock mode

| Aspect | Mock mode (default) | Real-provider mode |
|--------|---------------------|---------------------|
| STT | Returns fixed transcript | Deepgram API |
| TTS | Returns synthetic PCM | ElevenLabs API |
| LLM | Returns "Mock response: ..." | Groq API |
| Telephony | In-memory `MockTelephonyProvider` | Asterisk ARI adapter |
| Credentials | None needed | `.env` with real API keys |
| Missing credential | N/A | Startup fails fast with a clear error |
| Use case | CI, local dev, unit tests | Live demos, manual QA |

## Media format path

Enforced architecture (conversion only at the Asterisk adapter boundary):

```
Asterisk μ-law RTP (8 kHz)
  → rtp_ingress.py: parse RTP, decode_ulaw → internal PCM (8 kHz, mono, 16-bit LE)
  → VoiceSessionManager → Deepgram (encoding=slinear16 or mulaw passthrough)
  → AgentRuntime → ElevenLabs (pcm_8000)
  → internal PCM → media.py encode_ulaw → Asterisk μ-law RTP
```

`VoiceSessionManager` only ever receives normalized `AudioChunk` objects and
never sees RTP. Inbound wiring per call: `bind_media_ingress(call, host, port)`
then `start_external_media(call, external_host)` (ARI `externalMedia`, format
`ulaw`, app `call-e`). RTP ports 10000–10099/udp are published by
`docker-compose.asterisk.yml` and constrained by `rtp.conf`.

## Development check and live smoke

Validate the local stack without printing secrets:

```powershell
# Environment + dependency + Kaari seed check (works in mock mode)
.venv\Scripts\python.exe tools\dev_check.py

# Live provider smoke (requires --live AND real keys in the environment)
.venv\Scripts\python.exe tools\smoke_live_providers.py --live
```

`dev_check.py` reports `CALL-E DEVELOPMENT CHECK` (MongoDB, RabbitMQ, Groq,
Deepgram, ElevenLabs, Asterisk, Kaari Agent). `smoke_live_providers.py`
performs real Groq/Deepgram/ElevenLabs/ARI calls plus Kaari lookup and never
runs in CI.

## Remaining live-call blockers

Verified against the running stack; each item is the exact remaining work:

1. **ARI phone-leg ↔ external-media bridge** (`transport.py`,
   `extensions.conf`): `create_external_media` maps the real ARI endpoint,
   but nothing yet bridges the Stasis phone channel to the external-media
   channel, so live caller RTP never reaches the ingress listener. Required
   action: after `StasisStart`, create an ARI bridge and add both channels
   (needs the ARI WebSocket event stream, also not yet implemented).
2. **Outbound RTP playback** (`transport.py::play_media`): ARI plays named
   sounds, not raw bytes, so synthesized PCM cannot be streamed yet. Required
   action: serve TTS output over HTTP and play via ARI `/play`, or stream it
   back through the external-media RTP socket.
3. **Real provider credentials**: no `GROQ_API_KEY`, `DEEPGRAM_API_KEY`,
   `ELEVENLABS_API_KEY`, or ARI/SIP passwords exist in this environment, so
   criteria 6–8 and 10–13 are proven by fakes/unit tests, not live calls.
4. **Traefik Docker discovery on this host**: Traefik v3.2/v3.5 cannot query
   the Docker Desktop (Engine 29) socket proxy (`400 Bad Request`, empty
   message), so host-port routes (`localhost/voice-service/...`) 404 while
   every service is healthy in-network. Required action: upgrade Traefik past
   the incompatibility or add a static file provider; meanwhile reach
   services via `docker compose exec`.

---

**Security reminder:** All credentials stay in local environment variables.
`.env` files are gitignored. No secrets appear in logs (observability helpers
explicitly avoid logging API keys, SIP credentials, or raw audio).
