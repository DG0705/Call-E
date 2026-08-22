"""Kaari Planters product tools for the agent tool engine."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from agent_service.kaari.pricing import calculate_retail_price
from agent_service.kaari.repositories import ProductRepository
from agent_service.runtime.tools import (
    ToolDefinition,
    ToolExecutionContext,
    ToolResult,
    Tool,
)


class SearchProductsTool:
    """Search the Kaari product catalog by query, collection, colour, finish, texture, and size."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name="search_products",
            description=(
                "Search Kaari FRP planter products by text query, collection, "
                "colour, finish, texture, and size. Returns matching products "
                "with model names, variants, dimensions, and listed prices. "
                "Use this to find relevant products for a customer enquiry."
            ),
            version="v2",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search query (e.g. 'outdoor planter', 'tall white')",
                    },
                    "collection": {
                        "type": "string",
                        "description": "Filter by collection: 'Neo', 'Heritage', or 'Linea'.",
                    },
                    "size": {
                        "type": "string",
                        "description": "Optional size keyword to match (e.g. '24', 'large', '40 inch').",
                    },
                    "colour": {
                        "type": "string",
                        "description": "Filter by colour (e.g. 'Pure White', 'Black Grey').",
                    },
                    "finish": {
                        "type": "string",
                        "description": "Filter by finish (e.g. 'Matte', 'Concrete', 'Orange Peel').",
                    },
                    "texture": {
                        "type": "string",
                        "description": "Filter by texture (e.g. 'Stone Texture', 'Sand').",
                    },
                    "height_min": {
                        "type": "number",
                        "description": "Minimum height in inches.",
                    },
                    "height_max": {
                        "type": "number",
                        "description": "Maximum height in inches.",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Optional expected quantity, included in results for reference.",
                        "minimum": 1,
                    },
                },
                "additionalProperties": False,
            },
            risk_level="low",
        )

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, object]
    ) -> ToolResult:
        query = str(arguments.get("query", ""))
        collection = arguments.get("collection")
        size = arguments.get("size")
        colour = arguments.get("colour")
        finish = arguments.get("finish")
        texture = arguments.get("texture")
        quantity = arguments.get("quantity")

        height_min = None
        if "height_min" in arguments and arguments["height_min"] is not None:
            try:
                height_min = Decimal(str(arguments["height_min"]))
            except (InvalidOperation, ValueError):
                pass

        height_max = None
        if "height_max" in arguments and arguments["height_max"] is not None:
            try:
                height_max = Decimal(str(arguments["height_max"]))
            except (InvalidOperation, ValueError):
                pass

        products = await self._repository.search(
            tenant_id=context.tenant_id,
            query=query,
            collection=str(collection) if collection else None,
            size=str(size) if size else None,
            colour=str(colour) if colour else None,
            finish=str(finish) if finish else None,
            texture=str(texture) if texture else None,
            height_min=height_min,
            height_max=height_max,
        )

        if not products:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=True,
                result={
                    "products": [],
                    "count": 0,
                    "message": "No products found matching your criteria.",
                },
            )

        product_list = []
        for p in products:
            variant_data = []
            for v in p.variants:
                vd: dict[str, object] = {
                    "variant_id": v.variant_id,
                    "size_label": v.size_label,
                    "listed_price": str(v.listed_price),
                    "price_display": v.price_display,
                    "colours": v.colours,
                    "finish": v.finish,
                    "dimensions": v.dimensions_summary,
                }
                variant_data.append(vd)

            product_list.append({
                "product_id": p.product_id,
                "model_name": p.model_name,
                "collection": p.collection,
                "description": p.description,
                "price_range": p.price_range_display,
                "colours": p.all_colours,
                "finishes": p.all_finishes,
                "variants": variant_data,
            })

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
                "Returns the authoritative product record including all variants, "
                "dimensions, colours, finishes/textures, and listed prices."
            ),
            version="v2",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The unique product identifier (e.g. 'KP-DEW', 'KP-ARLO')",
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

        variants = []
        for v in product.variants:
            variants.append({
                "variant_id": v.variant_id,
                "size_label": v.size_label,
                "dimensions": v.dimensions_summary,
                "listed_price": str(v.listed_price),
                "price_display": v.price_display,
                "colours": v.colours,
                "finish": v.finish,
                "texture": v.texture,
                "catalog_page": v.catalog_page,
            })

        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result={
                "product_id": product.product_id,
                "model_name": product.model_name,
                "collection": product.collection,
                "description": product.description,
                "material": product.material,
                "price_range": product.price_range_display,
                "colours": product.all_colours,
                "finishes": product.all_finishes,
                "textures": product.all_textures,
                "variants": variants,
                "made_to_order": True,
                "catalog_version": product.catalog_version,
            },
        )


class CalculateRetailPriceTool:
    """Calculate indicative retail pricing using the confirmed Kaari discount policy."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name="calculate_retail_price",
            description=(
                "Calculate the indicative retail price for a Kaari product variant "
                "given a quantity. Uses the confirmed discount tiers: "
                "1-3 units (20-25% range), 4-19 units (30%), 20+ units (bulk quote required). "
                "The LLM never invents prices."
            ),
            version="v1",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The unique product identifier (e.g. 'KP-DEW')",
                        "minLength": 1,
                    },
                    "variant_id": {
                        "type": "string",
                        "description": "The variant identifier (e.g. 'DEW-28'). If not provided, uses the first variant.",
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
        variant_id = arguments.get("variant_id")

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

        variant = None
        if variant_id:
            variant = product.get_variant(str(variant_id))
        if variant is None and product.variants:
            variant = product.variants[0]

        if variant is None:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error=f"No variant found for product '{product_id}'.",
                metadata={"code": "variant_not_found"},
            )

        pricing = calculate_retail_price(
            product=product, variant=variant, quantity=quantity
        )

        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result={
                "product_id": product.product_id,
                "model_name": product.model_name,
                "variant_id": variant.variant_id,
                "size_label": variant.size_label,
                **pricing,
            },
        )
