"""In-memory repositories for Kaari products and leads."""

from __future__ import annotations

from decimal import Decimal

from agent_service.kaari.models import Product, ProductVariant, SalesLead


class ProductRepository:
    """In-memory product lookup scoped by tenant."""

    def __init__(self) -> None:
        self._products: dict[tuple[str, str], Product] = {}

    def seed(self, products: list[Product]) -> None:
        """Load initial product data."""
        for product in products:
            self._products[(product.tenant_id, product.product_id)] = product

    async def get(self, *, tenant_id: str, product_id: str) -> Product | None:
        """Load one product within its tenant boundary."""
        return self._products.get((tenant_id, product_id))

    async def get_variant(
        self, *, tenant_id: str, product_id: str, variant_id: str
    ) -> tuple[Product, ProductVariant] | None:
        """Load a specific variant within its tenant boundary."""
        product = self._products.get((tenant_id, product_id))
        if product is None:
            return None
        variant = product.get_variant(variant_id)
        if variant is None:
            return None
        return product, variant

    async def search(
        self,
        *,
        tenant_id: str,
        query: str = "",
        collection: str | None = None,
        size: str | None = None,
        colour: str | None = None,
        finish: str | None = None,
        texture: str | None = None,
        height_min: Decimal | None = None,
        height_max: Decimal | None = None,
        active_only: bool = True,
    ) -> list[Product]:
        """Search products by text query, collection, size, colour, finish, texture, and height."""
        results: list[Product] = []
        query_lower = query.lower().strip()

        for key, product in self._products.items():
            if key[0] != tenant_id:
                continue
            if active_only and not product.active:
                continue

            if collection and product.collection and product.collection.lower() != collection.lower():
                continue

            if colour:
                colour_lower = colour.lower()
                if not any(colour_lower in c.lower() for c in product.all_colours):
                    continue

            if finish:
                finish_lower = finish.lower()
                if not any(finish_lower in f.lower() for f in product.all_finishes):
                    continue

            if texture:
                texture_lower = texture.lower()
                if not any(texture_lower in t.lower() for t in product.all_textures):
                    continue

            if height_min is not None or height_max is not None:
                heights = []
                for v in product.variants:
                    if v.height is not None:
                        heights.append(v.height)
                if not heights:
                    continue
                max_h = max(heights)
                min_h = min(heights)
                if height_min is not None and max_h < height_min:
                    continue
                if height_max is not None and min_h > height_max:
                    continue

            if size:
                size_lower = size.lower()
                size_match = False
                for v in product.variants:
                    if size_lower in v.size_label.lower():
                        size_match = True
                        break
                    if v.height is not None and size_lower in str(v.height):
                        size_match = True
                        break
                    if v.upper_diameter is not None and size_lower in str(v.upper_diameter):
                        size_match = True
                        break
                if not size_match:
                    continue

            if query_lower:
                searchable = " ".join([
                    product.model_name,
                    product.description,
                    product.collection or "",
                    product.material,
                    *product.all_colours,
                    *product.all_finishes,
                    *product.all_textures,
                    *[v.size_label for v in product.variants],
                ]).lower()
                if query_lower not in searchable:
                    continue

            results.append(product)
        return results

    async def list_all(self, *, tenant_id: str, active_only: bool = True) -> list[Product]:
        """Return all products for a tenant."""
        return [
            p
            for (tid, _), p in self._products.items()
            if tid == tenant_id and (not active_only or p.active)
        ]


class LeadRepository:
    """In-memory lead persistence scoped by tenant."""

    def __init__(self) -> None:
        self._leads: dict[tuple[str, str], SalesLead] = {}
        self._sequence: int = 0

    async def create(self, lead: SalesLead) -> SalesLead:
        """Persist a new sales lead."""
        self._sequence += 1
        key = (lead.tenant_id, lead.lead_id)
        self._leads[key] = lead
        return lead

    async def get(self, *, tenant_id: str, lead_id: str) -> SalesLead | None:
        """Load one lead within its tenant boundary."""
        return self._leads.get((tenant_id, lead_id))

    async def list_by_tenant(self, *, tenant_id: str) -> list[SalesLead]:
        """Return all leads for a tenant."""
        return [lead for (_, tid), lead in self._leads.items() if tid == tenant_id]
