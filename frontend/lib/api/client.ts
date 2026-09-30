/** Typed API client abstraction for the Call-E backend.
 *
 * All HTTP access goes through this module — never scatter fetch() calls
 * across components. Each backend service has its own base URL from the
 * environment (see `lib/api/resources.ts`) so the same build works locally
 * and in deployed environments.
 *
 * No secrets are hardcoded here. Authenticated calls accept a token that the
 * (future) auth layer will supply; callers pass it explicitly for now.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string;
  requestId?: string;
}

export async function apiRequest<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.requestId) headers["X-Request-ID"] = options.requestId;

  const response = await fetch(`${baseUrl}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    let code: string | undefined;
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as {
        message?: string;
        code?: string;
      };
      if (payload.message) message = payload.message;
      if (payload.code) code = payload.code;
    } catch {
      /* non-JSON error body — keep the default message */
    }
    throw new ApiError(response.status, message, code);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** POST multipart form data (file uploads). Same error contract as apiRequest. */
export async function apiUpload<T>(
  baseUrl: string,
  path: string,
  form: FormData,
  options: { token?: string; requestId?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.requestId) headers["X-Request-ID"] = options.requestId;

  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers,
    body: form,
  });

  if (!response.ok) {
    let code: string | undefined;
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as {
        message?: string;
        code?: string;
      };
      if (payload.message) message = payload.message;
      if (payload.code) code = payload.code;
    } catch {
      /* non-JSON error body — keep the default message */
    }
    throw new ApiError(response.status, message, code);
  }
  return (await response.json()) as T;
}
