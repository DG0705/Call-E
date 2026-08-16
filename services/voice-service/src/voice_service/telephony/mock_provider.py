"""Deterministic local telephony provider for development and tests."""

import uuid
from datetime import UTC, datetime

from voice_service.audio import AudioChunk
from voice_service.telephony.models import TelephonyCall
from voice_service.telephony.provider import (
    TelephonyTransferUnavailableError,
)


class MockTelephonyProvider:
    """Simulate the full phone-call lifecycle without any network or PBX."""

    provider_name = "mock"

    def __init__(self) -> None:
        self._state: dict[str, dict[str, object]] = {}

    def _state_for(self, call_id: str) -> dict[str, object]:
        return self._state.setdefault(
            call_id, {"queued": [], "sent": [], "hung_up": False}
        )

    async def start_call(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        conversation_id: str,
        destination_number: str,
        caller_number: str | None = None,
        request_id: str | None = None,
    ) -> TelephonyCall:
        now = datetime.now(UTC)
        call = TelephonyCall(
            call_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            caller_number=caller_number,
            destination_number=destination_number,
            direction="outbound",
            status="ringing",
            provider=self.provider_name,
            created_at=now,
            updated_at=now,
        )
        self._state_for(call.call_id)
        return call

    async def accept_call(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        conversation_id: str,
        caller_number: str,
        destination_number: str,
        request_id: str | None = None,
    ) -> TelephonyCall:
        now = datetime.now(UTC)
        call = TelephonyCall(
            call_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            caller_number=caller_number,
            destination_number=destination_number,
            direction="inbound",
            status="ringing",
            provider=self.provider_name,
            created_at=now,
            updated_at=now,
        )
        self._state_for(call.call_id)
        return call

    async def answer_call(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> TelephonyCall:
        self._state_for(call.call_id)
        call.status = "active"
        call.updated_at = datetime.now(UTC)
        return call

    async def receive_audio(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> AudioChunk | None:
        state = self._state_for(call.call_id)
        queued = state["queued"]
        if isinstance(queued, list) and queued:
            chunk = queued.pop(0)
            return chunk if isinstance(chunk, AudioChunk) else None
        return None

    async def send_audio(
        self,
        call: TelephonyCall,
        audio: AudioChunk,
        *,
        request_id: str | None = None,
    ) -> None:
        state = self._state_for(call.call_id)
        sent = state["sent"]
        if isinstance(sent, list):
            sent.append(audio)

    async def hangup(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> TelephonyCall:
        state = self._state_for(call.call_id)
        state["hung_up"] = True
        now = datetime.now(UTC)
        call.status = "ended"
        call.updated_at = now
        call.ended_at = now
        return call

    async def transfer(
        self,
        call: TelephonyCall,
        destination: str,
        *,
        request_id: str | None = None,
    ) -> TelephonyCall:
        raise TelephonyTransferUnavailableError(
            "Human transfer is not implemented for the mock provider."
        )

    def queue_audio(self, call_id: str, audio: AudioChunk) -> None:
        """Test helper: feed an audio chunk as if it came from the phone."""
        state = self._state_for(call_id)
        queued = state["queued"]
        if isinstance(queued, list):
            queued.append(audio)

    def sent_audio(self, call_id: str) -> list[AudioChunk]:
        """Test helper: return audio sent toward the phone."""
        state = self._state_for(call_id)
        sent = state["sent"]
        return [chunk for chunk in sent if isinstance(chunk, AudioChunk)] if isinstance(sent, list) else []
