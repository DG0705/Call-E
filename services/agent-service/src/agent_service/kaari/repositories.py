"""In-memory repositories for Kaari products and leads."""

from __future__ import annotations

from agent_service.kaari.models import Product, SalesLead


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

    async def search(
        self,
        *,
        tenant_id: str,
        query: str = "",
        category: str | None = None,
        size: str | None = None,
        active_only: bool = True,
    ) -> list[Product]:
        """Search products by text query, category, and size."""
        results: list[Product] = []
        query_lower = query.lower().strip()
        for key, product in self._products.items():
            if key[0] != tenant_id:
                continue
            if active_only and not product.active:
                continue
            if category and product.category.lower() != category.lower():
                continue
            if size and size.lower() not in product.dimensions.lower():
                continue
            if query_lower:
                searchable = " ".join(
                    [
                        product.name,
                        product.description,
                        product.category,
                        product.material,
                        product.finish,
                        *product.colours,
                    ]
                ).lower()
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
