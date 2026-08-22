"""Kaari Planters sales lead tool for the agent tool engine."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

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
                "and requirements. Optional: email, company, location, product IDs, "
                "quantity, preferred colours/finish/texture, budget, and notes."
            ),
            version="v2",
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
                    "location": {
                        "type": "string",
                        "description": "Customer location or city (optional).",
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
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Total quantity required (optional).",
                        "minimum": 1,
                    },
                    "preferred_colours": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Customer's preferred colours (optional).",
                    },
                    "preferred_finish": {
                        "type": "string",
                        "description": "Customer's preferred finish (optional).",
                    },
                    "preferred_texture": {
                        "type": "string",
                        "description": "Customer's preferred texture (optional).",
                    },
                    "budget": {
                        "type": "number",
                        "description": "Customer's budget in INR (optional).",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes about the enquiry (optional).",
                    },
                },
                "required": ["customer_name", "phone", "requirements"],
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

        product_ids_raw = arguments.get("product_ids", [])
        product_ids = [str(pid) for pid in product_ids_raw] if isinstance(product_ids_raw, list) else []
        quantity = int(arguments.get("quantity", 0))

        preferred_colours_raw = arguments.get("preferred_colours", [])
        preferred_colours = [str(c) for c in preferred_colours_raw] if isinstance(preferred_colours_raw, list) else []

        budget = None
        if "budget" in arguments and arguments["budget"] is not None:
            try:
                budget = Decimal(str(arguments["budget"]))
            except (InvalidOperation, ValueError):
                pass

        lead_id = f"lead-{context.tenant_id}-{context.call_id[:8]}"

        lead = SalesLead(
            lead_id=lead_id,
            tenant_id=context.tenant_id,
            customer_name=customer_name,
            phone=phone,
            email=str(arguments.get("email", "")) or None,
            company=str(arguments.get("company", "")) or None,
            location=str(arguments.get("location", "")) or None,
            requirements=requirements,
            interested_products=product_ids,
            quantity=quantity,
            preferred_colours=preferred_colours,
            preferred_finish=str(arguments.get("preferred_finish", "")) or None,
            preferred_texture=str(arguments.get("preferred_texture", "")) or None,
            budget=budget,
            source="phone",
            status="new",
            notes=str(arguments.get("notes", "")) or "",
        )

        await self._repository.create(lead)

        bulk_note = ""
        if quantity >= 20:
            bulk_note = (
                " This is a bulk order (20+ units) that will require "
                "commercial confirmation from the Kaari sales team."
            )

        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result={
                "lead_id": lead.lead_id,
                "status": lead.status,
                "bulk_order": quantity >= 20,
                "confirmation": (
                    f"Sales lead {lead.lead_id} created for {customer_name}. "
                    f"Requirements: {requirements}"
                    + (f" Products: {', '.join(product_ids)}." if product_ids else "")
                    + (f" Quantity: {quantity}." if quantity else "")
                    + bulk_note
                ),
            },
        )
