"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { type QueryLogItem, getToken, listQueries } from "@/lib/api";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function QaLogPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [items, setItems] = useState<QueryLogItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listQueries());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the Q&A log");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    load();
  }, [router, load]);

  if (!ready) return null;

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Q&amp;A log</h1>
        <Link href="/app">
          <button style={{ marginTop: 0 }}>← Back to app</button>
        </Link>
      </div>
      <p className="muted">Every question you&apos;ve asked, with its answer, sources, and confidence.</p>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            No questions yet. Head back and ask something — it&apos;ll show up here.
          </p>
        </div>
      )}

      {items.map((q) => (
        <div className="card" key={q.id}>
          <div
            style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}
          >
            <strong>{q.question}</strong>
            <span className="muted" style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
              {formatDate(q.created_at)}
            </span>
          </div>

          {q.status === "completed" ? (
            <>
              <p style={{ marginBottom: 4 }}>{q.answer}</p>
              {q.confidence != null && (
                <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
                  Confidence: {(q.confidence * 100).toFixed(0)}%
                </p>
              )}
              {q.citations.length > 0 && (
                <>
                  <div className="muted" style={{ fontSize: "0.8rem", marginTop: 8 }}>Sources</div>
                  {q.citations.map((c) => (
                    <div className="citation" key={c.chunk_id}>
                      [{c.marker}] {c.filename} — {c.snippet}
                    </div>
                  ))}
                </>
              )}
            </>
          ) : (
            <p className="muted" style={{ marginBottom: 0 }}>
              <span className="badge">{q.status.replace("_", " ")}</span>{" "}
              {q.status === "pending_approval"
                ? "Held for human review (low confidence or unsupported by your documents)."
                : "No answer recorded."}
            </p>
          )}
        </div>
      ))}
    </main>
  );
}
