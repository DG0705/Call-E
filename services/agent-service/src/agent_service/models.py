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
    """Provider-neutral, tenant-scoped configuration for an AI employee."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id")
    tenant_id: str
    name: str
    role: str = "assistant"
    status: str = "active"
    system_prompt: str = ""
    personality: str = "professional and helpful"
    language: str = "en"
    voice_id: str | None = None
    goals: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
