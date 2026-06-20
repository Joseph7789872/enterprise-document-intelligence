"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  type Citation,
  type SavedObjection,
  clearToken,
  getMe,
  getToken,
  isManager,
  listObjections,
  streamAnswer,
} from "@/lib/api";

// Mirrors the backend CONFIDENCE_THRESHOLD: below this we surface an honest
// "not fully sure" banner rather than presenting the answer as definitive.
const LOW_CONFIDENCE = 0.6;

type Mode = "ask" | "objection";

export default function ChatPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  const [mode, setMode] = useState<Mode>("ask");
  const [objections, setObjections] = useState<SavedObjection[]>([]);
  const [manager, setManager] = useState(false);

  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [held, setHeld] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    listObjections()
      .then(setObjections)
      .catch(() => {
        /* objection library is optional; ignore load errors */
      });
    getMe()
      .then((u) => setManager(isManager(u.role)))
      .catch(() => {
        /* role lookup is best-effort; just hides the Admin link */
      });
    // Deep-link from the ramp checklist: /app?q=<question> prefills and runs it.
    // Read from window.location to avoid the useSearchParams Suspense requirement.
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      setQuestion(q);
      void run(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const run = useCallback(async (q: string) => {
    const text = q.trim();
    if (!text) return;
    setAsked(text);
    setAnswer("");
    setCitations([]);
    setConfidence(null);
    setHeld(false);
    setError(null);
    setStreaming(true);
    try {
      await streamAnswer(text, {
        onToken: (t) => setAnswer((prev) => prev + t),
        onDone: (d) => {
          setCitations(d.citations);
          setConfidence(d.confidence);
        },
        onPending: () => setHeld(true),
        onError: (detail) => setError(detail),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setStreaming(false);
    }
  }, []);

  if (!ready) return null;

  function signOut() {
    clearToken();
    router.push("/login");
  }

  const lowConfidence =
    !held && !streaming && confidence != null && confidence < LOW_CONFIDENCE;

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Sales Assistant</h1>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Link href="/ramp" className="muted" style={{ fontSize: "0.9rem" }}>
            Ramp checklist
          </Link>
          {manager && (
            <Link href="/admin" className="muted" style={{ fontSize: "0.9rem" }}>
              Admin
            </Link>
          )}
          <Link href="/log" className="muted" style={{ fontSize: "0.9rem" }}>
            History
          </Link>
          <button onClick={signOut} style={{ marginTop: 0 }}>
            Sign out
          </button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Ask anything about your product, pricing, ICP, or competition — or look up an
        objection. Every answer is grounded in your team&apos;s playbooks and cited.
      </p>

      <div className="card">
        <div className="tabs">
          <button
            className={`tab${mode === "ask" ? " active" : ""}`}
            onClick={() => setMode("ask")}
          >
            Ask a question
          </button>
          <button
            className={`tab${mode === "objection" ? " active" : ""}`}
            onClick={() => setMode("objection")}
          >
            Objection lookup
          </button>
        </div>

        {mode === "ask" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(question);
            }}
          >
            <label htmlFor="q">Question</label>
            <textarea
              id="q"
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. How is our product priced and packaged?"
              required
            />
            <button type="submit" disabled={streaming || !question.trim()}>
              {streaming ? "Thinking…" : "Ask"}
            </button>
          </form>
        ) : (
          <>
            <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
              Pick a common objection and get a fast, cited way to handle it.
            </p>
            {objections.length === 0 ? (
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                No saved objections yet. Your manager can add them in the admin area.
              </p>
            ) : (
              <div className="chips">
                {objections.map((o) => (
                  <button
                    key={o.id}
                    className="chip"
                    disabled={streaming}
                    onClick={() => run(o.prompt)}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {(asked || streaming) && (
        <div className="card">
          {asked && (
            <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
              <strong style={{ color: "var(--text)" }}>You asked:</strong> {asked}
            </p>
          )}

          {held ? (
            <div className="banner warn">
              I couldn&apos;t find enough in your playbooks to answer this confidently. Try
              rephrasing, or ask your manager to add supporting content.
            </div>
          ) : (
            <>
              {lowConfidence && (
                <div className="banner warn">
                  I&apos;m not fully sure on this one — here&apos;s what I found in your
                  playbooks. Double-check the sources below before relying on it.
                </div>
              )}
              <p className={streaming ? "streaming-cursor" : ""} style={{ marginTop: 0 }}>
                {answer}
              </p>
              {!streaming && confidence != null && (
                <p className="muted" style={{ fontSize: "0.85rem" }}>
                  Confidence: {(confidence * 100).toFixed(0)}%
                </p>
              )}
              {citations.length > 0 && (
                <>
                  <h3>Sources</h3>
                  {citations.map((c) => (
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
