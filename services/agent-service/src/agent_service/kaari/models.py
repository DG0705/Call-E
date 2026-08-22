"""Kaari Planters domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field


PRODUCTS_COLLECTION = "kaari_products"
LEADS_COLLECTION = "kaari_leads"

LeadStatus = Literal["new", "qualified", "contacted", "converted", "closed"]

KNOWN_COLLECTIONS = [
    "Neo",
    "Heritage",
    "Linea",
]

KNOWN_FINISHES = [
    "Matte",
    "Gloss",
    "Orange Peel",
    "Sand",
    "Sand & Dotted",
    "Stone Texture",
    "Concrete",
    "Distressed Ink",
]

KNOWN_TEXTURES = [
    "Matte",
    "Glossy",
    "Orange Peel",
    "Sand",
    "Sand & Dotted",
    "Stone Texture",
    "Concrete",
    "Distressed Ink",
    "Rim - Glossy, Body - Matte",
]


class ProductVariant(BaseModel):
    """A single size variant of a Kaari product model."""

    variant_id: str
    size_label: str
    upper_diameter: Decimal | None = None
    lower_diameter: Decimal | None = None
    height: Decimal | None = None
    length: Decimal | None = None
    width: Decimal | None = None
    dimensions_unit: str = "inch"
    listed_price: Decimal
    currency: str = "INR"
    colours: list[str] = Field(default_factory=list)
    finish: str = ""
    texture: str = ""
    catalog_page: int | None = None
    active: bool = True
    metadata: dict[str, object] = Field(default_factory=dict)

    @computed_field
    @property
    def price_display(self) -> str:
        """Human-readable formatted price."""
        return f"\u20b9{self.listed_price:,.0f}"

    @computed_field
    @property
    def dimensions_summary(self) -> str:
        """Human-readable dimensions."""
        if self.upper_diameter is not None and self.lower_diameter is not None and self.height is not None:
            return f"UD {self.upper_diameter}\" x BD {self.lower_diameter}\" x H {self.height}\""
        if self.length is not None and self.width is not None and self.height is not None:
            return f"L {self.length}\" x W {self.width}\" x H {self.height}\""
        return ""


class Product(BaseModel):
    """A tenant-scoped Kaari product model with one or more size variants."""

    product_id: str
    tenant_id: str
    model_name: str
    collection: str | None = None
    description: str = ""
    category: str = "Planter"
    material: str = "FRP (Fibreglass Reinforced Plastic)"
    variants: list[ProductVariant] = Field(default_factory=list)
    active: bool = True
    catalog_version: str = "2026"
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_variant(self, variant_id: str) -> ProductVariant | None:
        """Find a variant by its ID."""
        for v in self.variants:
            if v.variant_id == variant_id:
                return v
        return None

    def get_variant_by_size(self, size_label: str) -> ProductVariant | None:
        """Find a variant by its size label."""
        for v in self.variants:
            if v.size_label.lower() == size_label.lower():
                return v
        return None

    @computed_field
    @property
    def min_price(self) -> Decimal | None:
        """Lowest price across all variants."""
        if not self.variants:
            return None
        return min(v.listed_price for v in self.variants)

    @computed_field
    @property
    def max_price(self) -> Decimal | None:
        """Highest price across all variants."""
        if not self.variants:
            return None
        return max(v.listed_price for v in self.variants)

    @computed_field
    @property
    def price_range_display(self) -> str:
        """Human-readable price range."""
        if self.min_price is None:
            return ""
        if self.min_price == self.max_price:
            return f"\u20b9{self.min_price:,.0f}"
        return f"\u20b9{self.min_price:,.0f} \u2013 \u20b9{self.max_price:,.0f}"

    @computed_field
    @property
    def all_colours(self) -> list[str]:
        """Deduplicated list of all colours across variants."""
        seen: set[str] = set()
        colours: list[str] = []
        for v in self.variants:
            for c in v.colours:
                if c not in seen:
                    seen.add(c)
                    colours.append(c)
        return colours

    @computed_field
    @property
    def all_finishes(self) -> list[str]:
        """Deduplicated list of all finishes across variants."""
        seen: set[str] = set()
        finishes: list[str] = []
        for v in self.variants:
            if v.finish and v.finish not in seen:
                seen.add(v.finish)
                finishes.append(v.finish)
        return finishes

    @computed_field
    @property
    def all_textures(self) -> list[str]:
        """Deduplicated list of all textures across variants."""
        seen: set[str] = set()
        textures: list[str] = []
        for v in self.variants:
            if v.texture and v.texture not in seen:
                seen.add(v.texture)
                textures.append(v.texture)
        return textures


class SalesLead(BaseModel):
    """A tenant-scoped sales lead captured during a conversation."""

    lead_id: str
    tenant_id: str
    customer_name: str
    phone: str
    email: str | None = None
    company: str | None = None
    location: str | None = None
    interested_products: list[str] = Field(default_factory=list)
    quantity: int = 0
    requirements: str = ""
    preferred_colours: list[str] = Field(default_factory=list)
    preferred_finish: str | None = None
    preferred_texture: str | None = None
    budget: Decimal | None = None
    estimated_value: Decimal | None = None
    source: str = "phone"
    status: LeadStatus = "new"
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CatalogImportWarning(BaseModel):
    """A warning generated during catalog import."""

    page: int
    model_name: str | None = None
    message: str


class CatalogImportSummary(BaseModel):
    """Summary of a catalog import run."""

    catalog_version: str
    pages_processed: int = 0
    products_created: int = 0
    products_updated: int = 0
    products_skipped: int = 0
    warnings: list[CatalogImportWarning] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    total_products: int = 0
    total_variants: int = 0
