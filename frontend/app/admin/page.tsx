"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  type ContentType,
  type CurrentUser,
  type DocumentInfo,
  type RampTopic,
  type Role,
  type SavedObjection,
  type Segment,
  type Visibility,
  clearToken,
  createObjection,
  createRampTopic,
  createSegment,
  createUser,
  deactivateUser,
  deleteDocument,
  deleteObjection,
  deleteRampTopic,
  deleteSegment,
  getMe,
  getToken,
  isManager,
  listDocuments,
  listObjections,
  listRampTopics,
  listSegments,
  listUsers,
  uploadDocument,
} from "@/lib/api";

const CONTENT_TYPES: ContentType[] = [
  "product",
  "pricing",
  "objections",
  "battlecard",
  "case_study",
  "script",
];

const selectStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--bg)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  color: "var(--text)",
  padding: "10px 12px",
};

export default function AdminPage() {
  const router = useRouter();
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [denied, setDenied] = useState(false);

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

  // Reps
  const [users, setUsers] = useState<CurrentUser[]>([]);
  const [repEmail, setRepEmail] = useState("");
  const [repPassword, setRepPassword] = useState("");
  const [repRole, setRepRole] = useState<Role>("member");
  const [repMsg, setRepMsg] = useState<string | null>(null);

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
    await Promise.all([
      refreshDocs(),
      listUsers().then(setUsers).catch(() => {}),
      listRampTopics().then(setTopics).catch(() => {}),
      listObjections().then(setObjections).catch(() => {}),
      listSegments().then(setSegments).catch(() => {}),
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

  function signOut() {
    clearToken();
    router.push("/login");
  }

  if (denied) {
    return (
      <main>
        <h1>Admin</h1>
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            This area is for managers only. <Link href="/app">Go to the chat →</Link>
          </p>
        </div>
      </main>
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

  async function onRemoveDoc(id: string) {
    await deleteDocument(id);
    await refreshDocs();
  }

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    setRepMsg(null);
    try {
      await createUser(repEmail.trim(), repPassword, repRole);
      setRepEmail("");
      setRepPassword("");
      setRepRole("member");
      setRepMsg("Rep invited.");
      setUsers(await listUsers());
    } catch (err) {
      setRepMsg(err instanceof Error ? err.message : "Could not invite rep");
    }
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

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Admin</h1>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Link href="/app" className="muted" style={{ fontSize: "0.9rem" }}>
            Chat
          </Link>
          <button onClick={signOut} style={{ marginTop: 0 }}>
            Sign out
          </button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Manage the content your reps can query, invite reps, and curate the ramp checklist
        and objection library.
      </p>

      {/* Content */}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Content / playbooks</h2>
        <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
          Upload PDF, DOCX, or TXT. Rep-visible content is queryable by every AE;
          manager-only content (e.g. floor pricing) stays hidden from reps.
        </p>
        <form onSubmit={onUpload}>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" required />
          <label htmlFor="ct">Content type</label>
          <select
            id="ct"
            value={contentType}
            onChange={(e) => setContentType(e.target.value as ContentType)}
            style={selectStyle}
          >
            {CONTENT_TYPES.map((c) => (
              <option key={c} value={c}>
                {c.replace("_", " ")}
              </option>
            ))}
          </select>
          <label htmlFor="vis">Visibility</label>
          <select
            id="vis"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value as Visibility)}
            style={selectStyle}
          >
            <option value="rep_visible">rep-visible</option>
            <option value="manager_only">manager-only</option>
          </select>
          {segments.length > 0 && (
            <>
              <label>Segments (optional)</label>
              <div className="chips" style={{ marginBottom: 12 }}>
                {segments.map((s) => (
                  <label key={s.id} className="chip" style={{ cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={uploadSegments.includes(s.id)}
                      onChange={() => setUploadSegments((cur) => toggle(cur, s.id))}
                      style={{ marginRight: 6 }}
                    />
                    {s.name}
                  </label>
                ))}
              </div>
            </>
          )}
          <button type="submit" disabled={uploading}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
          {uploadMsg && <p className="muted" style={{ marginTop: 12 }}>{uploadMsg}</p>}
        </form>

        {docs.length > 0 && (
          <table style={{ width: "100%", marginTop: 16, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--muted)", fontSize: "0.8rem" }}>
                <th>File</th>
                <th>Type</th>
                <th>Visibility</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} style={{ borderTop: "1px solid var(--border)", fontSize: "0.9rem" }}>
                  <td style={{ padding: "6px 0" }}>{d.filename}</td>
                  <td>{d.content_type.replace("_", " ")}</td>
                  <td>{d.visibility === "manager_only" ? "manager-only" : "rep-visible"}</td>
                  <td>
                    <span className="badge">{d.status}</span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <button
                      onClick={() => onRemoveDoc(d.id)}
                      style={{ marginTop: 0, padding: "2px 10px", fontSize: "0.8rem" }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Segments (ICP) */}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Segments (ICP)</h2>
        <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
          Define your market segments (e.g. Enterprise, SMB, Healthcare). Tag content and
          objections with segments so reps can filter &quot;objections for [segment]&quot;.
        </p>
        <form onSubmit={onAddSegment}>
          <label htmlFor="sn">Segment name</label>
          <input
            id="sn"
            value={segName}
            onChange={(e) => setSegName(e.target.value)}
            placeholder="Enterprise"
            required
          />
          <button type="submit" disabled={!segName.trim()}>
            Add segment
          </button>
        </form>
        {segments.length > 0 && (
          <div className="chips" style={{ marginTop: 12 }}>
            {segments.map((s) => (
              <span key={s.id} className="chip">
                {s.name}
                <button
                  onClick={() => onRemoveSegment(s.id)}
                  aria-label={`Delete ${s.name}`}
                  style={{
                    marginTop: 0,
                    marginLeft: 8,
                    padding: "0 6px",
                    fontSize: "0.8rem",
                    background: "transparent",
                  }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Reps */}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Reps</h2>
        <form onSubmit={onInvite}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={repEmail}
            onChange={(e) => setRepEmail(e.target.value)}
            placeholder="ae@yourco.com"
            required
          />
          <label htmlFor="pw">Temporary password (min 12 chars)</label>
          <input
            id="pw"
            type="text"
            value={repPassword}
            onChange={(e) => setRepPassword(e.target.value)}
            minLength={12}
            required
          />
          <label htmlFor="role">Role</label>
          <select
            id="role"
            value={repRole}
            onChange={(e) => setRepRole(e.target.value as Role)}
            style={selectStyle}
          >
            <option value="member">AE (rep)</option>
            <option value="admin">Manager</option>
          </select>
          <button type="submit" disabled={!repEmail.trim() || repPassword.length < 12}>
            Invite rep
          </button>
          {repMsg && <p className="muted" style={{ marginTop: 12 }}>{repMsg}</p>}
        </form>

        {users.length > 0 && (
          <table style={{ width: "100%", marginTop: 16, borderCollapse: "collapse" }}>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} style={{ borderTop: "1px solid var(--border)", fontSize: "0.9rem" }}>
                  <td style={{ padding: "6px 0" }}>{u.email}</td>
                  <td>
                    <span className="badge">{isManager(u.role) ? "manager" : "AE"}</span>
                  </td>
                  <td>{u.is_active ? "active" : "inactive"}</td>
                  <td style={{ textAlign: "right" }}>
                    {u.is_active && u.id !== me.id && (
                      <button
                        onClick={() => onDeactivate(u.id)}
                        style={{ marginTop: 0, padding: "2px 10px", fontSize: "0.8rem" }}
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Ramp topics */}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Ramp checklist</h2>
        <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
          Starter topics new reps work through. Each is a one-click cited question.
        </p>
        <form onSubmit={onAddTopic}>
          <label htmlFor="tt">Title</label>
          <input
            id="tt"
            value={topicTitle}
            onChange={(e) => setTopicTitle(e.target.value)}
            placeholder="Pricing & packaging"
            required
          />
          <label htmlFor="tq">Suggested question</label>
          <input
            id="tq"
            value={topicQuestion}
            onChange={(e) => setTopicQuestion(e.target.value)}
            placeholder="How is our product priced and packaged?"
            required
          />
          <button type="submit" disabled={!topicTitle.trim() || !topicQuestion.trim()}>
            Add topic
          </button>
        </form>
        {topics.map((t) => (
          <div
            key={t.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderTop: "1px solid var(--border)",
              padding: "8px 0",
              fontSize: "0.9rem",
            }}
          >
            <span>
              <strong>{t.title}</strong>{" "}
              <span className="muted">— {t.suggested_question}</span>
            </span>
            <button
              onClick={() => onRemoveTopic(t.id)}
              style={{ marginTop: 0, padding: "2px 10px", fontSize: "0.8rem" }}
            >
              Delete
            </button>
          </div>
        ))}
      </div>

      {/* Objections */}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Objection library</h2>
        <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
          One-click objection prompts surfaced in the chat&apos;s objection-lookup mode.
        </p>
        <form onSubmit={onAddObjection}>
          <label htmlFor="ol">Label</label>
          <input
            id="ol"
            value={objLabel}
            onChange={(e) => setObjLabel(e.target.value)}
            placeholder="Too expensive"
            required
          />
          <label htmlFor="op">Prompt</label>
          <input
            id="op"
            value={objPrompt}
            onChange={(e) => setObjPrompt(e.target.value)}
            placeholder="How do I handle 'your product is too expensive'?"
            required
          />
          {segments.length > 0 && (
            <>
              <label>Segments (optional)</label>
              <div className="chips" style={{ marginBottom: 12 }}>
                {segments.map((s) => (
                  <label key={s.id} className="chip" style={{ cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={objSegments.includes(s.id)}
                      onChange={() => setObjSegments((cur) => toggle(cur, s.id))}
                      style={{ marginRight: 6 }}
                    />
                    {s.name}
                  </label>
                ))}
              </div>
            </>
          )}
          <button type="submit" disabled={!objLabel.trim() || !objPrompt.trim()}>
            Add objection
          </button>
        </form>
        {objections.map((o) => (
          <div
            key={o.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderTop: "1px solid var(--border)",
              padding: "8px 0",
              fontSize: "0.9rem",
            }}
          >
            <span>
              <strong>{o.label}</strong> <span className="muted">— {o.prompt}</span>
              {o.segment_ids.length > 0 && (
                <span className="muted">
                  {" "}
                  [{o.segment_ids.map(segName_).filter(Boolean).join(", ")}]
                </span>
              )}
            </span>
            <button
              onClick={() => onRemoveObjection(o.id)}
              style={{ marginTop: 0, padding: "2px 10px", fontSize: "0.8rem" }}
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </main>
  );
}
