"""Kaari Planters domain models."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field


PRODUCTS_COLLECTION = "kaari_products"
LEADS_COLLECTION = "kaari_leads"

LeadStatus = Literal["new", "qualified", "contacted", "converted", "closed"]


class Product(BaseModel):
    """A tenant-scoped Kaari product with authoritative pricing."""

    product_id: str
    tenant_id: str
    product_code: str
    name: str
    description: str
    category: str
    dimensions: str
    material: str
    colours: list[str] = Field(default_factory=list)
    finish: str = ""
    base_price: float
    currency: str = "INR"
    active: bool = True
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def price_display(self) -> str:
        """Human-readable formatted price."""
        return f"{self.currency} {self.base_price:,.2f}"


class SalesLead(BaseModel):
    """A tenant-scoped sales lead captured during a conversation."""

    lead_id: str
    tenant_id: str
    customer_name: str
    phone: str
    email: str | None = None
    company: str | None = None
    requirements: str
    interested_products: list[str] = Field(default_factory=list)
    quantity: int = 0
    source: str = "phone"
    status: LeadStatus = "new"
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
