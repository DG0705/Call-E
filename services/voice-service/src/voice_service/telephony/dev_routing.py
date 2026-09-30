"""Development-only inbound routing for the phone-call MVP.

This is deliberately small and non-generic: it resolves an inbound extension
(or external DID) to a tenant and agent so a developer can place a real call
that reaches an AI employee without building a routing engine. The default
mapping preserves the original Kaari demo; tenant and agent overrides (via
explicit arguments or environment) route any extension to any employee.
"""

import os

from call_e_shared.exceptions import PlatformError

KAARI_TENANT_ID = "kaari-planters"
KAARI_AGENT_ID = "kaari-sales-agent"

KAARI_DEV_EXTENSION_ENV = "KAARI_DEV_EXTENSION"
KAARI_DEV_TENANT_ENV = "KAARI_DEV_TENANT_ID"
KAARI_DEV_AGENT_ENV = "KAARI_DEV_AGENT_ID"
DEFAULT_KAARI_DEV_EXTENSION = "1000"

_INBOUND_EXTENSION_UNMAPPED = "inbound_extension_unmapped"


class DevInboundRoute:
    """Resolved tenant and agent identifiers for one inbound destination."""

    def __init__(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        destination_number: str,
    ) -> None:
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.destination_number = destination_number


class KaariDevRouter:
    """Route a dev inbound extension/DID to a tenant and agent."""

    def __init__(
        self,
        kaari_extension: str,
        *,
        tenant_id: str = KAARI_TENANT_ID,
        agent_id: str = KAARI_AGENT_ID,
    ) -> None:
        self._kaari_extension = kaari_extension.strip()
        self._tenant_id = tenant_id
        self._agent_id = agent_id

    def resolve(
        self,
        *,
        destination_number: str,
        tenant_id: str | None = None,
        agent_id: str | None = None,
    ) -> DevInboundRoute:
        """Return the tenant/agent pair for an inbound destination.

        Explicit ``tenant_id``/``agent_id`` take precedence so the route can
        target a specific agent during development. Otherwise the configured
        extension resolves to the configured default tenant and agent,
        preserving the caller-supplied destination as the DID.
        """
        if tenant_id and agent_id:
            return DevInboundRoute(
                tenant_id=tenant_id,
                agent_id=agent_id,
                destination_number=destination_number,
            )
        if destination_number.strip() != self._kaari_extension:
            raise PlatformError(
                code=_INBOUND_EXTENSION_UNMAPPED,
                message=(
                    f"Inbound extension '{destination_number}' is not mapped for "
                    "development. Use extension "
                    f"'{self._kaari_extension}' or supply tenant_id and agent_id."
                ),
                status_code=404,
            )
        return DevInboundRoute(
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            destination_number=destination_number,
        )

    @staticmethod
    def from_environment() -> "KaariDevRouter":
        """Build the dev router from the service environment."""
        return KaariDevRouter(
            os.getenv(KAARI_DEV_EXTENSION_ENV, DEFAULT_KAARI_DEV_EXTENSION),
            tenant_id=os.getenv(KAARI_DEV_TENANT_ENV, KAARI_TENANT_ID),
            agent_id=os.getenv(KAARI_DEV_AGENT_ENV, KAARI_AGENT_ID),
        )
