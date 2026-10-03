"""Development-only inbound routing for the phone-call MVP.

This is deliberately small and non-generic: it resolves an inbound extension
(or external DID) to a tenant and agent so a developer can place a real call
that reaches an AI employee without building a routing engine. The default
mapping preserves the original Kaari demo; tenant and agent overrides (via
explicit arguments or environment) route any extension to any employee.
"""

import os

from call_e_shared.exceptions import PlatformError

# Original demo mapping, kept as documented reference values only. The live
# path never falls back to these: without explicit tenant/agent configuration
# (constructor args or DEV_INBOUND_* environment) the extension is unmapped.
KAARI_TENANT_ID = "kaari-planters"
KAARI_AGENT_ID = "kaari-sales-agent"

# Preferred generic names. KAARI_DEV_* are deprecated aliases kept only so
# existing development setups keep resolving without reconfiguration.
DEV_INBOUND_EXTENSION_ENV = "DEV_INBOUND_EXTENSION"
DEV_INBOUND_TENANT_ENV = "DEV_INBOUND_TENANT_ID"
DEV_INBOUND_AGENT_ENV = "DEV_INBOUND_AGENT_ID"

KAARI_DEV_EXTENSION_ENV = "KAARI_DEV_EXTENSION"
KAARI_DEV_TENANT_ENV = "KAARI_DEV_TENANT_ID"
KAARI_DEV_AGENT_ENV = "KAARI_DEV_AGENT_ID"
DEFAULT_KAARI_DEV_EXTENSION = "1000"

_INBOUND_EXTENSION_UNMAPPED = "inbound_extension_unmapped"


def _first_env(*names: str, default: str) -> str:
    """Return the first non-empty environment value, else ``default``.

    Empty strings are treated as unset so a compose file that passes an empty
    override can never blank out the resolved route.
    """
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default


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


class DevInboundRouter:
    """Route a dev inbound extension/DID to a tenant and agent."""

    def __init__(
        self,
        extension: str,
        *,
        tenant_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._extension = extension.strip()
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
        preserving the caller-supplied destination as the DID. There is no
        silent fallback: an unmapped extension or a configured extension
        without a configured tenant/agent raises unmapped.
        """
        if tenant_id and agent_id:
            return DevInboundRoute(
                tenant_id=tenant_id,
                agent_id=agent_id,
                destination_number=destination_number,
            )
        if destination_number.strip() != self._extension:
            raise PlatformError(
                code=_INBOUND_EXTENSION_UNMAPPED,
                message=(
                    f"Inbound extension '{destination_number}' is not mapped for "
                    "development. Use extension "
                    f"'{self._extension}' or supply tenant_id and agent_id."
                ),
                status_code=404,
            )
        if not self._tenant_id or not self._agent_id:
            raise PlatformError(
                code=_INBOUND_EXTENSION_UNMAPPED,
                message=(
                    f"Inbound extension '{destination_number}' has no tenant/agent "
                    "configured. Set DEV_INBOUND_TENANT_ID and "
                    "DEV_INBOUND_AGENT_ID (or supply tenant_id and agent_id)."
                ),
                status_code=404,
            )
        return DevInboundRoute(
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            destination_number=destination_number,
        )

    @staticmethod
    def from_environment() -> "DevInboundRouter":
        """Build the dev router from the service environment.

        Generic ``DEV_INBOUND_*`` variables take precedence; the deprecated
        ``KAARI_DEV_*`` aliases are the fallback so existing setups keep
        working. Nothing is invented: with no tenant/agent configured the
        extension stays unmapped instead of silently falling back to Kaari.
        """
        return DevInboundRouter(
            _first_env(
                DEV_INBOUND_EXTENSION_ENV,
                KAARI_DEV_EXTENSION_ENV,
                default=DEFAULT_KAARI_DEV_EXTENSION,
            ),
            tenant_id=_first_env(
                DEV_INBOUND_TENANT_ENV,
                KAARI_DEV_TENANT_ENV,
                default="",
            )
            or None,
            agent_id=_first_env(
                DEV_INBOUND_AGENT_ENV,
                KAARI_DEV_AGENT_ENV,
                default="",
            )
            or None,
        )


# Backward compatibility alias for existing imports
KaariDevRouter = DevInboundRouter
KaariDevRouter.resolve = DevInboundRouter.resolve  # type: ignore[assignment]
KaariDevRouter.from_environment = staticmethod(DevInboundRouter.from_environment)  # type: ignore[assignment]
