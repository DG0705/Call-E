"""Real Kaari 2026 catalog seed data extracted from the official PDF.

Each product has its exact catalog name, collection, sizes, dimensions (in inches),
prices (INR), colours, and finishes as printed in the 2026 retail catalog.

Pricing policy:
  1-3 pots: 20-25% discount (indicative range)
  4-19 pots: 30% discount (fixed)
  20+ pots: bulk quote required, human-confirmed
"""

from __future__ import annotations

from decimal import Decimal

from agent_service.kaari.models import Product, ProductVariant

KAARI_TENANT_ID = "kaari-planters"
CATALOG_VERSION = "2026"


def _v(
    *,
    model: str,
    size: str,
    price: int,
    ud: float | None = None,
    bd: float | None = None,
    h: float | None = None,
    l: float | None = None,
    w: float | None = None,
    colours: list[str] | None = None,
    finish: str = "",
    page: int = 0,
) -> ProductVariant:
    vid = f"{model}-{size}"
    pv = ProductVariant(
        variant_id=vid,
        size_label=size,
        listed_price=Decimal(price),
        currency="INR",
        dimensions_unit="inch",
        colours=colours or [],
        finish=finish,
        texture=finish,
        catalog_page=page,
    )
    if l is not None and w is not None:
        pv.length = Decimal(str(l))
        pv.width = Decimal(str(w))
    elif ud is not None and bd is not None:
        pv.upper_diameter = Decimal(str(ud))
        pv.lower_diameter = Decimal(str(bd))
    if h is not None:
        pv.height = Decimal(str(h))
    return pv


def _p(
    *,
    model: str,
    collection: str,
    variants: list[ProductVariant],
    description: str = "",
) -> Product:
    return Product(
        product_id=f"KP-{model}",
        tenant_id=KAARI_TENANT_ID,
        model_name=model,
        collection=collection,
        description=description or f"Kaari {model} planter from the {collection} collection.",
        variants=variants,
        catalog_version=CATALOG_VERSION,
    )
