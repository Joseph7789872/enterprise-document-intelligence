"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  type Citation,
  type ConversationInfo,
  type SavedObjection,
  type Segment,
  clearToken,
  createConversation,
  getConversation,
  getMe,
  getToken,
  isManager,
  listConversations,
  listObjections,
  listSegments,
  streamAnswer,
} from "@/lib/api";

// Mirrors the backend CONFIDENCE_THRESHOLD: below this we surface an honest
// "not fully sure" banner rather than presenting the answer as definitive.
const LOW_CONFIDENCE = 0.6;

type Mode = "ask" | "objection";

// One exchange in the transcript. `streaming` marks the turn currently receiving tokens.
interface Turn {
  question: string;
  answer: string;
  citations: Citation[];
  confidence: number | null;
  held: boolean;
  streaming: boolean;
  error: string | null;
}

function newTurn(question: string): Turn {
  return {
    question,
    answer: "",
    citations: [],
    confidence: null,
    held: false,
    streaming: true,
    error: null,
  };
}

export default function ChatPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  // Guards the /app?q=… deep-link so it auto-runs exactly once per mount.
  const autoRan = useRef(false);

  const [mode, setMode] = useState<Mode>("ask");
  const [objections, setObjections] = useState<SavedObjection[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [segmentFilter, setSegmentFilter] = useState<string>("");
  const [manager, setManager] = useState(false);

  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [streaming, setStreaming] = useState(false);

  // Active thread + the recent-thread list for the switcher.
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationInfo[]>([]);
  // Keep the active id in a ref so the streaming callbacks read the latest value.
  const convIdRef = useRef<string | null>(null);

  const refreshConversations = useCallback(() => {
    listConversations()
      .then(setConversations)
      .catch(() => {
        /* thread list is best-effort */
      });
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    // Confirm the token is valid before rendering the (auth-gated) chat UI. An expired or
    // invalid token would otherwise paint the full UI and fire a burst of 401s before any
    // redirect. Only mark ready — and fire the dependent loads — once /auth/me succeeds.
    getMe()
      .then((u) => {
        setManager(isManager(u.role));
        setReady(true);
        listObjections().then(setObjections).catch(() => {});
        listSegments().then(setSegments).catch(() => {});
        refreshConversations();
        // Deep-link from the ramp checklist: /app?q=<question> starts a fresh thread.
        const q = new URLSearchParams(window.location.search).get("q");
        if (q && !autoRan.current) {
          autoRan.current = true;
          void ask(q);
        }
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  // Refetch objections when the segment filter changes (the "objections for [segment]" view).
  useEffect(() => {
    if (!ready) return;
    listObjections(segmentFilter || null).then(setObjections).catch(() => {});
  }, [segmentFilter, ready]);

  // Mutate the most recent (in-flight) turn.
  const patchLastTurn = useCallback((patch: Partial<Turn>) => {
    setTurns((prev) => {
      if (prev.length === 0) return prev;
      const next = prev.slice();
      next[next.length - 1] = { ...next[next.length - 1], ...patch };
      return next;
    });
  }, []);

  // Token streaming appends to the last turn's answer via functional state.
  const appendToken = useCallback((t: string) => {
    setTurns((prev) => {
      if (prev.length === 0) return prev;
      const next = prev.slice();
      const last = next[next.length - 1];
      next[next.length - 1] = { ...last, answer: last.answer + t };
      return next;
    });
  }, []);

  const ask = useCallback(
    async (q: string) => {
      const text = q.trim();
      if (!text) return;
      let cid = convIdRef.current;
      if (!cid) {
        try {
          const convo = await createConversation(text.slice(0, 80));
          cid = convo.id;
          convIdRef.current = cid;
          setConversationId(cid);
        } catch {
          /* one-shot fallback */
        }
      }
      setTurns((prev) => [...prev, newTurn(text)]);
      setStreaming(true);
      try {
        await streamAnswer(
          text,
          {
            onToken: appendToken,
            onDone: (d) => {
              patchLastTurn({ citations: d.citations, confidence: d.confidence, streaming: false });
              if (d.conversation_id) {
                convIdRef.current = d.conversation_id;
                setConversationId(d.conversation_id);
              }
            },
            onPending: () => patchLastTurn({ held: true, streaming: false }),
            onError: (detail) => patchLastTurn({ error: detail, streaming: false }),
          },
          cid,
        );
      } catch (err) {
        patchLastTurn({
          error: err instanceof Error ? err.message : "Something went wrong",
          streaming: false,
        });
      } finally {
        setStreaming(false);
        refreshConversations();
      }
    },
    [appendToken, patchLastTurn, refreshConversations],
  );

  function startNewChat() {
    convIdRef.current = null;
    setConversationId(null);
    setTurns([]);
    setQuestion("");
  }

  async function switchThread(id: string) {
    try {
      const detail = await getConversation(id);
      convIdRef.current = id;
      setConversationId(id);
      setTurns(
        detail.turns.map((t) => ({
          question: t.question,
          answer: t.answer ?? "",
          citations: t.citations,
          confidence: t.confidence,
          held: t.status === "pending_approval",
          streaming: false,
          error: null,
        })),
      );
    } catch {
      /* ignore load failure */
    }
  }

  if (!ready) return null;

  function signOut() {
    clearToken();
    router.push("/login");
  }

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
          {manager && (
            <Link href="/analytics" className="muted" style={{ fontSize: "0.9rem" }}>
              Analytics
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
        objection. Follow-up questions keep the thread&apos;s context. Every answer is
        grounded in your team&apos;s playbooks and cited.
      </p>

      {/* Thread controls */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
        <button onClick={startNewChat} disabled={streaming} style={{ marginTop: 0 }}>
          New chat
        </button>
        {conversations.length > 0 && (
          <select
            value={conversationId ?? ""}
            onChange={(e) => (e.target.value ? switchThread(e.target.value) : startNewChat())}
            disabled={streaming}
            aria-label="Switch conversation"
          >
            <option value="">Recent chats…</option>
            {conversations.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title || "Untitled chat"}
              </option>
            ))}
          </select>
        )}
      </div>

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
              const q = question;
              setQuestion("");
              void ask(q);
            }}
          >
            <label htmlFor="q">{turns.length > 0 ? "Follow-up question" : "Question"}</label>
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
            {segments.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="seg" style={{ fontSize: "0.85rem" }}>
                  Filter by segment
                </label>
                <select
                  id="seg"
                  value={segmentFilter}
                  onChange={(e) => setSegmentFilter(e.target.value)}
                >
                  <option value="">All segments</option>
                  {segments.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {objections.length === 0 ? (
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                No saved objections{segmentFilter ? " for this segment" : " yet"}. Your manager
                can add them in the admin area.
              </p>
            ) : (
              <div className="chips">
                {objections.map((o) => (
                  <button
                    key={o.id}
                    className="chip"
                    disabled={streaming}
                    onClick={() => void ask(o.prompt)}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Transcript: every turn in the active thread, oldest first. */}
      {turns.map((turn, i) => (
        <div className="card" key={i}>
          <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
            <strong style={{ color: "var(--text)" }}>You asked:</strong> {turn.question}
          </p>

          {turn.error ? (
            <p className="error">{turn.error}</p>
          ) : turn.held ? (
            <div className="banner warn">
              I couldn&apos;t find enough in your playbooks to answer this confidently. Try
              rephrasing, or ask your manager to add supporting content.
            </div>
          ) : (
            <>
              {!turn.streaming &&
                turn.confidence != null &&
                turn.confidence < LOW_CONFIDENCE && (
                  <div className="banner warn">
                    I&apos;m not fully sure on this one — here&apos;s what I found in your
                    playbooks. Double-check the sources below before relying on it.
                  </div>
                )}
              <p className={turn.streaming ? "streaming-cursor" : ""} style={{ marginTop: 0 }}>
                {turn.answer}
              </p>
              {!turn.streaming && turn.confidence != null && (
                <p className="muted" style={{ fontSize: "0.85rem" }}>
                  Confidence: {(turn.confidence * 100).toFixed(0)}%
                </p>
              )}
              {turn.citations.length > 0 && (
                <>
                  <h3>Sources</h3>
                  {turn.citations.map((c) => (
                    <div className="citation" key={c.chunk_id}>
                      [{c.marker}] {c.filename} — {c.snippet}
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>
      ))}
    </main>
  );
}
