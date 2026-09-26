"""Live inbound call runner bridging Asterisk ARI events to the voice engine.

Production-oriented vertical slice for one real SIP conversation:

SIP phone -> Asterisk -> StasisStart -> external-media RTP -> ingress
-> utterance -> Deepgram STT -> AgentRuntime/Groq (+ Kaari tools)
-> ElevenLabs TTS -> egress RTP -> Asterisk -> SIP phone.

The runner owns only Asterisk-specific orchestration (ARI channels, bridges,
RTP wiring, turn-loop driving). Speech, reasoning, tools, memory, and session
state stay behind the existing provider-neutral boundaries:
``TelephonyService`` (calls, sessions, greeting, turns) and
``VoiceSessionManager`` (STT/agent/TTS). No Deepgram/ElevenLabs knowledge
lives here.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from call_e_shared.exceptions import PlatformError

from voice_service.audio import AudioChunk
from voice_service.telephony.asterisk.adapter import AsteriskAdapter
from voice_service.telephony.asterisk.ari_client import AriEventStream
from voice_service.telephony.asterisk.ari_events import AriEvent
from voice_service.telephony.asterisk.transport import AsteriskTransportError
from voice_service.telephony.dev_routing import KaariDevRouter
from voice_service.telephony.events import TELEPHONY_EVENT_LOGGER
from voice_service.telephony.observability import log_telephony_event
from voice_service.telephony.service import TelephonyService
from voice_service.telephony.models import TelephonyCall
from voice_service.utterance import UtteranceAccumulator, UtteranceConfig

_HANGUP_EVENT_TYPES = frozenset(
    {"StasisEnd", "ChannelHangupRequest", "ChannelDestroyed"}
)


@dataclass
class _LiveCallState:
    """Mutable per-call tracking for one live ARI conversation."""

    call: TelephonyCall
    request_id: str
    bridge_id: str | None = None
    external_channel_id: str | None = None
    accumulator: UtteranceAccumulator = field(default_factory=UtteranceAccumulator)
    turn_task: asyncio.Task[None] | None = None
    stop_turns: asyncio.Event | None = None
    answered: bool = False
    ended: bool = False


class AsteriskLiveCallRunner:
    """Drive real inbound SIP calls from ARI Stasis events to hangup."""

    def __init__(
        self,
        *,
        adapter: AsteriskAdapter,
        telephony_service: TelephonyService,
        dev_router: KaariDevRouter,
        event_stream: AriEventStream | None = None,
        rtp_host: str = "voice-service",
        rtp_port_start: int = 20000,
        rtp_port_count: int = 100,
        first_packet_timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.05,
        utterance_config: UtteranceConfig | None = None,
        start_turn_tasks: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        self._adapter = adapter
        self._transport = adapter.transport
        self._ingress = adapter.media_ingress
        self._telephony = telephony_service
        self._router = dev_router
        self._stream = event_stream
        self._rtp_host = rtp_host
        self._rtp_port_start = rtp_port_start
        self._rtp_port_count = max(1, rtp_port_count)
        self._first_packet_timeout = first_packet_timeout_seconds
        self._poll_interval = poll_interval_seconds
        self._utterance_config = utterance_config or UtteranceConfig()
        self._start_turn_tasks = start_turn_tasks
        self._logger = logger or logging.getLogger(TELEPHONY_EVENT_LOGGER)
        self._states: dict[str, _LiveCallState] = {}
        self._external_channels: dict[str, str] = {}
        self._port_cursor = 0
        self._stream_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Begin consuming ARI events in the background."""
        if self._stream_task is not None:
            return
        if self._stream is None:
            from voice_service.telephony.asterisk.ari_client import (
                AriEventStreamError,
            )

            raise AriEventStreamError(
                "No ARI event stream configured for the live-call runner."
            )
        self._stream_task = asyncio.create_task(
            self._stream.run(self.handle_event), name="ari-live-calls"
        )

    async def stop(self) -> None:
        """Stop the stream and hang up every tracked call best-effort."""
        if self._stream is not None:
            await self._stream.stop()
        if self._stream_task is not None:
            task, self._stream_task = self._stream_task, None
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        for channel_id in list(self._states):
            await self._cleanup(channel_id, reason="runner_stopped")

    async def handle_event(self, event: AriEvent) -> None:
        """Dispatch one ARI event. Unknown types are logged and ignored."""
        if event.type == "StasisStart":
            await self._handle_stasis_start(event)
        elif event.type in _HANGUP_EVENT_TYPES:
            await self._handle_hangup_event(event)
        else:
            log_telephony_event(
                self._logger, "ari_event_ignored", request_id=None,
                event_type=event.type,
            )

    async def _handle_stasis_start(self, event: AriEvent) -> None:
        channel_id = event.channel_id
        if channel_id is None:
            return
        if channel_id in self._external_channels:
            return
        if channel_id in self._states:
            log_telephony_event(
                self._logger, "stasis_start_duplicate", request_id=None,
                call_id=self._states[channel_id].call.call_id,
            )
            return
        destination = event.destination
        caller = event.channel.caller_number if event.channel else ""
        if not destination:
            await self._reject_channel(channel_id, reason="missing_destination")
            return
        try:
            route = self._router.resolve(destination_number=destination)
        except PlatformError as exc:
            await self._reject_channel(channel_id, reason=exc.code)
            return
        request_id = uuid.uuid4().hex
        conversation_id = uuid.uuid4().hex
        try:
            await self._transport.note_stasis_channel(
                channel_id, caller_number=caller, destination_number=destination
            )
            call = await self._telephony.create_inbound_call(
                tenant_id=route.tenant_id,
                agent_id=route.agent_id,
                caller_number=caller or "unknown",
                destination_number=route.destination_number,
                conversation_id=conversation_id,
                request_id=request_id,
            )
        except Exception as exc:
            self._log_call_event(
                "inbound_setup_failed", None, route.tenant_id, route.agent_id,
                conversation_id, request_id, stage="create", error=str(type(exc).__name__),
            )
            await self._reject_channel(channel_id, reason="create_failed")
            return
        state = _LiveCallState(
            call=call,
            request_id=request_id,
            accumulator=UtteranceAccumulator(config=self._utterance_config),
            stop_turns=asyncio.Event(),
        )
        self._states[channel_id] = state
        self._log_call_event(
            "stasis_start", call, None, None, None, request_id,
            ari_channel_id=channel_id,
        )
        try:
            await self._establish_media(state, channel_id)
            await self._answer(state)
        except Exception as exc:
            self._log_call_event(
                "inbound_setup_failed", call, None, None, None, request_id,
                stage="media_or_answer", error=str(type(exc).__name__),
            )
            await self._cleanup(channel_id, reason="setup_failed")
            return
        state.turn_task = None
        if self._start_turn_tasks:
            state.turn_task = asyncio.create_task(
                self._turn_loop(channel_id), name=f"live-turns-{call.call_id}"
            )

    async def _establish_media(self, state: _LiveCallState, channel_id: str) -> None:
        """Bridge the phone leg to a fresh external-media RTP path."""
        call = state.call
        port = self._rtp_port_start + (self._port_cursor % self._rtp_port_count)
        self._port_cursor += 1
        external_host = await self._adapter.bind_media_ingress(
            call, host=self._rtp_host, port=port
        )
        external_id = await self._adapter.start_external_media(
            call, external_host=external_host
        )
        state.external_channel_id = external_id
        self._external_channels[external_id] = channel_id
        self._log_call_event(
            "external_media_created", call, None, None, None, state.request_id,
            external_host=f"{self._rtp_host}:{port}",
        )
        bridge_id = await self._transport.create_bridge()
        await self._transport.add_channel_to_bridge(bridge_id, channel_id)
        await self._transport.add_channel_to_bridge(bridge_id, external_id)
        state.bridge_id = bridge_id
        self._log_call_event(
            "bridge_created", call, None, None, None, state.request_id,
        )
        remote = await self._wait_for_media(channel_id)
        self._adapter.bind_egress(
            call, remote_host=remote[0], remote_port=remote[1]
        )
        self._log_call_event(
            "media_path_ready", call, None, None, None, state.request_id,
        )

    async def _wait_for_media(self, channel_id: str) -> tuple[str, int]:
        """Wait for the first inbound RTP datagram (symmetric RTP learning)."""
        waited = 0.0
        step = 0.05
        while waited < self._first_packet_timeout:
            remote = self._ingress.remote_addr(channel_id)
            if remote is not None:
                return remote
            await asyncio.sleep(step)
            waited += step
        raise AsteriskTransportError(
            "No inbound RTP arrived for the call within the media timeout."
        )

    async def _answer(self, state: _LiveCallState) -> None:
        """Answer the call: ARI answer, voice session, greeting via RTP."""
        call = state.call
        await self._telephony.answer_call(
            tenant_id=call.tenant_id,
            call_id=call.call_id,
            request_id=state.request_id,
        )
        state.answered = True

    async def _turn_loop(self, channel_id: str) -> None:
        """Accumulate utterances and run voice turns until the call ends."""
        state = self._states.get(channel_id)
        if state is None or state.stop_turns is None:
            return
        try:
            while not state.stop_turns.is_set():
                if not await self._run_one_turn(state):
                    await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log_call_event(
                "live_turn_failed", state.call, None, None, None,
                state.request_id, error=str(type(exc).__name__),
            )
        finally:
            await self._cleanup(channel_id, reason="turn_loop_exited")

    async def _run_one_turn(self, state: _LiveCallState) -> bool:
        """Run at most one voice turn for completed utterances.

        Returns True when a turn ran (or failed and ended the loop).
        """
        utterance = self._collect_utterance(state)
        if utterance is None:
            return False
        try:
            await self._telephony.process_audio(
                tenant_id=state.call.tenant_id,
                call_id=state.call.call_id,
                audio=utterance,
                request_id=state.request_id,
            )
        except PlatformError as exc:
            self._log_call_event(
                "live_turn_failed", state.call, None, None, None,
                state.request_id, error_code=exc.code,
            )
            await self._cleanup(state.call.metadata.get("channel_id") or "", reason="turn_failed")
            return True
        return True

    def _collect_utterance(self, state: _LiveCallState) -> AudioChunk | None:
        """Drain queued frames into at most one completed utterance."""
        channel_id = state.call.metadata.get("channel_id")
        utterance: AudioChunk | None = None
        for _ in range(100):
            frame = self._ingress.receive(str(channel_id))
            if frame is None:
                break
            completed = state.accumulator.feed(frame)
            if completed is not None:
                utterance = completed
                break
        return utterance

    async def _handle_hangup_event(self, event: AriEvent) -> None:
        channel_id = event.channel_id
        if channel_id is None:
            return
        owner = self._external_channels.get(channel_id, channel_id)
        if channel_id in self._external_channels:
            self._log_call_event_external(
                "external_media_ended", owner, channel_id
            )
        if owner not in self._states:
            return
        await self._cleanup(owner, reason=f"remote_hangup:{event.type}")

    async def _reject_channel(self, channel_id: str, *, reason: str) -> None:
        log_telephony_event(
            self._logger, "inbound_unroutable", request_id=None,
            ari_channel_id=channel_id, reason=reason,
        )
        try:
            await self._transport.hangup(channel_id)
        except Exception:
            pass

    async def _cleanup(self, channel_id: str, *, reason: str) -> None:
        """End one call idempotently: task, record, bridge, channels, media."""
        state = self._states.get(channel_id)
        if state is None or state.ended:
            return
        state.ended = True
        if state.stop_turns is not None:
            state.stop_turns.set()
        task, state.turn_task = state.turn_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await self._telephony.hangup(
                tenant_id=state.call.tenant_id,
                call_id=state.call.call_id,
                request_id=state.request_id,
            )
        except PlatformError:
            pass
        except Exception as exc:
            self._log_call_event(
                "live_call_cleanup", state.call, None, None, None,
                state.request_id, reason=reason,
                hangup_error=str(type(exc).__name__),
            )
        if state.external_channel_id is not None:
            try:
                await self._transport.hangup(state.external_channel_id)
            except Exception:
                pass
            self._external_channels.pop(state.external_channel_id, None)
        if state.bridge_id is not None:
            try:
                await self._transport.destroy_bridge(state.bridge_id)
            except Exception:
                pass
        self._states.pop(channel_id, None)
        self._log_call_event(
            "live_call_cleanup", state.call, None, None, None,
            state.request_id, reason=reason,
        )

    def _log_call_event(
        self,
        event: str,
        call: TelephonyCall | None,
        tenant_id: str | None,
        agent_id: str | None,
        conversation_id: str | None,
        request_id: str | None,
        **details: object,
    ) -> None:
        session_id = call.metadata.get("session_id") if call is not None else None
        log_telephony_event(
            self._logger,
            event,
            tenant_id=call.tenant_id if call else tenant_id,
            agent_id=call.agent_id if call else agent_id,
            call_id=call.call_id if call else None,
            conversation_id=call.conversation_id if call else conversation_id,
            session_id=str(session_id) if session_id else None,
            request_id=request_id,
            **details,
        )

    def _log_call_event_external(
        self, event: str, owner_channel_id: str, external_channel_id: str
    ) -> None:
        state = self._states.get(owner_channel_id)
        self._log_call_event(
            event,
            state.call if state else None,
            None, None, None,
            state.request_id if state else None,
            external_channel_id=external_channel_id,
        )
