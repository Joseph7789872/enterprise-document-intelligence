// Thin typed client for the EDIP backend. The base URL is resolved at RUNTIME from the
// Next route handler /api/runtime-config (which reads BACKEND_API_URL on the server), so a
// single frontend image can target any backend in a hosted deploy. It falls back to the
// build-time NEXT_PUBLIC_API_URL (and finally localhost) for local dev. The bearer token is
// held in localStorage — adequate for this demo; a production SPA should use httpOnly cookies.

const BUILD_TIME_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let resolvedBase: string | null = null;
let basePromise: Promise<string> | null = null;

async function apiBase(): Promise<string> {
  if (resolvedBase) return resolvedBase;
  // On the server (SSR) there is no /api/runtime-config to call — use the env value.
  if (typeof window === "undefined") {
    resolvedBase = BUILD_TIME_API_URL;
    return resolvedBase;
  }
  if (!basePromise) {
    basePromise = fetch("/api/runtime-config")
      .then((r) => (r.ok ? r.json() : null))
      .then((c) => (c && c.apiUrl ? (c.apiUrl as string) : BUILD_TIME_API_URL))
      .catch(() => BUILD_TIME_API_URL);
  }
  resolvedBase = await basePromise;
  return resolvedBase;
}

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

  const res = await fetch(`${await apiBase()}${path}`, { ...init, headers });
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
  conversation_id: string | null;
}

export async function ask(
  question: string,
  conversationId?: string | null,
): Promise<AnswerResponse> {
  return request<AnswerResponse>("/query", {
    method: "POST",
    body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
  });
}

export interface StreamDone {
  query_id: string;
  citations: Citation[];
  confidence: number | null;
  conversation_id: string | null;
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onDone: (data: StreamDone) => void;
  onPending?: (data: { query_id: string; status: string; conversation_id: string | null }) => void;
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
export async function streamAnswer(
  question: string,
  h: StreamHandlers,
  conversationId?: string | null,
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${await apiBase()}/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
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
      else if (ev.event === "pending")
        h.onPending?.(ev.data as { query_id: string; status: string; conversation_id: string | null });
      else if (ev.event === "error") h.onError?.((ev.data as { detail: string }).detail);
    }
  }
}

export interface SavedObjection {
  id: string;
  label: string;
  prompt: string;
  sort_order: number;
  segment_ids: string[];
}

export async function listObjections(segmentId?: string | null): Promise<SavedObjection[]> {
  const q = segmentId ? `?segment_id=${encodeURIComponent(segmentId)}` : "";
  return request<SavedObjection[]>(`/objections${q}`);
}

// ── ICP / segments ──────────────────────────────────────────────────────────────────
export interface Segment {
  id: string;
  name: string;
  sort_order: number;
}

export async function listSegments(): Promise<Segment[]> {
  return request<Segment[]>("/segments");
}

export async function createSegment(name: string, sortOrder = 0): Promise<Segment> {
  return request<Segment>("/segments", {
    method: "POST",
    body: JSON.stringify({ name, sort_order: sortOrder }),
  });
}

