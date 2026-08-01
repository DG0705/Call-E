"""Shared platform primitives for Call-E services."""

from call_e_shared.auth import AuthContext
from call_e_shared.config import ServiceSettings, load_settings
from call_e_shared.fastapi import create_app
from call_e_shared.responses import PlatformResponse, build_platform_response

__all__ = [
    "PlatformResponse",
    "ServiceSettings",
    "AuthContext",
    "build_platform_response",
    "create_app",
    "load_settings",
]
