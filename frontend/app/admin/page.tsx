"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  type BillingOverview,
  type Capabilities,
  type ContentType,
  type CurrentUser,
  type DocumentInfo,
  type Invitation,
  type NotionStatus,
  type RampTopic,
  type Role,
  type SavedObjection,
  type Segment,
  type TemplateInfo,
  type Visibility,
  applyTemplate,
  createInvitation,
  createObjection,
  createRampTopic,
  createSegment,
  deactivateUser,
  deleteDocument,
  deleteObjection,
  deleteRampTopic,
  deleteSegment,
  getBilling,
  getCapabilities,
  getMe,
  getNotionStatus,
  getToken,
  importUrl,
  isManager,
  listDocuments,
  listInvitations,
  listObjections,
  listRampTopics,
  listSegments,
  listTemplates,
  listUsers,
  regenerateInvitationLink,
  revokeInvitation,
  setNotionToken,
  syncNotion,
  uploadDocument,
  uploadDocumentsBatch,
} from "@/lib/api";
import {
  AppShell,
  Badge,
  Banner,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Input,
  Select,
  Table,
  Td,
  Th,
} from "@/components";

const CONTENT_TYPES: ContentType[] = [
  "product",
  "pricing",
  "objections",
  "battlecard",
  "case_study",
  "script",
];

