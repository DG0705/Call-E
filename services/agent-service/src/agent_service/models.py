"""Minimal tenant and agent persistence models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


TENANTS_COLLECTION = "tenants"
AGENTS_COLLECTION = "agents"


class Tenant(BaseModel):
    """A generic tenant boundary for platform-owned data."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    name: str
    status: str = "active"
    created_at: datetime
    updated_at: datetime


class Agent(BaseModel):
    """A tenant-scoped agent without workflow configuration."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    tenant_id: str
    name: str
    status: str = "active"
    created_at: datetime
    updated_at: datetime
