"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  type AnswerResponse,
  type DocumentInfo,
  ask,
  clearToken,
  getToken,
  listDocuments,
  uploadDocument,
} from "@/lib/api";

export default function QueryPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  // Documents
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [classification, setClassification] = useState("internal");
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Query
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshDocs = useCallback(async () => {
    try {
      setDocs(await listDocuments());
    } catch {
      /* ignore transient list errors */
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    refreshDocs();
  }, [router, refreshDocs]);

  // While anything is still processing, poll until it completes.
  useEffect(() => {
    if (!docs.some((d) => d.status === "pending" || d.status === "processing")) return;
    const t = setInterval(refreshDocs, 2000);
    return () => clearInterval(t);
  }, [docs, refreshDocs]);

  if (!ready) return null;

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploadMsg(null);
    setUploading(true);
    try {
      const doc = await uploadDocument(file, classification);
      setUploadMsg(`Uploaded "${doc.filename}" — processing…`);
      if (fileRef.current) fileRef.current.value = "";
      await refreshDocs();
    } catch (err) {
      setUploadMsg(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function onAsk(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      setResult(await ask(question));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    clearToken();
    router.push("/login");
  }

  const ready_docs = docs.filter((d) => d.status === "completed").length;

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Document Intelligence</h1>
        <button onClick={signOut} style={{ marginTop: 0 }}>
          Sign out
        </button>
      </div>

      {/* Upload */}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Your documents</h2>
        <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
          Upload PDF, DOCX, or TXT files. They&apos;re encrypted at rest, then chunked and
          embedded for retrieval.
        </p>
        <form onSubmit={onUpload}>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" required />
          <label htmlFor="cls">Classification</label>
          <select
            id="cls"
            value={classification}
            onChange={(e) => setClassification(e.target.value)}
            style={{
              width: "100%",
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              color: "var(--text)",
              padding: "10px 12px",
            }}
          >
            <option value="public">public</option>
            <option value="internal">internal</option>
            <option value="confidential">confidential</option>
            <option value="privileged">privileged</option>
          </select>
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
                <th>Class</th>
                <th>Status</th>
                <th>Chunks</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} style={{ borderTop: "1px solid var(--border)", fontSize: "0.9rem" }}>
                  <td style={{ padding: "6px 0" }}>{d.filename}</td>
                  <td>{d.classification_level}</td>
                  <td>
                    <span className="badge">{d.status}</span>
                  </td>
                  <td>{d.chunk_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Query */}
      <form className="card" onSubmit={onAsk}>
        <h2 style={{ marginTop: 0 }}>Ask a question</h2>
        {ready_docs === 0 && (
          <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
            Upload at least one document above and wait for its status to read{" "}
            <span className="badge">completed</span> before asking.
          </p>
        )}
        <label htmlFor="q">Question</label>
        <textarea
          id="q"
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What is our remote-work policy?"
          required
        />
        <button type="submit" disabled={busy || !question.trim()}>
          {busy ? "Thinking…" : "Ask"}
        </button>
        {error && <p className="error">{error}</p>}
        <div style={{ marginTop: 16 }}>
          <Link href="/log" className="muted" style={{ fontSize: "0.9rem" }}>
            View Q&amp;A log →
          </Link>
        </div>
      </form>

      {result && (
        <div className="card">
          {result.requires_approval ? (
            <p>
              <span className="badge">Pending approval</span> This answer was low-confidence
              (or unsupported by your documents) and is held for human review.
            </p>
          ) : (
            <>
              <p style={{ marginTop: 0 }}>{result.answer}</p>
              {result.confidence != null && (
                <p className="muted" style={{ fontSize: "0.85rem" }}>
                  Confidence: {(result.confidence * 100).toFixed(0)}%
                </p>
              )}
              {result.citations.length > 0 && (
                <>
                  <h3>Sources</h3>
                  {result.citations.map((c) => (
                    <div className="citation" key={c.chunk_id}>
                      [{c.marker}] {c.filename} — {c.snippet}
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>
      )}
    </main>
  );
}
