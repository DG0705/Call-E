/** Tenant context for the Call-E workspace.
 *
 * Backend APIs are tenant-scoped. For internal testing the tenant comes from
 * configuration (`NEXT_PUBLIC_TENANT_ID`, defaulting to `kaari-planters`).
 * Authenticated workspace selection must replace this single function — no
 * page component should hardcode a tenant id.
 */

export const DEFAULT_TENANT_ID = "kaari-planters";

export function getTenantId(): string {
  return process.env.NEXT_PUBLIC_TENANT_ID ?? DEFAULT_TENANT_ID;
}
