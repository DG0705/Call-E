"""Kaari Planters sales lead tool for the agent tool engine."""

from __future__ import annotations

from agent_service.kaari.models import SalesLead
from agent_service.kaari.repositories import LeadRepository
from agent_service.runtime.tools import (
    ToolDefinition,
    ToolExecutionContext,
    ToolResult,
    Tool,
)


class CreateSalesLeadTool:
    """Create a tenant-scoped sales lead from a conversation."""

    def __init__(self, repository: LeadRepository) -> None:
        self._repository = repository

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name="create_sales_lead",
            description=(
                "Create a sales lead when a customer expresses genuine interest "
                "in purchasing Kaari products. Requires customer name, phone, "
                "requirements, and at least one product ID. Optional: email, "
                "company, quantity, and notes."
            ),
            version="v1",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Full name of the customer.",
                        "minLength": 1,
                    },
                    "phone": {
                        "type": "string",
                        "description": "Customer phone number.",
                        "minLength": 1,
                    },
                    "email": {
                        "type": "string",
                        "description": "Customer email address (optional).",
                    },
                    "company": {
                        "type": "string",
                        "description": "Customer company name (optional).",
                    },
                    "requirements": {
                        "type": "string",
                        "description": "Description of what the customer needs.",
                        "minLength": 1,
                    },
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of product IDs the customer is interested in.",
                        "minItems": 1,
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Total quantity required (optional).",
                        "minimum": 1,
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes about the enquiry (optional).",
                    },
                },
                "required": ["customer_name", "phone", "requirements", "product_ids"],
                "additionalProperties": False,
            },
            risk_level="medium",
        )

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, object]
    ) -> ToolResult:
        customer_name = str(arguments.get("customer_name", "")).strip()
        phone = str(arguments.get("phone", "")).strip()
        requirements = str(arguments.get("requirements", "")).strip()
        product_ids_raw = arguments.get("product_ids", [])

        if not customer_name:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error="Customer name is required.",
                metadata={"code": "missing_customer_name"},
            )
        if not phone:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error="Phone number is required.",
                metadata={"code": "missing_phone"},
            )
        if not requirements:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error="Requirements description is required.",
                metadata={"code": "missing_requirements"},
            )
        if not isinstance(product_ids_raw, list) or not product_ids_raw:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error="At least one product_id is required.",
                metadata={"code": "missing_product_ids"},
            )

        product_ids = [str(pid) for pid in product_ids_raw]
        lead_id = f"lead-{context.tenant_id}-{context.call_id[:8]}"
        quantity = int(arguments.get("quantity", 0))

        lead = SalesLead(
            lead_id=lead_id,
            tenant_id=context.tenant_id,
            customer_name=customer_name,
            phone=phone,
            email=str(arguments.get("email", "")) or None,
            company=str(arguments.get("company", "")) or None,
            requirements=requirements,
            interested_products=product_ids,
            quantity=quantity,
            source="phone",
            status="new",
            notes=str(arguments.get("notes", "")) or "",
        )

        await self._repository.create(lead)

        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result={
                "lead_id": lead.lead_id,
                "status": lead.status,
                "confirmation": (
                    f"Sales lead {lead.lead_id} created for {customer_name}. "
                    f"Products: {', '.join(product_ids)}. "
                    f"Requirements: {requirements}"
                ),
            },
        )
