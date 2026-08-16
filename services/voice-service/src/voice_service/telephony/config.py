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


def load_telephony_settings() -> TelephonySettings:
    """Load telephony settings without supplying credentials in logs."""
    return TelephonySettings(
        provider=os.getenv("TELEPHONY_PROVIDER", "mock").strip().lower(),
        asterisk_url=_optional_environment_value("ASTERISK_URL"),
        asterisk_username=_optional_environment_value("ASTERISK_USERNAME"),
        asterisk_password=_optional_environment_value("ASTERISK_PASSWORD"),
    )


def _optional_environment_value(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None
