"""Kaari 2026 catalog loader.

Loads the real Kaari retail catalog from pre-extracted seed data.
Each product model contains one or more size variants with exact catalog prices,
dimensions (in inches), colours, and finishes from the official 2026 retail catalog.

Pricing policy (confirmed by Kaari):
  1-3 pots: 20-25% discount (indicative range)
  4-19 pots: 30% discount (fixed)
  20+ pots: bulk quote required, human-confirmed
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from agent_service.kaari.models import Product, ProductVariant

KAARI_TENANT_ID = "kaari-planters"
CATALOG_VERSION = "2026"

_SEED_PATH = Path(__file__).parent / "catalog_seed.json"


def load_catalog_from_json(path: Path | None = None) -> list[Product]:
    """Load the real Kaari catalog from the pre-extracted JSON seed file."""
    seed_path = path or _SEED_PATH
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    products: list[Product] = []
    for entry in raw:
        variants: list[ProductVariant] = []
        for v in entry["variants"]:
            pv = ProductVariant(
                variant_id=v["variant_id"],
                size_label=v["size_label"],
                listed_price=Decimal(str(v["listed_price"])),
                currency=v.get("currency", "INR"),
                dimensions_unit=v.get("dimensions_unit", "inch"),
                colours=v.get("colours", []),
                finish=v.get("finish", ""),
                texture=v.get("texture", ""),
                catalog_page=v.get("catalog_page"),
            )
            if "upper_diameter" in v:
                pv.upper_diameter = Decimal(str(v["upper_diameter"]))
            if "lower_diameter" in v:
                pv.lower_diameter = Decimal(str(v["lower_diameter"]))
            if "height" in v:
                pv.height = Decimal(str(v["height"]))
            if "length" in v:
                pv.length = Decimal(str(v["length"]))
            if "width" in v:
                pv.width = Decimal(str(v["width"]))
            variants.append(pv)

        product = Product(
            product_id=entry["product_id"],
            tenant_id=entry.get("tenant_id", KAARI_TENANT_ID),
            model_name=entry["model_name"],
            collection=entry.get("collection"),
            description=entry.get("description", ""),
            variants=variants,
            catalog_version=entry.get("catalog_version", CATALOG_VERSION),
        )
        products.append(product)
    return products


def kaari_product_catalog() -> list[Product]:
    """Return the real 2026 Kaari retail catalog."""
    return load_catalog_from_json()
