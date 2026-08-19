"""Kaari Planters product tools for the agent tool engine."""

from __future__ import annotations

from agent_service.kaari.repositories import ProductRepository
from agent_service.runtime.tools import (
    ToolDefinition,
    ToolExecutionContext,
    ToolResult,
    Tool,
)


class SearchProductsTool:
    """Search the Kaari product catalog by query, category, and size."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name="search_products",
            description=(
                "Search Kaari FRP planter products by text query, category, and size. "
                "Returns matching products with names, descriptions, and base prices. "
                "Use this to find relevant products for a customer enquiry."
            ),
            version="v1",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search query (e.g. 'outdoor planter', 'tall white')",
                        "minLength": 1,
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional product category filter (e.g. 'Round Planter', 'Wall Planter')",
                    },
                    "size": {
                        "type": "string",
                        "description": "Optional size keyword to match in dimensions (e.g. 'large', '40cm')",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Optional expected quantity, included in results for reference.",
                        "minimum": 1,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            risk_level="low",
        )

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, object]
    ) -> ToolResult:
        query = str(arguments.get("query", ""))
        category = arguments.get("category")
        size = arguments.get("size")
        quantity = arguments.get("quantity")

        products = await self._repository.search(
            tenant_id=context.tenant_id,
            query=query,
            category=str(category) if category else None,
            size=str(size) if size else None,
        )

        if not products:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=True,
                result={
                    "products": [],
                    "message": "No products found matching your criteria.",
                },
            )

        product_list = [
            {
                "product_id": p.product_id,
                "product_code": p.product_code,
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "dimensions": p.dimensions,
                "material": p.material,
                "colours": p.colours,
                "finish": p.finish,
                "base_price": p.base_price,
                "currency": p.currency,
                "price_display": p.price_display,
            }
            for p in products
        ]

        result: dict[str, object] = {
            "products": product_list,
            "count": len(product_list),
        }
        if quantity is not None:
            result["quantity"] = int(quantity)
        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result=result,
        )


class GetProductDetailsTool:
    """Retrieve authoritative details for one Kaari product."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name="get_product_details",
            description=(
                "Get full details for a specific Kaari product by product_id. "
                "Returns the authoritative product record including dimensions, "
                "material, colours, finish, and base price."
            ),
            version="v1",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The unique product identifier (e.g. 'KP-FRP-001')",
                        "minLength": 1,
                    },
                },
                "required": ["product_id"],
                "additionalProperties": False,
            },
            risk_level="low",
        )

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, object]
    ) -> ToolResult:
        product_id = str(arguments.get("product_id", ""))
        product = await self._repository.get(
            tenant_id=context.tenant_id, product_id=product_id
        )

        if product is None:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error=f"Product '{product_id}' was not found.",
                metadata={"code": "product_not_found"},
            )

        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result={
                "product_id": product.product_id,
                "product_code": product.product_code,
                "name": product.name,
                "description": product.description,
                "category": product.category,
                "dimensions": product.dimensions,
                "material": product.material,
                "colours": product.colours,
                "finish": product.finish,
                "base_price": product.base_price,
                "currency": product.currency,
                "price_display": product.price_display,
            },
        )


class GetProductPriceTool:
    """Retrieve authoritative pricing for one Kaari product."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name="get_product_price",
            description=(
                "Get the unit price and subtotal for a specific Kaari product "
                "and quantity. All pricing is retrieved from the authoritative "
                "product repository — the LLM never invents prices."
            ),
            version="v1",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The unique product identifier (e.g. 'KP-FRP-001')",
                        "minLength": 1,
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of units required.",
                        "minimum": 1,
                    },
                },
                "required": ["product_id", "quantity"],
                "additionalProperties": False,
            },
            risk_level="low",
        )

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, object]
    ) -> ToolResult:
        product_id = str(arguments.get("product_id", ""))
        quantity = int(arguments.get("quantity", 1))

        if quantity < 1:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error="Quantity must be at least 1.",
                metadata={"code": "invalid_quantity"},
            )

        product = await self._repository.get(
            tenant_id=context.tenant_id, product_id=product_id
        )

        if product is None:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error=f"Product '{product_id}' was not found.",
                metadata={"code": "product_not_found"},
            )

        unit_price = product.base_price
        subtotal = unit_price * quantity

        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result={
                "product_id": product.product_id,
                "product_name": product.name,
                "unit_price": unit_price,
                "currency": product.currency,
                "quantity": quantity,
                "subtotal": subtotal,
                "price_display": f"{product.currency} {subtotal:,.2f}",
            },
        )
