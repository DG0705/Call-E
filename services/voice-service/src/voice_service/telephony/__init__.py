"""Provider-neutral telephony integration for the voice service.

Boundary composition: TelephonyProvider -> VoiceSessionManager -> STTProvider
-> AgentRuntime -> TTSProvider -> TelephonyProvider.
"""

from voice_service.telephony.config import (
    TelephonySettings,
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
    "TelephonyCall",
    "TelephonyProvider",
    "TelephonyProviderConfigurationError",
    "TelephonyProviderError",
    "TelephonyProviderFactory",
    "TelephonySettings",
    "TelephonyTransferUnavailableError",
    "load_telephony_settings",
]
