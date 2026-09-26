"""Provider-neutral telephony integration for the voice service.

Boundary composition: TelephonyProvider -> VoiceSessionManager -> STTProvider
-> AgentRuntime -> TTSProvider -> TelephonyProvider.
"""

from voice_service.telephony.config import (
    LiveCallSettings,
    RtpSettings,
    TelephonySettings,
    load_live_call_settings,
    load_rtp_settings,
    load_telephony_settings,
)
from voice_service.telephony.factory import (
    TelephonyProviderConfigurationError,
    TelephonyProviderFactory,
)
from voice_service.telephony.models import (
    CALLS_COLLECTION,
    CallDirection,
    CallStatus,
    TelephonyCall,
)
from voice_service.telephony.provider import (
    TelephonyProvider,
    TelephonyProviderError,
    TelephonyTransferUnavailableError,
)

__all__ = [
    "CALLS_COLLECTION",
    "CallDirection",
    "CallStatus",
    "LiveCallSettings",
    "RtpSettings",
    "TelephonyCall",
    "TelephonyProvider",
    "TelephonyProviderConfigurationError",
    "TelephonyProviderError",
    "TelephonyProviderFactory",
    "TelephonySettings",
    "TelephonyTransferUnavailableError",
    "load_live_call_settings",
    "load_rtp_settings",
    "load_telephony_settings",
]
