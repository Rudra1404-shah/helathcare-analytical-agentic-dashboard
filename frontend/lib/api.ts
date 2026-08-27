/**
 * The single typed client for the platform API.
 *
 * It unwraps the `{success, data, error}` envelope so callers work with the
 * payload directly, and throws an `ApiError` carrying the API's own message.
 * That message is written to be shown to a human, so the UI renders it rather
 * than inventing a generic one.
 *
 * The bearer token is read from the httpOnly session cookie on the server and
 * attached here. It is never exposed to browser JavaScript.
 */

import { cookies } from "next/headers";

import type { ApiEnvelope } from "@/lib/types";

export const SESSION_COOKIE = "unhp_session";
export const ROLE_COOKIE = "unhp_role";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }

  /** Whether the caller should be sent back to the sign-in page. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
  token?: string;
  /** Seconds to cache. Omit for always-fresh, which is the default here. */
  revalidate?: number;
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

/** Read the session token from the httpOnly cookie. Server components only. */
export async function sessionToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value;
}

/**
 * Call the API and return the unwrapped payload.
 *
 * @throws ApiError carrying the API's own human-readable message.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, revalidate } = options;
  const token = options.token ?? (await sessionToken());

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: revalidate === undefined ? "no-store" : undefined,
      next: revalidate === undefined ? undefined : { revalidate },
    });
  } catch {
    throw new ApiError(
      "The platform API is not reachable. Check that the backend is running on " +
        API_BASE_URL.replace("/api/v1", "") +
        ".",
      503,
    );
  }

  let envelope: ApiEnvelope<T> | null = null;
  try {
    envelope = (await response.json()) as ApiEnvelope<T>;
  } catch {
    envelope = null;
  }

  if (!response.ok || !envelope?.success) {
    throw new ApiError(
      envelope?.error ?? `The request failed with status ${response.status}.`,
      response.status,
    );
  }

  return envelope.data as T;
}

/**
 * Call the API without throwing, so a view can render its own error state.
 *
 * Returns a discriminated result rather than `null`, because "no rows" and
 * "the call failed" must render differently: one is an empty state, the other
 * needs a retry.
 */
export type Result<T> = { ok: true; data: T } | { ok: false; error: string; status: number };

export async function apiTry<T>(
  path: string,
  options: RequestOptions = {},
): Promise<Result<T>> {
  try {
    return { ok: true, data: await apiFetch<T>(path, options) };
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, error: error.message, status: error.status };
    }
    return { ok: false, error: "An unexpected error occurred.", status: 500 };
  }
}
