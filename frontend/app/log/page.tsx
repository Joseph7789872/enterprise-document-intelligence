"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  type CurrentUser,
  type QueryLogItem,
  clearToken,
  getMe,
  getToken,
  listQueries,
  setQuerySaved,
} from "@/lib/api";
import {
  AppShell,
  Badge,
  Banner,
  Button,
  Card,
  EmptyState,
  Spinner,
  Tabs,
} from "@/components";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

export default function QaLogPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [items, setItems] = useState<QueryLogItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savedOnly, setSavedOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listQueries(savedOnly));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the Q&A log");
    } finally {
      setLoading(false);
    }
  }, [savedOnly]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then((u) => {
        setUser(u);
        setReady(true);
        load();
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
  }, [router, load]);

  async function toggleSaved(q: QueryLogItem) {
    try {
      await setQuerySaved(q.id, !q.saved);
      // Reflect locally; drop from the list if we're in the Saved-only view.
      setItems((prev) =>
        savedOnly && q.saved
          ? prev.filter((x) => x.id !== q.id)
          : prev.map((x) => (x.id === q.id ? { ...x, saved: !x.saved } : x)),
      );
    } catch {
      /* ignore toggle failure */
    }
  }

  if (!ready) return null;

  return (
    <AppShell user={user}>
      <header className="page-head">
        <h1 className="page-head__title">Q&amp;A log</h1>
        <p className="page-head__sub">
          Every question you&apos;ve asked, with its answer, sources, and confidence.
        </p>
      </header>

      <div style={{ margin: "var(--space-lg) 0" }}>
        <Tabs
          aria-label="Filter log"
          value={savedOnly ? "saved" : "all"}
          onChange={(v) => setSavedOnly(v === "saved")}
          items={[
            { value: "all", label: "All" },
            { value: "saved", label: "Saved" },
          ]}
        />
      </div>

      {loading && (
        <p className="muted" style={{ display: "flex", gap: "var(--space-sm)", alignItems: "center" }}>
          <Spinner /> Loading…
        </p>
      )}
      {error && <Banner tone="error">{error}</Banner>}
      {!loading && !error && items.length === 0 && (
        <EmptyState
          title={savedOnly ? "No saved answers yet" : "No questions yet"}
          description={
            savedOnly
              ? "Star an answer from the log to keep it here for quick reference."
              : "Head to Ask and ask something — it'll show up here."
          }
        />
      )}

      <div className="chat-stack">
        {items.map((q) => (
          <Card key={q.id}>
            <div className="log-item__head">
              <span className="log-item__q">{q.question}</span>
              <span className="log-item__actions">
                <Button
                  variant={q.saved ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => toggleSaved(q)}
                  title={q.saved ? "Remove from Saved" : "Save this answer"}
                  aria-label={q.saved ? "Unsave" : "Save"}
                >
                  <StarIcon filled={q.saved} />
                  {q.saved ? "Saved" : "Save"}
                </Button>
                <span className="log-item__date">{formatDate(q.created_at)}</span>
              </span>
            </div>

            {q.status === "completed" ? (
              <>
                <p className="chat-answer">{q.answer}</p>
                {q.confidence != null && (
                  <div className="chat-meta">
                    <span className="muted" style={{ fontSize: "var(--text-xs)" }}>
                      Confidence
                    </span>
                    <Badge tone={q.confidence < 0.6 ? "warning" : "success"}>
                      {(q.confidence * 100).toFixed(0)}%
                    </Badge>
                  </div>
                )}
                {q.citations.length > 0 && (
                  <div className="chat-sources">
                    <p className="chat-sources__label">Sources</p>
                    {q.citations.map((c) => (
                      <div className="citation" key={c.chunk_id}>
                        [{c.marker}] {c.filename} — {c.snippet}
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="muted" style={{ marginBottom: 0, display: "flex", gap: "var(--space-sm)", alignItems: "center" }}>
                <Badge tone="warning">{q.status.replace("_", " ")}</Badge>
                {q.status === "pending_approval"
                  ? "Held for human review (low confidence or unsupported by your documents)."
                  : "No answer recorded."}
              </p>
            )}
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
