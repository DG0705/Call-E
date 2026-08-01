"""Shared platform primitives for Call-E services."""

from call_e_shared.config import ServiceSettings, load_settings
from call_e_shared.fastapi import create_app

__all__ = ["ServiceSettings", "create_app", "load_settings"]
