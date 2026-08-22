"""Kaari Planters retail pricing engine.

Implements the confirmed Kaari retail discount policy with Decimal-safe arithmetic.

Pricing tiers:
  1-3 pots: 20-25% discount (indicative range)
  4-19 pots: 30% discount (exact)
  20+ pots: bulk quote required, human-confirmed

The LLM must never invent prices. All pricing goes through this engine.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from agent_service.kaari.models import Product, ProductVariant


DISCOUNT_TIER_1_MIN = Decimal("0.20")
DISCOUNT_TIER_1_MAX = Decimal("0.25")
DISCOUNT_TIER_2 = Decimal("0.30")
BULK_THRESHOLD = Decimal("20")


def calculate_retail_price(
    *,
    product: Product,
    variant: ProductVariant,
    quantity: int,
) -> dict[str, object]:
    """Calculate indicative retail pricing for a given product variant and quantity.

    Returns a dict with:
      - unit_list_price: catalog base price
      - quantity: ordered quantity
      - discount_policy: description of applicable discount
      - discount_min / discount_max: discount percentages
      - indicative_unit_price_min / indicative_unit_price_max: per-unit after discount
      - indicative_subtotal_min / indicative_subtotal_max: total after discount
      - currency: INR
      - bulk_quote_required: True if quantity >= 20
    """
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")

    unit_price = variant.listed_price
    qty = Decimal(quantity)

    if qty >= BULK_THRESHOLD:
        subtotal_at_list = unit_price * qty
        return {
            "unit_list_price": str(unit_price),
            "quantity": quantity,
            "discount_policy": "Bulk order (20+ units): final commercial discount confirmed by Kaari sales team.",
            "discount_min": None,
            "discount_max": None,
            "indicative_unit_price_min": None,
            "indicative_unit_price_max": None,
            "indicative_subtotal_min": None,
            "indicative_subtotal_max": None,
            "catalog_subtotal": str(subtotal_at_list),
            "currency": "INR",
            "bulk_quote_required": True,
            "message": (
                f"For {quantity} units, the catalog list price is {variant.price_display} per unit "
                f"(subtotal: {variant.currency} {subtotal_at_list:,.0f}). "
                "The final commercial discount for bulk orders is confirmed by Kaari's sales team. "
                "I can record your requirement and have the team provide the final offer."
            ),
        }

    if qty <= Decimal("3"):
        discounted_min = (unit_price * (Decimal("1") - DISCOUNT_TIER_1_MIN)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        discounted_max = (unit_price * (Decimal("1") - DISCOUNT_TIER_1_MAX)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        subtotal_min = (discounted_min * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal_max = (discounted_max * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "unit_list_price": str(unit_price),
            "quantity": quantity,
            "discount_policy": "1-3 units: 20-25% retail discount (indicative range).",
            "discount_min": "20%",
            "discount_max": "25%",
            "indicative_unit_price_min": str(discounted_max),
            "indicative_unit_price_max": str(discounted_min),
            "indicative_subtotal_min": str(subtotal_max),
            "indicative_subtotal_max": str(subtotal_min),
            "currency": "INR",
            "bulk_quote_required": False,
            "message": (
                f"Kaari generally offers a 20-25% retail discount for 1-3 pieces. "
                f"Based on the catalog price of {variant.price_display} per unit, "
                f"the indicative range is {variant.currency} {discounted_max:,.0f} to "
                f"{variant.currency} {discounted_min:,.0f} per unit."
            ),
        }

    discounted = (unit_price * (Decimal("1") - DISCOUNT_TIER_2)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    subtotal = (discounted * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "unit_list_price": str(unit_price),
        "quantity": quantity,
        "discount_policy": "4-19 units: 30% retail discount.",
        "discount_min": "30%",
        "discount_max": "30%",
        "indicative_unit_price_min": str(discounted),
        "indicative_unit_price_max": str(discounted),
        "indicative_subtotal_min": str(subtotal),
        "indicative_subtotal_max": str(subtotal),
        "currency": "INR",
        "bulk_quote_required": False,
        "message": (
            f"For {quantity} or more pieces, the standard retail discount is 30%. "
            f"Based on the catalog price of {variant.price_display} per unit, "
            f"the indicative price is {variant.currency} {discounted:,.0f} per unit "
            f"(subtotal: {variant.currency} {subtotal:,.0f})."
        ),
    }
