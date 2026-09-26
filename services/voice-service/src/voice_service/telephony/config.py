"""Telephony provider configuration loaded from the service environment."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelephonySettings:
    """Configuration for selecting a telephony provider at startup."""

    provider: str = "mock"
    asterisk_url: str | None = None
    asterisk_username: str | None = None
    asterisk_password: str | None = None


@dataclass(frozen=True, slots=True)
class RtpSettings:
    """Configuration for the Asterisk RTP media path."""

    host: str = "voice-service"
    port_start: int = 20000
    port_count: int = 100
    first_packet_timeout_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
class LiveCallSettings:
    """Configuration for the ARI-driven live inbound call runner."""

    enabled: bool = False
    ari_app: str = "call-e"


def load_telephony_settings() -> TelephonySettings:
    """Load telephony settings without supplying credentials in logs."""
    return TelephonySettings(
        provider=os.getenv("TELEPHONY_PROVIDER", "mock").strip().lower(),
        asterisk_url=_optional_environment_value("ASTERISK_URL"),
        asterisk_username=_optional_environment_value("ASTERISK_USERNAME"),
        asterisk_password=_optional_environment_value("ASTERISK_PASSWORD"),
    )


def load_rtp_settings() -> RtpSettings:
    """Load RTP media settings without supplying credentials in logs."""
    return RtpSettings(
        host=os.getenv("VOICE_RTP_HOST", "voice-service").strip() or "voice-service",
        port_start=_positive_int("VOICE_RTP_PORT_START", 20000),
        port_count=_positive_int("VOICE_RTP_PORT_COUNT", 100),
        first_packet_timeout_seconds=_positive_float(
            "VOICE_RTP_FIRST_PACKET_TIMEOUT_SECONDS", 10.0
        ),
    )


def load_live_call_settings(*, telephony_provider: str = "mock") -> LiveCallSettings:
    """Load live-call runner settings.

    The runner starts by default with the Asterisk provider and stays off
    for mock telephony; ``ASTERISK_LIVE_CALLS`` overrides either way.
    """
    default = telephony_provider.strip().lower() == "asterisk"
    raw = os.getenv("ASTERISK_LIVE_CALLS", "").strip().lower()
    enabled = default if raw == "" else raw in ("1", "true", "yes", "on")
    return LiveCallSettings(
        enabled=enabled,
        ari_app=os.getenv("ASTERISK_ARI_APP", "call-e").strip() or "call-e",
    )


def _optional_environment_value(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default
