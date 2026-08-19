"""In-memory knowledge retriever for Kaari Planters."""

from __future__ import annotations

from agent_service.runtime.knowledge import RetrievedKnowledge

KAARI_TENANT_ID = "kaari-planters"

_KNOWLEDGE_CHUNKS: list[dict[str, str]] = [
    {
        "chunk_id": "kaari-about",
        "content": (
            "Kaari Planters is a manufacturer of premium fibreglass reinforced plastic (FRP) planters "
            "based in India. The company designs and produces planters for residential, commercial, and "
            "hospitality landscaping. All products are manufactured in-house using high-quality FRP material."
        ),
    },
    {
        "chunk_id": "kaari-material",
        "content": (
            "FRP (Fibreglass Reinforced Plastic) is a composite material that is lightweight, strong, "
            "and weather-resistant. Kaari FRP planters are UV-stable, frost-resistant, and corrosion-proof. "
            "They are suitable for both indoor and outdoor environments. FRP does not rust or degrade like "
            "metal or concrete planters."
        ),
    },
    {
        "chunk_id": "kaari-categories",
        "content": (
            "Kaari product categories include: Trough Planters, Round Planters, Column Planters, "
            "Wall Planters, Desktop Planters, Outdoor Planters, and Custom Planters. Each category "
            "covers multiple sizes and colour options."
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
        "chunk_id": "kaari-colours-finishes",
        "content": (
            "Standard colour options include White, Charcoal, Matte Black, Gloss White, Terracotta, "
            "Sage Green, Olive, Anthracite, Navy Blue, and Pastel Pink. Custom RAL colours are available "
            "for orders of 10 or more planters. Finishes include Matte, Gloss, and Textured."
        ),
    },
    {
        "chunk_id": "kaari-customisation",
        "content": (
            "Kaari offers fully customisable FRP planters. Customers can specify dimensions, colours, "
            "finish, and even branding. Custom orders have a minimum quantity of 10 units and a lead "
            "time of approximately 21 business days."
        ),
    },
    {
        "chunk_id": "kaari-sizes",
        "content": (
            "Standard planter sizes range from 15cm desktop planters to 80cm large outdoor planters. "
            "Dimensions are specified as length x width x height for rectangular planters or diameter x "
            "height for round planters. Custom dimensions are available on request."
        ),
    },
    {
        "chunk_id": "kaari-pricing",
        "content": (
            "All pricing on the Kaari product catalog is in Indian Rupees (INR). Prices shown are per-unit "
            "base prices. Volume discounts may be available for bulk orders. Custom planter pricing depends "
            "on specifications and order quantity."
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
        "chunk_id": "kaari-enquiry-faq",
        "content": (
            "Common enquiry topics: minimum order quantities (1 for standard, 10 for custom), delivery "
            "timeline (standard stock ships within 5-7 business days, custom orders 21 business days), "
            "payment terms (advance payment for custom orders), and warranty (1 year manufacturing "
            "defect warranty on all FRP products)."
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
