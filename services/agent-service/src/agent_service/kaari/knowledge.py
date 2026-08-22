"""In-memory knowledge retriever for Kaari Planters."""

from __future__ import annotations

from agent_service.runtime.knowledge import RetrievedKnowledge

KAARI_TENANT_ID = "kaari-planters"

_KNOWLEDGE_CHUNKS: list[dict[str, str]] = [
    {
        "chunk_id": "kaari-about",
        "content": (
            "Kaari Planters is a premium manufacturer of handcrafted fibreglass reinforced plastic (FRP) "
            "planters based in India. The company designs and produces planters for residential, commercial, "
            "hospitality, and landscape architecture. All products are handcrafted in-house using high-quality "
            "FRP material. Prices on the catalog are listed in Indian Rupees (INR)."
        ),
    },
    {
        "chunk_id": "kaari-material",
        "content": (
            "FRP (Fibreglass Reinforced Plastic) is a composite material that is lightweight, strong, "
            "and weather-resistant. Kaari FRP planters are UV-stable, frost-resistant, crack-proof, "
            "rust-resistant, and corrosion-proof. They are suitable for both indoor and outdoor environments. "
            "FRP does not degrade like metal or concrete planters."
        ),
    },
    {
        "chunk_id": "kaari-collections",
        "content": (
            "Kaari has three collections: Neo (modern, geometric), Heritage (timeless, classic profiles), "
            "and Linea (minimalist, clean lines). Models include DEW, DODA, DUNE, ECHO, IOTA, KAVI, LUNA, "
            "NOVA, OVA, PARA, QUBE, RIMA, RUCHI, SARA, TARA, UDAYA, ZION, ARLO, BRIK, CAMEO, CAPE, CELLO, "
            "DOME, JADE, KAMI, KIMI, LUNA-H, OPAL, PEARL, PILLAR, SERA, VERO, ALTO, ASPEN, BOX, BOX-72, "
            "CUBE, DUO, DUO-60, DUNE, LEGO, NINA, NOVA-L, PICO, RECTANGLE, and others. Over 55 product "
            "models across the three collections."
        ),
    },
    {
        "chunk_id": "kaari-measurements",
        "content": (
            "Measurements are in inches. For round planters: UD = Upper Diameter, BD = Bottom Diameter, "
            "H = Height. For rectangular models (RECTANGLE, CUBE, LEGO, BOX): L = Length, W = Width, "
            "H = Height. All prices are in INR."
        ),
    },
    {
        "chunk_id": "kaari-colours-finishes",
        "content": (
            "Standard finishes: Matte, Gloss, Orange Peel, Sand, Sand & Dotted, Stone Texture, Concrete, "
            "Distressed Ink, Marble, and others depending on the model. Standard colours include Jet Black, "
            "Carbon Black, Dark Charcoal, Grey, Pearl Beige, Light Ivory, Pure White, Bone White, Terracotta, "
            "Red Rust, Teak, Concrete, and more. Custom RAL colours are available for orders of 10 or more "
            "planters. Colour and texture can be customized as products are handcrafted."
        ),
    },
    {
        "chunk_id": "kaari-made-to-order",
        "content": (
            "All Kaari products are made to order. There is no ready stock. Delivery timelines depend on "
            "order size and customization. Never claim stock availability. Never make unsupported promises "
            "about delivery dates. The AI agent should confirm lead times with the Kaari sales team for "
            "specific orders."
        ),
    },
    {
        "chunk_id": "kaari-pricing-policy",
        "content": (
            "Pricing tiers: 1-3 pieces: 20-25% retail discount (indicative range, the exact percentage "
            "depends on specific product and order). 4-19 pieces: 30% retail discount (exact, standard). "
            "20 or more pieces: bulk quote required, commercial discount confirmed by Kaari's sales team. "
            "Never say 'this is your final price' for bulk orders. Always use the calculate_retail_price "
            "tool for pricing. The tool returns indicative prices for small orders and a bulk_quote_required "
            "flag for 20+ pieces."
        ),
    },
    {
        "chunk_id": "kaari-customisation",
        "content": (
            "Kaari offers fully customisable FRP planters. Customers can specify dimensions, colours, "
            "finish, texture, and even branding. Custom RAL colours require a minimum of 10 pieces. "
            "Because products are handcrafted, colour and texture can be adapted to customer preferences."
        ),
    },
    {
        "chunk_id": "kaari-indoor-outdoor",
        "content": (
            "Most Kaari FRP planters are suitable for both indoor and outdoor use. Wall planters and "
            "desktop planters are recommended for sheltered outdoor or indoor placement. Large outdoor "
            "planters and trough planters are designed for full outdoor exposure including gardens, "
            "terraces, and commercial landscapes."
        ),
    },
    {
        "chunk_id": "kaari-ideal-for",
        "content": (
            "Kaari planters are ideal for: offices, co-working spaces, hotel lobbies, restaurants, "
            "residential balconies, garden landscaping, corporate campuses, retail stores, and event "
            "decor. The lightweight FRP material makes them easy to relocate and rearrange."
        ),
    },
    {
        "chunk_id": "kaari-warranty",
        "content": (
            "All Kaari FRP products carry a 1-year manufacturing defect warranty. The warranty covers "
            "manufacturing defects, not wear from misuse or improper installation."
        ),
    },
    {
        "chunk_id": "kaari-drainage",
        "content": (
            "Most Kaari planters come with pre-drilled drainage holes or include drainage accessories. "
            "Desktop planters and wall planters may require additional saucers or mounting hardware, "
            "which are sold separately."
        ),
    },
    {
        "chunk_id": "kaari-price-range",
        "content": (
            "Catalog retail prices range from around Rs 1,300 for the smallest models (e.g. ARLO variant) "
            "up to Rs 63,000 for the largest specialty models (e.g. RECTANGLE 80x32). Most mid-range "
            "planters fall between Rs 3,000 and Rs 15,000. All prices are in INR."
        ),
    },
]


class KaariKnowledgeRetriever:
    """Simple keyword-based in-memory knowledge retriever for the MVP."""

    def __init__(self, tenant_id: str = KAARI_TENANT_ID) -> None:
        self._tenant_id = tenant_id

    async def retrieve(
        self, *, tenant_id: str, agent_id: str, query: str, top_k: int = 3
    ) -> list[RetrievedKnowledge]:
        """Return relevant knowledge chunks ranked by keyword overlap."""
        if tenant_id != self._tenant_id:
            return []
        query_words = set(query.lower().split())
        scored: list[tuple[float, dict[str, str]]] = []
        for chunk in _KNOWLEDGE_CHUNKS:
            content_words = set(chunk["content"].lower().split())
            score = len(query_words & content_words) / max(len(query_words), 1)
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedKnowledge(
                document_id="kaari-knowledge",
                chunk_id=chunk["chunk_id"],
                content=chunk["content"],
                score=score,
            )
            for score, chunk in scored[:top_k]
            if score > 0
        ]
