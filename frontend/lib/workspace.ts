import { getTenantId } from "./tenant";
import { initials } from "./format";

/** Workspace identity for the top-right header.
 *
 * There is currently NO backend user/profile endpoint (auth-service exposes
 * only `/api/v1/auth/status`) and NO tenant-lookup endpoint, so no real
 * person or role can be displayed. To avoid fabricating one, the header shows
 * the real workspace tenant context instead:
 * - label: the tenant's real display name where known (kaari-planters is
 *   seeded in the backend as "Kaari Planters"), otherwise a humanized
 *   tenant id — never a person's name;
 * - sublabel: the neutral word "Workspace" (no invented role such as owner);
 * - initials: derived from the label.
 *
 * A future multi-user backend needs: `GET /api/v1/auth/me` (or equivalent)
 * returning the authenticated user's name/role, at which point this module
 * should prefer it over the workspace fallback.
 */

export interface WorkspaceProfile {
  label: string;
  sublabel: string;
  initials: string;
  tenantId: string;
}

const KNOWN_WORKSPACE_NAMES: Record<string, string> = {
  // Mirrors the backend seed in agent_service.database (Tenant name).
  "kaari-planters": "Kaari Planters",
};

function humanizeTenantId(tenantId: string): string {
  const words = tenantId.split(/[-_]+/).filter(Boolean);
  if (words.length === 0) return "Workspace";
  return words
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function getWorkspaceProfile(
  tenantId: string = getTenantId(),
): WorkspaceProfile {
  const label = KNOWN_WORKSPACE_NAMES[tenantId] ?? humanizeTenantId(tenantId);
  return {
    label,
    sublabel: "Workspace",
    initials: initials(label),
    tenantId,
  };
}