export default function AdminPage() {
  const router = useRouter();
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [denied, setDenied] = useState(false);
  // Client-visible feature flags — gate connector cards (URL import + Notion) so they
  // don't render when ENABLE_CONNECTORS is off (their actions would 404).
  const [caps, setCaps] = useState<Capabilities | null>(null);

  // Content
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [contentType, setContentType] = useState<ContentType>("product");
  const [visibility, setVisibility] = useState<Visibility>("rep_visible");
  const [uploadSegments, setUploadSegments] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  // Segments (ICP)
  const [segments, setSegments] = useState<Segment[]>([]);
  const [segName, setSegName] = useState("");
  const [objSegments, setObjSegments] = useState<string[]>([]);

  // Phase C: templates, bulk upload, URL import, Notion
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [templateMsg, setTemplateMsg] = useState<string | null>(null);
  const bulkRef = useRef<HTMLInputElement>(null);
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [importUrlValue, setImportUrlValue] = useState("");
  const [urlMsg, setUrlMsg] = useState<string | null>(null);
  const [urlBusy, setUrlBusy] = useState(false);
  const [notion, setNotion] = useState<NotionStatus | null>(null);
  const [notionToken, setNotionTokenValue] = useState("");
  const [notionMsg, setNotionMsg] = useState<string | null>(null);
  const [notionBusy, setNotionBusy] = useState(false);

  // Reps + invitations
  const [users, setUsers] = useState<CurrentUser[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [repEmail, setRepEmail] = useState("");
  const [repRole, setRepRole] = useState<Role>("member");
  const [repMsg, setRepMsg] = useState<string | null>(null);
  // Shareable invite for the most recent invite (created or regenerated). The manager sends
  // the key + workspace id to the teammate out-of-band (Slack/Teams) — no email required.
  const [inviteInfo, setInviteInfo] = useState<{
    key: string;
    email: string;
    slug: string;
  } | null>(null);
  const [copied, setCopied] = useState<"key" | "message" | null>(null);

  // Plan & usage (billing may be disabled → 404, handled best-effort)
  const [billing, setBilling] = useState<BillingOverview | null>(null);

  // Ramp topics
  const [topics, setTopics] = useState<RampTopic[]>([]);
  const [topicTitle, setTopicTitle] = useState("");
  const [topicQuestion, setTopicQuestion] = useState("");

  // Objections
  const [objections, setObjections] = useState<SavedObjection[]>([]);
  const [objLabel, setObjLabel] = useState("");
  const [objPrompt, setObjPrompt] = useState("");

  const refreshDocs = useCallback(async () => {
    try {
      setDocs(await listDocuments());
    } catch {
      /* ignore transient list errors */
    }
  }, []);

  const refreshAll = useCallback(async () => {
    const capsResult = await getCapabilities().catch(() => null);
    setCaps(capsResult);
    await Promise.all([
      refreshDocs(),
      listUsers().then(setUsers).catch(() => {}),
      listInvitations().then(setInvitations).catch(() => {}),
      listRampTopics().then(setTopics).catch(() => {}),
      listObjections().then(setObjections).catch(() => {}),
      listSegments().then(setSegments).catch(() => {}),
      listTemplates().then(setTemplates).catch(() => {}),
      // Notion status only when connectors are enabled (otherwise the card is hidden).
      capsResult?.connectors
        ? getNotionStatus().then(setNotion).catch(() => setNotion(null))
        : Promise.resolve(),
      // Plan & usage only when billing is enabled (otherwise the card is hidden).
      capsResult?.billing
        ? getBilling().then(setBilling).catch(() => setBilling(null))
        : Promise.resolve(),
    ]);
  }, [refreshDocs]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then((u) => {
        setMe(u);
        if (!isManager(u.role)) setDenied(true);
        else void refreshAll();
      })
      .catch(() => router.replace("/login"));
  }, [router, refreshAll]);

  // Poll while any content is still ingesting.
  useEffect(() => {
    if (!docs.some((d) => d.status === "pending" || d.status === "processing")) return;
    const t = setInterval(refreshDocs, 2000);
    return () => clearInterval(t);
  }, [docs, refreshDocs]);

  if (!me) return null;

  if (denied) {
    return (
      <AppShell user={me}>
        <header className="page-head">
          <h1 className="page-head__title">Admin</h1>
        </header>
        <EmptyState
          title="Managers only"
          description="This area is for managers. Head to Ask to query your playbooks."
        />
      </AppShell>
    );
  }

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploadMsg(null);
    setUploading(true);
    try {
      const doc = await uploadDocument(file, contentType, visibility, uploadSegments);
      setUploadMsg(`Uploaded "${doc.filename}" — processing…`);
      if (fileRef.current) fileRef.current.value = "";
      setUploadSegments([]);
      await refreshDocs();
    } catch (err) {
      setUploadMsg(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function onAddSegment(e: React.FormEvent) {
    e.preventDefault();
    await createSegment(segName.trim(), segments.length);
    setSegName("");
    setSegments(await listSegments());
  }

  async function onRemoveSegment(id: string) {
    await deleteSegment(id);
    setSegments(await listSegments());
    // Drop the removed segment from any pending selections.
    setUploadSegments((s) => s.filter((x) => x !== id));
    setObjSegments((s) => s.filter((x) => x !== id));
  }

  function toggle(list: string[], id: string): string[] {
    return list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
  }

  async function onApplyTemplate() {
    if (!selectedTemplate) return;
    setTemplateMsg(null);
    try {
      const r = await applyTemplate(selectedTemplate);
      const n =
        r.segments.created.length + r.ramp_topics.created.length + r.objections.created.length;
      setTemplateMsg(
        `Added ${r.segments.created.length} segments, ${r.ramp_topics.created.length} ramp topics, ` +
          `${r.objections.created.length} objections${n === 0 ? " (all already existed)" : ""}.`,
      );
      await refreshAll();
    } catch (err) {
      setTemplateMsg(err instanceof Error ? err.message : "Could not apply template");
    }
  }

  async function onBulkUpload(e: React.FormEvent) {
    e.preventDefault();
    const files = Array.from(bulkRef.current?.files ?? []);
    if (files.length === 0) return;
    setBulkMsg(null);
    setBulkBusy(true);
    try {
      const r = await uploadDocumentsBatch(files, contentType, visibility, uploadSegments);
      const ok = r.results.filter((x) => x.status === "accepted").length;
      const bad = r.results.filter((x) => x.status === "rejected");
      setBulkMsg(
        `Uploaded ${ok}/${r.results.length} files.` +
          (bad.length ? ` Rejected: ${bad.map((b) => `${b.filename} (${b.error})`).join(", ")}` : ""),
      );
      if (bulkRef.current) bulkRef.current.value = "";
      await refreshDocs();
    } catch (err) {
      setBulkMsg(err instanceof Error ? err.message : "Bulk upload failed");
    } finally {
      setBulkBusy(false);
    }
  }

  async function onImportUrl(e: React.FormEvent) {
    e.preventDefault();
    if (!importUrlValue.trim()) return;
    setUrlMsg(null);
    setUrlBusy(true);
    try {
      const doc = await importUrl(importUrlValue.trim(), contentType, visibility, uploadSegments);
      setUrlMsg(`Imported "${doc.filename}" — processing…`);
      setImportUrlValue("");
      await refreshDocs();
    } catch (err) {
      setUrlMsg(err instanceof Error ? err.message : "Import failed");
    } finally {
      setUrlBusy(false);
    }
  }

  async function onSaveNotionToken(e: React.FormEvent) {
    e.preventDefault();
    if (!notionToken.trim()) return;
    setNotionMsg(null);
    setNotionBusy(true);
    try {
      setNotion(await setNotionToken(notionToken.trim()));
      setNotionTokenValue("");
      setNotionMsg("Token saved.");
    } catch (err) {
      setNotionMsg(err instanceof Error ? err.message : "Could not save token");
    } finally {
      setNotionBusy(false);
    }
  }

  async function onSyncNotion() {
    setNotionMsg(null);
    setNotionBusy(true);
    try {
      const r = await syncNotion();
      const ok = r.results.filter((x) => x.status === "accepted").length;
      setNotionMsg(`Synced ${ok}/${r.results.length} Notion pages.`);
      await refreshAll();
    } catch (err) {
      setNotionMsg(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setNotionBusy(false);
    }
  }

  async function onRemoveDoc(id: string) {
    await deleteDocument(id);
    await refreshDocs();
  }

  const joinUrl = () =>
    typeof window !== "undefined"
      ? `${window.location.origin}/accept-invite`
      : "/accept-invite";

  function inviteMessage(info: { key: string; email: string; slug: string }) {
    return (
      `You're invited to our Sales Assistant workspace.\n\n` +
      `Go to: ${joinUrl()}\n` +
      `Workspace identifier: ${info.slug}\n` +
      `Email: ${info.email}\n` +
      `Invite key: ${info.key}\n` +
      `(then choose a password to finish.)`
    );
  }

  async function copyText(text: string, which: "key" | "message") {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
    } catch {
      /* clipboard blocked — values are shown for manual copy */
    }
  }

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    setRepMsg(null);
    setInviteInfo(null);
    setCopied(null);
    try {
      const inv = await createInvitation(repEmail.trim(), repRole);
      setRepEmail("");
      setRepRole("member");
      setRepMsg("Invite created — send your teammate the details below (Slack, Teams, etc.).");
      const info = { key: inv.invite_key, email: inv.email, slug: inv.tenant_slug };
      setInviteInfo(info);
      await copyText(inviteMessage(info), "message");
      setInvitations(await listInvitations());
    } catch (err) {
      setRepMsg(err instanceof Error ? err.message : "Could not create invitation");
    }
  }

  async function onRegenerateKey(id: string) {
    setCopied(null);
    try {
      const inv = await regenerateInvitationLink(id);
      setRepMsg("Fresh invite key generated — the previous key is now invalid.");
      const info = { key: inv.invite_key, email: inv.email, slug: inv.tenant_slug };
      setInviteInfo(info);
      await copyText(inviteMessage(info), "message");
    } catch (err) {
      setRepMsg(err instanceof Error ? err.message : "Could not generate key");
    }
  }

  async function onRevokeInvite(id: string) {
    await revokeInvitation(id);
    setInvitations(await listInvitations());
  }

  async function onDeactivate(id: string) {
    await deactivateUser(id);
    setUsers(await listUsers());
  }

  async function onAddTopic(e: React.FormEvent) {
    e.preventDefault();
    await createRampTopic(topicTitle.trim(), topicQuestion.trim(), topics.length);
    setTopicTitle("");
    setTopicQuestion("");
    setTopics(await listRampTopics());
  }

  async function onRemoveTopic(id: string) {
    await deleteRampTopic(id);
    setTopics(await listRampTopics());
  }

  async function onAddObjection(e: React.FormEvent) {
    e.preventDefault();
    await createObjection(objLabel.trim(), objPrompt.trim(), objections.length, objSegments);
    setObjLabel("");
    setObjPrompt("");
    setObjSegments([]);
    setObjections(await listObjections());
  }

  const segName_ = (id: string) => segments.find((s) => s.id === id)?.name ?? "";

  async function onRemoveObjection(id: string) {
    await deleteObjection(id);
    setObjections(await listObjections());
  }

  // Segment multi-select pills shared by the upload + objection forms. A render
  // helper (not a component) so it doesn't remount on every parent render.
  const renderSegmentPicker = (
    selected: string[],
    onToggle: (id: string) => void,
  ) => (
    <>
      <label className="ui-field__label" style={{ marginTop: "var(--space-md)" }}>
        Segments (optional)
      </label>
      <div className="chips">
        {segments.map((s) => (
          <label key={s.id} className="chip seg-toggle">
            <input
              type="checkbox"
              checked={selected.includes(s.id)}
              onChange={() => onToggle(s.id)}
            />
            {s.name}
          </label>
        ))}
      </div>
    </>
  );

  return (
    <AppShell user={me} wide>
      <header className="page-head">
        <h1 className="page-head__title">Admin</h1>
        <p className="page-head__sub">
          Manage the content your reps can query, invite teammates, and curate the ramp
          checklist and objection library.
        </p>
      </header>

      <div className="section-stack">
        {/* Quick setup (starter templates) */}
        <Card>
          <CardHeader
            title="Quick setup"
            description="New team? Apply a starter template to seed segments, a ramp checklist, and an objection library. Safe to re-apply — anything that already exists is skipped."
          />
          <div className="form-row">
            <select
              className="ui-field__control field-inline"
              value={selectedTemplate}
              onChange={(e) => setSelectedTemplate(e.target.value)}
              aria-label="Choose a template"
            >
              <option value="">Choose a template…</option>
              {templates.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.name} ({t.segment_count} segments · {t.ramp_count} ramp ·{" "}
                  {t.objection_count} objections)
                </option>
              ))}
            </select>
            <Button onClick={onApplyTemplate} disabled={!selectedTemplate}>
              Apply template
            </Button>
          </div>
          {selectedTemplate && (
            <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
              {templates.find((t) => t.key === selectedTemplate)?.description}
            </p>
          )}
          {templateMsg && (
            <p className="muted" style={{ marginTop: "var(--space-sm)" }}>{templateMsg}</p>
          )}
        </Card>

        {/* Content */}
        <Card>
          <CardHeader
            title="Content / playbooks"
            description="Upload PDF, DOCX, or TXT. Rep-visible content is queryable by every AE; manager-only content (e.g. floor pricing) stays hidden from reps."
          />
          <form onSubmit={onUpload}>
            <label className="ui-field__label">Document</label>
            <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" required />
            <Select
              label="Content type"
              value={contentType}
              onChange={(e) => setContentType(e.target.value as ContentType)}
            >
              {CONTENT_TYPES.map((c) => (
                <option key={c} value={c}>
                  {c.replace("_", " ")}
                </option>
              ))}
            </Select>
            <Select
              label="Visibility"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as Visibility)}
            >
              <option value="rep_visible">rep-visible</option>
              <option value="manager_only">manager-only</option>
            </Select>
            {segments.length > 0 &&
              renderSegmentPicker(uploadSegments, (id) =>
                setUploadSegments((cur) => toggle(cur, id)),
              )}
            <div style={{ marginTop: "var(--space-md)" }}>
              <Button type="submit" loading={uploading}>
                {uploading ? "Uploading…" : "Upload"}
              </Button>
            </div>
            {uploadMsg && (
              <p className="muted" style={{ marginTop: "var(--space-md)" }}>{uploadMsg}</p>
            )}
          </form>

          {docs.length > 0 && (
            <div style={{ marginTop: "var(--space-lg)" }}>
              <Table>
                <thead>
                  <tr>
                    <Th>File</Th>
                    <Th>Type</Th>
                    <Th>Visibility</Th>
                    <Th>Status</Th>
                    <Th numeric>Chunks</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {docs.map((d) => (
                    <tr key={d.id}>
                      <Td>{d.filename}</Td>
                      <Td>{d.content_type.replace("_", " ")}</Td>
                      <Td>{d.visibility === "manager_only" ? "manager-only" : "rep-visible"}</Td>
                      <Td>
                        <Badge
                          tone={
                            d.status === "ready" || d.status === "completed"
                              ? "success"
                              : d.status === "failed" || d.status === "error"
                                ? "danger"
                                : "neutral"
                          }
                        >
                          {d.status}
                        </Badge>
                      </Td>
                      <Td numeric>{d.chunk_count}</Td>
                      <Td numeric>
                        <Button variant="danger" size="sm" onClick={() => onRemoveDoc(d.id)}>
                          Delete
                        </Button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </Card>

        {/* More ways to add content (Phase C): bulk, URL, Notion */}
        <Card>
          <CardHeader
            title="Import content"
            description={`Bulk-upload many files at once${caps?.connectors ? ", or import a public web page by URL" : ""}. New content uses the content type, visibility, and segments selected in the upload form above.`}
          />
          <form onSubmit={onBulkUpload} style={{ marginBottom: caps?.connectors ? "var(--space-xl)" : 0 }}>
            <label className="ui-field__label">Bulk upload (PDF, DOCX, TXT — select several)</label>
            <input ref={bulkRef} type="file" accept=".pdf,.docx,.txt" multiple required />
            <div style={{ marginTop: "var(--space-md)" }}>
              <Button type="submit" loading={bulkBusy}>
                {bulkBusy ? "Uploading…" : "Upload files"}
              </Button>
            </div>
            {bulkMsg && (
              <p className="muted" style={{ marginTop: "var(--space-md)" }}>{bulkMsg}</p>
            )}
          </form>

          {caps?.connectors && (
            <form onSubmit={onImportUrl}>
              <Input
                label="Import from URL"
                type="url"
                value={importUrlValue}
                onChange={(e) => setImportUrlValue(e.target.value)}
                placeholder="https://example.com/our-pricing-page"
              />
              <div style={{ marginTop: "var(--space-md)" }}>
                <Button type="submit" loading={urlBusy} disabled={!importUrlValue.trim()}>
                  {urlBusy ? "Importing…" : "Import URL"}
                </Button>
              </div>
              {urlMsg && (
                <p className="muted" style={{ marginTop: "var(--space-md)" }}>{urlMsg}</p>
              )}
            </form>
          )}
        </Card>

        {/* Notion connector — only when connectors are enabled */}
        {caps?.connectors && (
          <Card>
            <CardHeader
              title="Notion"
              description="Create a Notion internal integration, share the pages you want indexed with it, then paste its token here. Sync pulls those pages in as rep-visible content."
            />
            <p className="muted" style={{ fontSize: "var(--text-sm)", marginTop: 0 }}>
              Status:{" "}
              {notion?.connected ? (
                <>
                  <Badge tone="success">connected</Badge>
                  {notion.last_synced_at
                    ? ` — last synced ${new Date(notion.last_synced_at).toLocaleString()}`
                    : " — not yet synced"}
                </>
              ) : (
                <Badge>not connected</Badge>
              )}
            </p>
            <form onSubmit={onSaveNotionToken}>
              <Input
                label="Notion integration token"
                type="password"
                value={notionToken}
                onChange={(e) => setNotionTokenValue(e.target.value)}
                placeholder="secret_…"
              />
              <div className="form-row" style={{ marginTop: "var(--space-md)" }}>
                <Button type="submit" disabled={notionBusy || !notionToken.trim()}>
                  {notion?.connected ? "Update token" : "Connect"}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onSyncNotion}
                  loading={notionBusy}
                  disabled={!notion?.connected}
                >
                  {notionBusy ? "Working…" : "Sync now"}
                </Button>
              </div>
              {notionMsg && (
                <p className="muted" style={{ marginTop: "var(--space-md)" }}>{notionMsg}</p>
              )}
            </form>
          </Card>
        )}

        {/* Segments (ICP) */}
        <Card>
          <CardHeader
            title="Segments (ICP)"
            description={`Define your market segments (e.g. Enterprise, SMB, Healthcare). Tag content and objections with segments so reps can filter "objections for [segment]".`}
          />
          <form onSubmit={onAddSegment}>
            <Input
              label="Segment name"
              value={segName}
              onChange={(e) => setSegName(e.target.value)}
              placeholder="Enterprise"
              required
            />
            <div style={{ marginTop: "var(--space-md)" }}>
              <Button type="submit" disabled={!segName.trim()}>
                Add segment
              </Button>
            </div>
          </form>
          {segments.length > 0 && (
            <div className="chips" style={{ marginTop: "var(--space-md)" }}>
              {segments.map((s) => (
                <span key={s.id} className="chip">
                  {s.name}
                  <button
                    onClick={() => onRemoveSegment(s.id)}
                    aria-label={`Delete ${s.name}`}
                    style={{
                      margin: "0 0 0 8px",
                      padding: "0 4px",
                      fontSize: "var(--text-base)",
                      lineHeight: 1,
                      background: "transparent",
                      color: "var(--color-muted-foreground)",
                      border: 0,
                    }}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </Card>

        {/* Plan & usage */}
        {billing && (
          <Card>
            <CardHeader
              title="Plan & usage"
              action={<Link href="/billing" className="ui-btn ui-btn--secondary ui-btn--sm">Manage plan →</Link>}
            />
            <p className="muted" style={{ marginTop: 0 }}>
              <strong>{billing.plan.name}</strong> ({billing.plan.price_display}) ·{" "}
              <Badge tone="success">{billing.subscription.status}</Badge>
            </p>
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
              <li>
                Seats: {billing.usage.users}
                {billing.plan.limits.seats != null
                  ? ` / ${billing.plan.limits.seats}`
                  : " (unlimited)"}
              </li>
              <li>
                Documents: {billing.usage.documents}
                {billing.plan.limits.documents != null
                  ? ` / ${billing.plan.limits.documents}`
                  : " (unlimited)"}
              </li>
              <li>
                Queries this month: {billing.usage.queries_this_period}
                {billing.plan.limits.queries_per_month != null
                  ? ` / ${billing.plan.limits.queries_per_month}`
                  : " (unlimited)"}
              </li>
            </ul>
          </Card>
        )}

        {/* Reps + invitations */}
        <Card>
          <CardHeader
            title="Reps"
            description="Invite a teammate, then send them the generated invite key and workspace identifier (Slack, Teams, etc.). They join with their email, the key, and a password they choose — no email required."
          />
          <form onSubmit={onInvite}>
            <Input
              label="Email"
              type="email"
              value={repEmail}
              onChange={(e) => setRepEmail(e.target.value)}
              placeholder="ae@yourco.com"
              required
            />
            <Select
              label="Role"
              value={repRole}
              onChange={(e) => setRepRole(e.target.value as Role)}
            >
              <option value="member">AE (rep)</option>
              <option value="admin">Manager</option>
            </Select>
            <div style={{ marginTop: "var(--space-md)" }}>
              <Button type="submit" disabled={!repEmail.trim()}>
                Create invite
              </Button>
            </div>
            {repMsg && (
              <p className="muted" style={{ marginTop: "var(--space-md)" }}>{repMsg}</p>
            )}
          </form>

          {inviteInfo && (
            <div className="inset" style={{ marginTop: "var(--space-md)" }}>
              <label className="ui-field__label" style={{ marginTop: 0 }}>
                Send your teammate these details
              </label>
              <ul style={{ margin: "var(--space-xs) 0", paddingLeft: 18, lineHeight: 1.8, fontSize: "var(--text-sm)" }}>
                <li>
                  Join page: <span className="mono">{joinUrl()}</span>
                </li>
                <li>
                  Workspace identifier: <strong className="mono">{inviteInfo.slug}</strong>
                </li>
                <li>
                  Email: <strong>{inviteInfo.email}</strong>
                </li>
                <li>
                  Invite key: <strong className="mono">{inviteInfo.key}</strong>
                </li>
              </ul>
              <div className="form-row">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => copyText(inviteInfo.key, "key")}
                >
                  Copy key
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => copyText(inviteMessage(inviteInfo), "message")}
                >
                  Copy full message
                </Button>
                {copied && (
                  <span className="muted" style={{ fontSize: "var(--text-sm)" }}>
                    {copied === "key" ? "Key copied ✓" : "Message copied ✓"}
                  </span>
                )}
              </div>
              <p className="muted" style={{ fontSize: "var(--text-xs)", margin: "var(--space-sm) 0 0" }}>
                Single-use and expires soon. The key is shown only once — regenerate it from
                the pending list if it&apos;s lost.
              </p>
            </div>
          )}

          {invitations.length > 0 && (
            <div style={{ marginTop: "var(--space-lg)" }}>
              <h3 style={{ fontSize: "var(--text-base)", marginBottom: "var(--space-xs)" }}>
                Pending invitations
              </h3>
              <Table>
                <tbody>
                  {invitations.map((inv) => (
                    <tr key={inv.id}>
                      <Td>{inv.email}</Td>
                      <Td>
                        <Badge>{isManager(inv.role) ? "manager" : "AE"}</Badge>
                      </Td>
                      <Td numeric>
                        <span className="form-row" style={{ justifyContent: "flex-end" }}>
                          <Button variant="secondary" size="sm" onClick={() => onRegenerateKey(inv.id)}>
                            New key
                          </Button>
                          <Button variant="danger" size="sm" onClick={() => onRevokeInvite(inv.id)}>
                            Revoke
                          </Button>
                        </span>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}

          {users.length > 0 && (
            <div style={{ marginTop: "var(--space-lg)" }}>
              <Table>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <Td>{u.email}</Td>
                      <Td>
                        <Badge>{isManager(u.role) ? "manager" : "AE"}</Badge>
                      </Td>
                      <Td>{u.is_active ? "active" : "inactive"}</Td>
                      <Td numeric>
                        {u.is_active && u.id !== me.id && (
                          <Button variant="danger" size="sm" onClick={() => onDeactivate(u.id)}>
                            Deactivate
                          </Button>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </Card>

        {/* Ramp topics */}
        <Card>
          <CardHeader
            title="Ramp checklist"
            description="Starter topics new reps work through. Each is a one-click cited question."
          />
          <form onSubmit={onAddTopic}>
            <Input
              label="Title"
              value={topicTitle}
              onChange={(e) => setTopicTitle(e.target.value)}
              placeholder="Pricing & packaging"
              required
            />
            <Input
              label="Suggested question"
              value={topicQuestion}
              onChange={(e) => setTopicQuestion(e.target.value)}
              placeholder="How is our product priced and packaged?"
              required
            />
            <div style={{ marginTop: "var(--space-md)" }}>
              <Button type="submit" disabled={!topicTitle.trim() || !topicQuestion.trim()}>
                Add topic
              </Button>
            </div>
          </form>
          {topics.map((t) => (
            <div className="list-row" key={t.id}>
              <span className="list-row__main">
                <span className="list-row__title">{t.title}</span>{" "}
                <span className="muted">— {t.suggested_question}</span>
              </span>
              <Button variant="ghost" size="sm" onClick={() => onRemoveTopic(t.id)}>
                Delete
              </Button>
            </div>
          ))}
        </Card>

        {/* Objections */}
        <Card>
          <CardHeader
            title="Objection library"
            description="One-click objection prompts surfaced in the chat's objection-lookup mode."
          />
          <form onSubmit={onAddObjection}>
            <Input
              label="Label"
              value={objLabel}
              onChange={(e) => setObjLabel(e.target.value)}
              placeholder="Too expensive"
              required
            />
            <Input
              label="Prompt"
              value={objPrompt}
              onChange={(e) => setObjPrompt(e.target.value)}
              placeholder="How do I handle 'your product is too expensive'?"
              required
            />
            {segments.length > 0 &&
              renderSegmentPicker(objSegments, (id) =>
                setObjSegments((cur) => toggle(cur, id)),
              )}
            <div style={{ marginTop: "var(--space-md)" }}>
              <Button type="submit" disabled={!objLabel.trim() || !objPrompt.trim()}>
                Add objection
              </Button>
            </div>
          </form>
          {objections.map((o) => (
            <div className="list-row" key={o.id}>
              <span className="list-row__main">
                <span className="list-row__title">{o.label}</span>{" "}
                <span className="muted">— {o.prompt}</span>
                {o.segment_ids.length > 0 && (
                  <span className="muted">
                    {" "}
                    [{o.segment_ids.map(segName_).filter(Boolean).join(", ")}]
                  </span>
                )}
              </span>
              <Button variant="ghost" size="sm" onClick={() => onRemoveObjection(o.id)}>
                Delete
              </Button>
            </div>
          ))}
        </Card>
      </div>
    </AppShell>
  );
}
