// Thin fetch wrapper around the scrapper backend REST API.
//
// - Base URL comes from VITE_API_BASE_URL.
// - Every request is sent with credentials: "include" so the httpOnly auth
//   cookie set by POST /api/auth/login is attached automatically.
// - Any response with status 401 triggers the registered "unauthorized"
//   handler (see setUnauthorizedHandler), which AuthContext uses to flip
//   auth state so RequireAuth redirects to /login.

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Builds an absolute URL for a backend path, e.g. for EventSource or <a href>. */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export class ApiError extends Error {
  status: number;
  detail: string | undefined;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Registered once by AuthContext to react to a 401 from any request. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

interface RequestOptions extends RequestInit {
  /** Skip the global 401 -> "log the user out" handler (used by login/me calls). */
  skipAuthRedirect?: boolean;
}

async function parseErrorDetail(res: Response): Promise<string | undefined> {
  try {
    const data: unknown = await res.clone().json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // Response body was not JSON; fall through to statusText.
  }
  return undefined;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { skipAuthRedirect, headers, body, ...rest } = options;

  const isFormData = body instanceof FormData;
  const finalHeaders: HeadersInit = {
    ...(body !== undefined && !isFormData ? { "Content-Type": "application/json" } : {}),
    ...headers,
  };

  const res = await fetch(apiUrl(path), {
    ...rest,
    body,
    headers: finalHeaders,
    credentials: "include",
  });

  if (res.status === 401 && !skipAuthRedirect) {
    unauthorizedHandler?.();
  }

  if (!res.ok) {
    const detail = await parseErrorDetail(res);
    throw new ApiError(res.status, detail ?? res.statusText, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export const apiClient = {
  get<T>(path: string, options: RequestOptions = {}): Promise<T> {
    return request<T>(path, { ...options, method: "GET" });
  },

  post<T>(path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
    return request<T>(path, {
      ...options,
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },

  postForm<T>(path: string, form: FormData, options: RequestOptions = {}): Promise<T> {
    return request<T>(path, { ...options, method: "POST", body: form });
  },

  /** For endpoints that return a binary payload (e.g. session ZIP download). */
  async getBlob(path: string): Promise<Blob> {
    const res = await fetch(apiUrl(path), { credentials: "include" });
    if (res.status === 401) {
      unauthorizedHandler?.();
    }
    if (!res.ok) {
      const detail = await parseErrorDetail(res);
      throw new ApiError(res.status, detail ?? res.statusText, detail);
    }
    return res.blob();
  },
};
