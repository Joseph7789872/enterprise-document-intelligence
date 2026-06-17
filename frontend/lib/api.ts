// Thin typed client for the EDIP backend. The base URL is configured at build/runtime
// via NEXT_PUBLIC_API_URL (defaults to the local dev backend). The bearer token is held
// in localStorage — adequate for this demo; a production SPA should use httpOnly cookies.

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "edip_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function login(
  tenantSlug: string,
  email: string,
  password: string,
): Promise<void> {
  const data = await request<TokenPair>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ tenant_slug: tenantSlug, email, password }),
  });
  setToken(data.access_token);
}

export interface Citation {
  marker: number;
  document_id: string;
  chunk_id: string;
  filename: string;
  snippet: string;
}

export interface AnswerResponse {
  query_id: string;
  status: string;
  requires_approval: boolean;
  answer: string | null;
  citations: Citation[];
  confidence: number | null;
}

export async function ask(question: string): Promise<AnswerResponse> {
  return request<AnswerResponse>("/query", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export interface QueryLogItem {
  id: string;
  status: string;
  question: string;
  answer: string | null;
  citations: Citation[];
  confidence: number | null;
  created_at: string;
}

export async function listQueries(): Promise<QueryLogItem[]> {
  return request<QueryLogItem[]>("/query");
}

export interface DocumentInfo {
  id: string;
  filename: string;
  status: string;
  chunk_count: number;
  classification_level: string;
  error_message: string | null;
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  return request<DocumentInfo[]>("/documents");
}

export async function uploadDocument(
  file: File,
  classification = "internal",
): Promise<DocumentInfo> {
  // Multipart upload — let the browser set the Content-Type boundary (so we don't reuse
  // the JSON `request` helper here).
  const form = new FormData();
  form.append("file", file);
  form.append("classification_level", classification);
  const token = getToken();
  const res = await fetch(`${API_URL}/documents`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!res.ok) {
    let detail = `Upload failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      /* non-JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as DocumentInfo;
}
