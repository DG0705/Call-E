"""Factory for selecting the configured telephony provider."""

from voice_service.telephony.asterisk.adapter import AsteriskAdapter
from voice_service.telephony.config import TelephonySettings
from voice_service.telephony.mock_provider import MockTelephonyProvider
from voice_service.telephony.provider import TelephonyProvider


class TelephonyProviderConfigurationError(ValueError):
    """Raised when telephony provider settings are incomplete or unsupported."""


class TelephonyProviderFactory:
    """Construct the configured provider while retaining the neutral boundary."""

    @staticmethod
    def create(settings: TelephonySettings) -> TelephonyProvider:
        """Return mock or the Asterisk adapter foundation."""
        if settings.provider == "mock":
            return MockTelephonyProvider()
        if settings.provider != "asterisk":
            raise TelephonyProviderConfigurationError(
                f"Unsupported TELEPHONY_PROVIDER '{settings.provider}'. "
                "Use 'mock' or 'asterisk'."
            )
        if not settings.asterisk_url:
            raise TelephonyProviderConfigurationError(
                "ASTERISK_URL must be set when TELEPHONY_PROVIDER is 'asterisk'."
            )
        return AsteriskAdapter(
            base_url=settings.asterisk_url,
            username=settings.asterisk_username,
            password=settings.asterisk_password,
        )