export async function deleteSegment(id: string): Promise<void> {
  await request<void>(`/segments/${id}`, { method: "DELETE" });
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
  segmentIds?: string[],
): Promise<SavedObjection> {
  return request<SavedObjection>("/objections", {
    method: "POST",
    body: JSON.stringify({
      label,
      prompt,
      sort_order: sortOrder,
      segment_ids: segmentIds ?? null,
    }),
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
  conversation_id: string | null;
  saved: boolean;
}

export async function listQueries(savedOnly = false): Promise<QueryLogItem[]> {
  const q = savedOnly ? "?saved_only=true" : "";
  return request<QueryLogItem[]>(`/query${q}`);
}

export async function setQuerySaved(id: string, saved: boolean): Promise<QueryLogItem> {
  return request<QueryLogItem>(`/query/${id}/save?saved=${saved}`, { method: "POST" });
}

// ── Conversations (chat threads) ──────────────────────────────────────────────────────
export interface ConversationInfo {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationInfo {
  turns: QueryLogItem[];
}

export async function createConversation(title?: string | null): Promise<ConversationInfo> {
  return request<ConversationInfo>("/conversations", {
    method: "POST",
    body: JSON.stringify({ title: title ?? null }),
  });
}

export async function listConversations(): Promise<ConversationInfo[]> {
  return request<ConversationInfo[]>("/conversations");
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${id}`);
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
  segment_ids: string[];
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  return request<DocumentInfo[]>("/documents");
}

export async function setDocumentSegments(
  id: string,
  segmentIds: string[],
): Promise<DocumentInfo> {
  return request<DocumentInfo>(`/documents/${id}/segments`, {
    method: "PUT",
    body: JSON.stringify({ segment_ids: segmentIds }),
  });
}

export async function uploadDocument(
  file: File,
  contentType: ContentType = "product",
  visibility: Visibility = "rep_visible",
  segmentIds: string[] = [],
): Promise<DocumentInfo> {
  // Multipart upload — let the browser set the Content-Type boundary (so we don't reuse
  // the JSON `request` helper here).
  const form = new FormData();
  form.append("file", file);
  form.append("content_type", contentType);
  form.append("visibility", visibility);
  for (const sid of segmentIds) form.append("segment_ids", sid);
  const token = getToken();
  const res = await fetch(`${await apiBase()}/documents`, {
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

// ── Phase C: bulk upload, URL import, connectors, templates ───────────────────────────
export interface BatchItemResult {
  filename: string;
  status: "accepted" | "rejected";
  id: string | null;
  error: string | null;
}

export async function uploadDocumentsBatch(
  files: File[],
  contentType: ContentType = "product",
  visibility: Visibility = "rep_visible",
  segmentIds: string[] = [],
): Promise<{ results: BatchItemResult[] }> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("content_type", contentType);
  form.append("visibility", visibility);
  for (const sid of segmentIds) form.append("segment_ids", sid);
  const token = getToken();
  const res = await fetch(`${await apiBase()}/documents/batch`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  // 207 Multi-Status is an expected success here (mixed per-file results).
  if (!res.ok && res.status !== 207) {
    throw new Error(`Bulk upload failed (${res.status})`);
  }
  return (await res.json()) as { results: BatchItemResult[] };
}

export async function importUrl(
  url: string,
  contentType: ContentType = "product",
  visibility: Visibility = "rep_visible",
  segmentIds: string[] = [],
): Promise<DocumentInfo> {
  return request<DocumentInfo>("/documents/import-url", {
    method: "POST",
    body: JSON.stringify({
      url,
      content_type: contentType,
      visibility,
      segment_ids: segmentIds,
    }),
  });
}

export interface NotionStatus {
  connected: boolean;
  enabled: boolean;
  last_synced_at: string | null;
}

export async function getNotionStatus(): Promise<NotionStatus> {
  return request<NotionStatus>("/connectors/notion");
}

export async function setNotionToken(token: string): Promise<NotionStatus> {
  return request<NotionStatus>("/connectors/notion/token", {
    method: "PUT",
    body: JSON.stringify({ token }),
  });
}

export async function syncNotion(): Promise<{ results: BatchItemResult[] }> {
  return request<{ results: BatchItemResult[] }>("/connectors/notion/sync", { method: "POST" });
}

export interface TemplateInfo {
  key: string;
  name: string;
  description: string;
  segment_count: number;
  ramp_count: number;
  objection_count: number;
}

interface TemplateBucket {
  created: string[];
  skipped: string[];
}

export interface TemplateApplyResult {
  template_key: string;
  segments: TemplateBucket;
  ramp_topics: TemplateBucket;
  objections: TemplateBucket;
}

export async function listTemplates(): Promise<TemplateInfo[]> {
  return request<TemplateInfo[]>("/admin/templates");
}

export async function applyTemplate(templateKey: string): Promise<TemplateApplyResult> {
  return request<TemplateApplyResult>("/admin/templates/apply", {
    method: "POST",
    body: JSON.stringify({ template_key: templateKey }),
  });
}

// ── Phase D: self-serve signup ────────────────────────────────────────────────────────
export interface RegisterResponse {
  tenant: { id: string; name: string; slug: string };
  user: CurrentUser;
  tokens: TokenPair;
}

export async function register(
  tenantName: string,
  tenantSlug: string,
  email: string,
  password: string,
): Promise<void> {
  const data = await request<RegisterResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      tenant_name: tenantName,
      tenant_slug: tenantSlug,
      email,
      password,
    }),
  });
  setToken(data.tokens.access_token);
}

// ── Phase D: password reset (public) ──────────────────────────────────────────────────
export async function forgotPassword(tenantSlug: string, email: string): Promise<void> {
  await request<{ detail: string }>("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ tenant_slug: tenantSlug, email }),
  });
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await request<{ detail: string }>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

// ── Phase D: invitation acceptance (public) ───────────────────────────────────────────
export interface AcceptInviteResponse {
  user_id: string;
  tenant_id: string;
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function acceptInvite(token: string, password: string): Promise<void> {
  const data = await request<AcceptInviteResponse>("/auth/accept-invite", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
  setToken(data.access_token);
}

// ── Phase D: manager invitations ──────────────────────────────────────────────────────
export interface Invitation {
  id: string;
  email: string;
  role: Role;
  status: "pending" | "accepted" | "revoked";
  expires_at: string;
  created_at: string;
}

export async function listInvitations(): Promise<Invitation[]> {
  return request<Invitation[]>("/admin/invitations");
}

export async function createInvitation(email: string, role: Role = "member"): Promise<Invitation> {
  return request<Invitation>("/admin/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function revokeInvitation(id: string): Promise<void> {
  await request<void>(`/admin/invitations/${id}`, { method: "DELETE" });
}

// ── Phase D: billing (mounted only when ENABLE_BILLING) ───────────────────────────────
export interface PlanLimits {
  seats: number | null;
  documents: number | null;
  queries_per_month: number | null;
}

export interface PlanInfo {
  key: string;
  name: string;
  price_display: string;
  limits: PlanLimits;
}

export interface BillingOverview {
  subscription: {
    plan_key: string;
    status: "trialing" | "active" | "past_due" | "canceled";
    seats: number;
    current_period_end: string | null;
  };
  plan: PlanInfo;
  usage: { users: number; documents: number; queries_this_period: number };
}

export async function getBilling(): Promise<BillingOverview> {
  return request<BillingOverview>("/billing");
}

export async function listPlans(): Promise<PlanInfo[]> {
  return request<PlanInfo[]>("/billing/plans");
}

export async function startCheckout(planKey: string): Promise<{ checkout_url: string }> {
  return request<{ checkout_url: string }>("/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_key: planKey }),
  });
}

export async function openBillingPortal(): Promise<{ portal_url: string }> {
  return request<{ portal_url: string }>("/billing/portal", { method: "POST" });
}

// ── Phase E: manager analytics ────────────────────────────────────────────────────────
export interface RepActivity {
  user_id: string;
  email: string;
  role: Role;
  query_count: number;
  answered_count: number;
  avg_confidence: number | null;
  last_active: string | null;
  active: boolean;
}

export interface TrendPoint {
  date: string;
  count: number;
}

export interface AnswerQuality {
  total: number;
  avg_confidence: number | null;
  low_confidence: number;
  pending_approval: number;
  rejected: number;
  with_citations: number;
  citation_coverage_pct: number;
}

export interface CitedDocument {
  document_id: string;
  filename: string;
  citation_count: number;
}

export interface UncitedDocument {
  document_id: string;
  filename: string;
  content_type: string;
}

export interface UploadsByType {
  content_type: string;
  count: number;
}

export interface ContentInsights {
  most_cited: CitedDocument[];
  uncited_documents: UncitedDocument[];
  uploads_by_type: UploadsByType[];
}

export interface AnalyticsOverview {
  days: number;
  since: string;
  total_queries: number;
  active_reps: number;
  rep_activity: RepActivity[];
  query_trend: TrendPoint[];
  answer_quality: AnswerQuality;
  content_insights: ContentInsights;
}

export interface LowConfidenceItem {
  query_id: string;
  user_email: string;
  confidence: number | null;
  question: string;
  created_at: string;
}

export async function getAnalyticsOverview(days = 30): Promise<AnalyticsOverview> {
  return request<AnalyticsOverview>(`/analytics/overview?days=${days}`);
}

export async function getLowConfidence(days = 30, limit = 20): Promise<LowConfidenceItem[]> {
  return request<LowConfidenceItem[]>(`/analytics/low-confidence?days=${days}&limit=${limit}`);
}

// Download the per-rep activity CSV (needs the auth header, so fetch → blob → anchor click).
export async function exportAnalyticsCsv(days = 30): Promise<void> {
  const token = getToken();
  const res = await fetch(`${await apiBase()}/analytics/export?days=${days}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "rep_activity.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
