"""Tests for ARI event parsing (no network, no Asterisk)."""

from voice_service.telephony.asterisk.ari_events import (
    AriEvent,
    parse_ari_event,
)


def stasis_start_payload() -> dict[str, object]:
    return {
        "type": "StasisStart",
        "application": "call-e",
        "timestamp": "2026-09-26T10:00:00.000+00:00",
        "channel": {
            "id": "chan-1",
            "name": "PJSIP/dev-phone-00000001",
            "state": "Ring",
            "caller": {"number": "+15550001", "name": "Dev Phone"},
            "connected": {"number": "", "name": ""},
            "dialplan": {
                "context": "call-e-inbound",
                "exten": "1000",
                "priority": 2,
            },
        },
        "args": ["1000"],
    }


def test_parse_stasis_start_extracts_routing_fields() -> None:
    event = parse_ari_event(stasis_start_payload())

    assert event is not None
    assert event.type == "StasisStart"
    assert event.application == "call-e"
    assert event.channel_id == "chan-1"
    assert event.destination == "1000"
    assert event.channel is not None
    assert event.channel.caller_number == "+15550001"
    assert event.channel.dialplan_context == "call-e-inbound"


def test_parse_stasis_start_falls_back_to_args_for_destination() -> None:
    payload = stasis_start_payload()
    channel = dict(payload["channel"])  # type: ignore[arg-type]
    channel["dialplan"] = {"context": "call-e-inbound", "exten": "", "priority": 2}
    payload["channel"] = channel

    event = parse_ari_event(payload)

    assert event is not None
    assert event.destination == "1000"


def test_parse_stasis_end_and_hangup_events() -> None:
    for event_type in ("StasisEnd", "ChannelHangupRequest", "ChannelDestroyed"):
        event = parse_ari_event(
            {"type": event_type, "channel": {"id": "chan-9"}}
        )
        assert event is not None
        assert event.type == event_type
        assert event.channel_id == "chan-9"


def test_parse_unknown_event_type_is_preserved() -> None:
    event = parse_ari_event({"type": "PlaybackFinished", "playback": {"id": "p-1"}})

    assert event is not None
    assert isinstance(event, AriEvent)
    assert event.type == "PlaybackFinished"
    assert event.channel_id is None


def test_parse_malformed_messages_return_none() -> None:
    assert parse_ari_event(None) is None
    assert parse_ari_event("not-json-shaped") is None
    assert parse_ari_event({"no_type": True}) is None
    assert parse_ari_event({"type": 42}) is None
    assert parse_ari_event({"type": "StasisStart"}) is not None


def test_parse_stasis_start_without_channel_has_no_destination() -> None:
    event = parse_ari_event({"type": "StasisStart", "args": []})

    assert event is not None
    assert event.channel_id is None
    assert event.destination == ""


def test_channel_snapshot_rejects_unusable_channels() -> None:
    from voice_service.telephony.asterisk.ari_events import AriChannelSnapshot

    assert AriChannelSnapshot.from_payload(None) is None
    assert AriChannelSnapshot.from_payload({"name": "no-id"}) is None
    assert AriChannelSnapshot.from_payload({"id": 123}) is None
