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
  // 204 No Content (e.g. DELETE) has no body to parse.
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
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

export interface StreamDone {
  query_id: string;
  citations: Citation[];
  confidence: number | null;
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onDone: (data: StreamDone) => void;
  onPending?: (data: { query_id: string; status: string }) => void;
  onError?: (detail: string) => void;
}

function parseSseEvent(raw: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

// Stream a cited answer token-by-token from /query/stream (Server-Sent Events). The
// answer arrives via onToken; citations + confidence arrive via onDone. Low-confidence
// answers (human-review off, the v1 default) still stream — the caller surfaces the
// confidence as an honest "not fully sure" banner.
export async function streamAnswer(question: string, h: StreamHandlers): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_URL}/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Stream failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const ev = parseSseEvent(buffer.slice(0, sep));
      buffer = buffer.slice(sep + 2);
      if (!ev) continue;
      if (ev.event === "token") h.onToken((ev.data as { text: string }).text);
      else if (ev.event === "done") h.onDone(ev.data as StreamDone);
      else if (ev.event === "pending") h.onPending?.(ev.data as { query_id: string; status: string });
      else if (ev.event === "error") h.onError?.((ev.data as { detail: string }).detail);
    }
  }
}

export interface SavedObjection {
  id: string;
  label: string;
  prompt: string;
  sort_order: number;
}

export async function listObjections(): Promise<SavedObjection[]> {
  return request<SavedObjection[]>("/objections");
}

export interface RampTopic {
  id: string;
  title: string;
  suggested_question: string;
  sort_order: number;
}

export async function listRampTopics(): Promise<RampTopic[]> {
  return request<RampTopic[]>("/ramp/topics");
}

// ── Current user ────────────────────────────────────────────────────────────────────
export type Role = "owner" | "admin" | "member" | "reviewer";

export interface CurrentUser {
  id: string;
  tenant_id: string;
  email: string;
  role: Role;
  is_active: boolean;
}

export function isManager(role: Role): boolean {
  return role === "owner" || role === "admin";
}

export async function getMe(): Promise<CurrentUser> {
  return request<CurrentUser>("/auth/me");
}

// ── Manager: reps (users) ─────────────────────────────────────────────────────────
export async function listUsers(): Promise<CurrentUser[]> {
  return request<CurrentUser[]>("/admin/users");
}

export async function createUser(
  email: string,
  password: string,
  role: Role = "member",
): Promise<CurrentUser> {
  return request<CurrentUser>("/admin/users", {
    method: "POST",
    body: JSON.stringify({ email, password, role }),
  });
}

export async function deactivateUser(userId: string): Promise<void> {
  await request<void>(`/admin/users/${userId}`, { method: "DELETE" });
}

// ── Manager: ramp topic + objection CRUD ────────────────────────────────────────────
export async function createRampTopic(
  title: string,
  suggestedQuestion: string,
  sortOrder = 0,
): Promise<RampTopic> {
  return request<RampTopic>("/ramp/topics", {
    method: "POST",
    body: JSON.stringify({
      title,
      suggested_question: suggestedQuestion,
      sort_order: sortOrder,
    }),
  });
}

export async function deleteRampTopic(id: string): Promise<void> {
  await request<void>(`/ramp/topics/${id}`, { method: "DELETE" });
}

export async function createObjection(
  label: string,
  prompt: string,
  sortOrder = 0,
): Promise<SavedObjection> {
  return request<SavedObjection>("/objections", {
    method: "POST",
    body: JSON.stringify({ label, prompt, sort_order: sortOrder }),
  });
}

export async function deleteObjection(id: string): Promise<void> {
  await request<void>(`/objections/${id}`, { method: "DELETE" });
}

export async function deleteDocument(id: string): Promise<void> {
  await request<void>(`/documents/${id}`, { method: "DELETE" });
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

export type ContentType =
  | "product"
  | "pricing"
  | "objections"
  | "battlecard"
  | "case_study"
  | "script";
export type Visibility = "rep_visible" | "manager_only";

export interface DocumentInfo {
  id: string;
  filename: string;
  status: string;
  chunk_count: number;
  content_type: ContentType;
  visibility: Visibility;
  error_message: string | null;
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  return request<DocumentInfo[]>("/documents");
}

export async function uploadDocument(
  file: File,
  contentType: ContentType = "product",
  visibility: Visibility = "rep_visible",
): Promise<DocumentInfo> {
  // Multipart upload — let the browser set the Content-Type boundary (so we don't reuse
  // the JSON `request` helper here).
  const form = new FormData();
  form.append("file", file);
  form.append("content_type", contentType);
  form.append("visibility", visibility);
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
