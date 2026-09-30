"""Tenant-scoped agent configuration routes (list/create/update)."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from agent_service.models import Agent
from call_e_shared.exceptions import PlatformError


router = APIRouter(tags=["agents"])


class CreateAgentRequest(BaseModel):
    """Fields a workspace may set when creating an AI employee."""

    tenant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    role: str = "assistant"
    status: str = "draft"
    system_prompt: str = ""
    personality: str = "professional and helpful"
    language: str = "en"
    voice_id: str | None = None
    greeting: str | None = None
    goals: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)


class UpdateAgentRequest(BaseModel):
    """Full desired configuration for a tenant-scoped AI employee."""

    tenant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    role: str = "assistant"
    status: str = "draft"
    system_prompt: str = ""
    personality: str = "professional and helpful"
    language: str = "en"
    voice_id: str | None = None
    greeting: str | None = None
    goals: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)


def _not_found() -> PlatformError:
    return PlatformError(code="agent_not_found", message="Agent was not found.", status_code=404)


@router.get("/api/v1/agents", response_model=list[Agent])
async def list_agents(
    request: Request,
    tenant_id: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Agent]:
    """List agent configurations visible to one tenant."""
    return await request.app.state.agent_service.list_by_tenant(
        tenant_id=tenant_id, limit=limit
    )


@router.post("/api/v1/agents", response_model=Agent, status_code=201)
async def create_agent(request: Request, payload: CreateAgentRequest) -> Agent:
    """Create a tenant-scoped agent configuration with a generated id."""
    return await request.app.state.agent_service.create_agent(
        tenant_id=payload.tenant_id,
        name=payload.name,
        description=payload.description,
        role=payload.role,
        status=payload.status,
        system_prompt=payload.system_prompt,
        personality=payload.personality,
        language=payload.language,
        voice_id=payload.voice_id,
        greeting=payload.greeting,
        goals=payload.goals,
        allowed_tools=payload.allowed_tools,
        knowledge_sources=payload.knowledge_sources,
    )


@router.patch("/api/v1/agents/{agent_id}", response_model=Agent)
async def update_agent(
    request: Request, agent_id: str, payload: UpdateAgentRequest
) -> Agent:
    """Replace a tenant-scoped agent configuration (pausing included)."""
    service = request.app.state.agent_service
    existing = await service.get_by_tenant_and_id(
        tenant_id=payload.tenant_id, agent_id=agent_id
    )
    if existing is None:
        raise _not_found()
    updated = existing.model_copy(
        update={
            "name": payload.name,
            "description": payload.description,
            "role": payload.role,
            "status": payload.status,
            "system_prompt": payload.system_prompt,
            "personality": payload.personality,
            "language": payload.language,
            "voice_id": payload.voice_id,
            "greeting": payload.greeting,
            "goals": payload.goals,
            "allowed_tools": payload.allowed_tools,
            "knowledge_sources": payload.knowledge_sources,
        }
    )
    return await service.update_agent(updated)
