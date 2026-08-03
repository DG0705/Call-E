"""Minimal persistence models owned by the auth service."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


AUTH_ACCOUNTS_COLLECTION = "auth_accounts"


class AuthAccount(BaseModel):
    """A future-facing auth account record without credential data."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    service_name: str
    status: str = "active"
    created_at: datetime
    updated_at: datetime
