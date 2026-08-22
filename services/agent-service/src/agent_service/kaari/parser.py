"""Kaari 2026 catalog PDF parser.

Extracts product data from the Kaari catalog PDF into normalized records.

Dimension column headings normalize as:
- UD / UD/L -> upper_diameter
- BD / BD/W -> lower_diameter
- H -> height
- L / W / H (Rectangle/Cube) -> length / width / height

All measurements are in inches as stated by the catalog.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from agent_service.kaari.models import CatalogImportWarning, Product, ProductVariant


CATALOG_VERSION = "2026"
TENANT_ID = "kaari-planters"

_PRICE_RE = re.compile(r"\u20b9\s*([\d,]+)")

_COLLECTION_PAGES: dict[str, tuple[int, int]] = {
    "Neo": (7, 47),
    "Heritage": (49, 87),
    "Linea": (89, 117),
}


def _parse_price(text: str) -> Decimal | None:
    match = _PRICE_RE.search(text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _parse_decimal(text: str) -> Decimal | None:
    text = text.strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _resolve_collection(page_num: int) -> str | None:
    for name, (start, end) in _COLLECTION_PAGES.items():
        if start <= page_num <= end:
            return name
    return None


def _classify_texture(text: str) -> str:
    text_upper = text.strip().upper()
    for t in [
        "ORANGE PEEL", "SAND & DOTTED", "SAND", "STONE TEXTURE",
        "CONCRETE", "DISTRESSED INK", "MATTE", "GLOSSY", "GLOSS",
    ]:
        if t in text_upper:
            return t.title() if t != "ORANGE PEEL" else "Orange Peel"
    return ""


def _extract_ral_colours(text: str) -> list[str]:
    colours = []
    for match in re.finditer(r"RAL\s+\d+\s*\n?\s*([A-Z][A-Z\s]+)", text):
        colour = match.group(1).strip().title()
        if colour not in colours:
            colours.append(colour)
    return colours


def _is_pricing_page(text: str) -> bool:
    upper = text.upper()
    return "PRICE" in upper and ("UD" in upper or "BD" in upper or "SET" in upper or "\nL\n" in upper or "L " in upper)


def _is_model_entry(text: str) -> bool:
    return bool(re.match(r"^[A-Z][A-Z\s]*\s+\d+[A-Z]?\s*$", text.strip()))


def parse_pricing_page(text: str, page_num: int) -> tuple[list[dict[str, object]], list[CatalogImportWarning]]:
    """Parse a pricing table page into raw variant records."""
    warnings: list[CatalogImportWarning] = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    price_idx = None
    for i, line in enumerate(lines):
        if line.upper() == "PRICE":
            price_idx = i
            break

    if price_idx is None:
        warnings.append(CatalogImportWarning(
            page=page_num, message="No PRICE header found on pricing page"
        ))
        return [], warnings

    header_text = " ".join(lines[:price_idx]).upper()
    is_rectangular = ("L " in header_text or "L\n" in header_text or "SET L" in header_text) and "UD" not in header_text

    model_entries: list[str] = []
    price_values: list[Decimal] = []
    dim_rows: list[list[Decimal]] = []

    data_lines = lines[price_idx + 1:]

    skip_words = {
        "RAL", "NEO", "HERITAGE", "LINEA", "COLLECTION", "CO L L E CT I O N",
        "UD - UPPER DIA, BD - BOTTOM DIA, H - HEIGHT", "MEASUREMENTS IN INCH",
        "SET", "PRICE",
    }

    for line in data_lines:
        upper = line.upper()

        if upper in skip_words or upper.startswith("RAL "):
            continue
        if re.match(r"^[A-Z][A-Z\s]+$", line) and len(line) < 25:
            continue

        p = _parse_price(line)
        if p is not None:
            price_values.append(p)
            continue

        parts = line.split()
        if not parts:
            continue

        if _is_model_entry(line):
            model_entries.append(parts[0])
            continue

        if parts[0].upper() in ("UD", "BD", "H", "L", "W", "UD/L", "BD/W"):
            continue

        nums: list[Decimal] = []
        for part in parts:
            d = _parse_decimal(part)
            if d is not None:
                nums.append(d)
            else:
                break
        else:
            if len(nums) >= 3:
                dim_rows.append(nums[:3])
            continue

    if len(model_entries) != len(price_values):
        warnings.append(CatalogImportWarning(
            page=page_num,
            message=f"Mismatch: {len(model_entries)} models vs {len(price_values)} prices",
        ))

    min_count = min(len(model_entries), len(price_values), len(dim_rows))

    variants: list[dict[str, object]] = []
    for i in range(min_count):
        model_entry = model_entries[i]
        parts = model_entry.split()
        model_name = parts[0] if parts else model_entry
        size_label = parts[1] if len(parts) > 1 else ""

        dims = dim_rows[i]
        variant: dict[str, object] = {
            "model_name": model_name,
            "size_label": size_label,
            "price": price_values[i],
            "is_rectangular": is_rectangular,
        }

        if is_rectangular:
            variant["length"] = dims[0]
            variant["width"] = dims[1]
            variant["height"] = dims[2]
        else:
            variant["upper_diameter"] = dims[0]
            variant["lower_diameter"] = dims[1]
            variant["height"] = dims[2]

        variants.append(variant)

    return variants, warnings


def parse_image_page(text: str, page_num: int) -> dict[str, str]:
    """Parse an image page to extract model-name -> texture mapping."""
    result: dict[str, str] = {}
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and re.match(r"^[A-Z]", parts[0]):
            model = parts[0]
            texture = " ".join(parts[1:])
            if re.match(r"\d+", texture):
                continue
            result[model] = texture
    return result


def parse_catalog_pdf(pdf_path: str | Path) -> tuple[list[Product], list[CatalogImportWarning]]:
    """Parse the full Kaari catalog PDF into Product objects."""
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore[no-redef]
        except ImportError:
            raise ImportError("pymupdf is required for PDF parsing. Install with: uv pip install pymupdf")

    doc = pymupdf.open(str(pdf_path))
    warnings: list[CatalogImportWarning] = []
    all_variants: list[dict[str, object]] = []

    for page_idx in range(doc.page_count):
        page_num = page_idx + 1
        text = doc[page_idx].get_text()

        if not text.strip():
            continue

        if _is_pricing_page(text):
            page_variants, page_warnings = parse_pricing_page(text, page_num)
            all_variants.extend(page_variants)
            warnings.extend(page_warnings)

    products_dict: dict[str, dict[str, object]] = {}
    for v in all_variants:
        model_name = str(v["model_name"])
        collection = None
        for coll, (start, end) in _COLLECTION_PAGES.items():
            pass

        if model_name not in products_dict:
            products_dict[model_name] = {
                "model_name": model_name,
                "variants": [],
            }
        products_dict[model_name]["variants"].append(v)

    products: list[Product] = []
    for model_name, data in products_dict.items():
        raw_variants = data["variants"]
        collection = None
        for coll, (start, end) in _COLLECTION_PAGES.items():
            for v in raw_variants:
                if isinstance(v.get("catalog_page"), int):
                    if start <= v["catalog_page"] <= end:
                        collection = coll
                        break

        product_variants: list[ProductVariant] = []
        for v in raw_variants:
            vid = f"{model_name}-{v['size_label']}"
            is_rect = v.get("is_rectangular", False)

            pv = ProductVariant(
                variant_id=vid,
                size_label=str(v["size_label"]),
                listed_price=v["price"],
                currency="INR",
                dimensions_unit="inch",
                finish=_classify_texture(str(v.get("texture", ""))),
                texture=str(v.get("texture", "")),
            )

            if is_rect:
                pv.length = v.get("length")
                pv.width = v.get("width")
                pv.height = v.get("height")
            else:
                pv.upper_diameter = v.get("upper_diameter")
                pv.lower_diameter = v.get("lower_diameter")
                pv.height = v.get("height")

            product_variants.append(pv)

        product = Product(
            product_id=f"KP-{model_name}",
            tenant_id=TENANT_ID,
            model_name=model_name,
            collection=collection,
            variants=product_variants,
            catalog_version=CATALOG_VERSION,
        )
        products.append(product)

    return products, warnings
