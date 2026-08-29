"""Development API for exercising the Kaari AI Sales Agent end-to-end."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from agent_service.runtime.runtime import AgentNotFoundError, RuntimeResult
from call_e_shared.exceptions import PlatformError


router = APIRouter(tags=["kaari-sales"])


class KaariTestRequest(BaseModel):
    """Input for the Kaari sales agent development test endpoint."""

    tenant_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class KaariTestResponse(BaseModel):
    """Stable API response for a Kaari sales agent test invocation."""

    conversation_id: str
    response: str
    tool_calls: list[dict[str, object]] = Field(default_factory=list)
    tool_results: list[dict[str, object]] = Field(default_factory=list)
    lead_id: str | None = None
    pricing: dict[str, object] | None = None
    products_matched: list[str] = Field(default_factory=list)
    request_id: str | None = None


def _not_found() -> PlatformError:
    return PlatformError(
        code="kaari_agent_not_found",
        message="Kaari agent was not found.",
        status_code=404,
    )


def _extract_demo_fields(
    history: list[dict[str, object]],
) -> tuple[str | None, dict[str, object] | None, list[str]]:
    """Extract lead_id, pricing, and product matches from tool execution history."""
    lead_id = None
    pricing = None
    products_matched: list[str] = []

    for entry in history:
        tool_name = entry.get("tool_name", "")
        if not entry.get("success"):
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue

        if tool_name == "create_sales_lead":
            lead_id = str(result.get("lead_id", "")) or lead_id

        elif tool_name == "calculate_retail_price":
            pricing = {
                "product_id": result.get("product_id"),
                "model_name": result.get("model_name"),
                "variant_id": result.get("variant_id"),
                "quantity": result.get("quantity"),
                "discount_policy": result.get("discount_policy"),
                "bulk_quote_required": result.get("bulk_quote_required"),
                "message": result.get("message"),
                "indicative_unit_price_min": result.get("indicative_unit_price_min"),
                "indicative_unit_price_max": result.get("indicative_unit_price_max"),
                "indicative_subtotal_min": result.get("indicative_subtotal_min"),
                "indicative_subtotal_max": result.get("indicative_subtotal_max"),
                "catalog_subtotal": result.get("catalog_subtotal"),
                "currency": result.get("currency"),
            }

        elif tool_name == "search_products":
            product_list = result.get("products", [])
            if isinstance(product_list, list):
                for p in product_list:
                    if isinstance(p, dict):
                        mid = p.get("model_name")
                        if mid and mid not in products_matched:
                            products_matched.append(str(mid))

    return lead_id, pricing, products_matched


@router.post(
    "/api/v1/kaari/sales/test",
    response_model=KaariTestResponse,
)
async def kaari_sales_test(
    request: Request,
    payload: KaariTestRequest,
) -> KaariTestResponse:
    """Run the Kaari AI Sales Agent through the complete workflow."""
    try:
        result: RuntimeResult = await request.app.state.agent_runtime.respond(
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            conversation_id=payload.conversation_id,
            message=payload.message,
        )
    except AgentNotFoundError as exc:
        raise _not_found() from exc

    lead_id, pricing, products_matched = _extract_demo_fields(
        result.tool_execution_history
    )

    return KaariTestResponse(
        conversation_id=result.conversation_id,
        response=result.text,
        tool_calls=[
            {
                "tool_name": e.get("tool_name"),
                "arguments": e.get("arguments"),
                "call_id": e.get("call_id"),
                "success": e.get("success"),
            }
            for e in result.tool_execution_history
        ],
        tool_results=[
            {
                "tool_name": e.get("tool_name"),
                "result": e.get("result"),
                "error": e.get("error"),
            }
            for e in result.tool_execution_history
        ],
        lead_id=lead_id,
        pricing=pricing,
        products_matched=products_matched,
        request_id=getattr(request.state, "request_id", None),
    )
