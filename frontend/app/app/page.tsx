"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  type Citation,
  type ConversationInfo,
  type CurrentUser,
  type SavedObjection,
  type Segment,
  clearToken,
  createConversation,
  getConversation,
  getMe,
  getToken,
  listConversations,
  listObjections,
  listSegments,
  streamAnswer,
} from "@/lib/api";
import {
  AppShell,
  Badge,
  Banner,
  Button,
  Card,
  Chip,
  Tabs,
  Textarea,
} from "@/components";

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
  const [user, setUser] = useState<CurrentUser | null>(null);
  // Guards the /app?q=… deep-link so it auto-runs exactly once per mount.
  const autoRan = useRef(false);

  const [mode, setMode] = useState<Mode>("ask");
  const [objections, setObjections] = useState<SavedObjection[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [segmentFilter, setSegmentFilter] = useState<string>("");

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
        setUser(u);
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

  return (
    <AppShell user={user}>
      <header className="page-head">
        <h1 className="page-head__title">Ask</h1>
        <p className="page-head__sub">
          Ask anything about your product, pricing, ICP, or competition — or look up an
          objection. Follow-up questions keep the thread&apos;s context, and every answer is
          grounded in your team&apos;s playbooks and cited.
        </p>
      </header>

      {/* Thread controls */}
      <div className="chat-toolbar">
        <Button variant="secondary" size="sm" onClick={startNewChat} disabled={streaming}>
          New chat
        </Button>
        {conversations.length > 0 && (
          <select
            className="ui-field__control chat-select"
            value={conversationId ?? ""}
            onChange={(e) =>
              e.target.value ? switchThread(e.target.value) : startNewChat()
            }
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

      <Card>
        <Tabs<Mode>
          aria-label="Answer mode"
          value={mode}
          onChange={setMode}
          items={[
            { value: "ask", label: "Ask a question" },
            { value: "objection", label: "Objection lookup" },
          ]}
        />

        {mode === "ask" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const q = question;
              setQuestion("");
              void ask(q);
            }}
          >
            <Textarea
              label={turns.length > 0 ? "Follow-up question" : "Question"}
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. How is our product priced and packaged?"
              required
            />
            <div className="composer__actions">
              <Button type="submit" loading={streaming} disabled={!question.trim()}>
                {streaming ? "Thinking…" : "Ask"}
              </Button>
            </div>
          </form>
        ) : (
          <>
            <p className="muted" style={{ fontSize: "var(--text-sm)", marginTop: "var(--space-md)" }}>
              Pick a common objection and get a fast, cited way to handle it.
            </p>
            {segments.length > 0 && (
              <select
                className="ui-field__control chat-select"
                aria-label="Filter by segment"
                value={segmentFilter}
                onChange={(e) => setSegmentFilter(e.target.value)}
                style={{ marginBottom: "var(--space-md)" }}
              >
                <option value="">All segments</option>
                {segments.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            )}
            {objections.length === 0 ? (
              <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
                No saved objections{segmentFilter ? " for this segment" : " yet"}. Your
                manager can add them in the admin area.
              </p>
            ) : (
              <div className="chips">
                {objections.map((o) => (
                  <Chip key={o.id} disabled={streaming} onClick={() => void ask(o.prompt)}>
                    {o.label}
                  </Chip>
                ))}
              </div>
            )}
          </>
        )}
      </Card>

      {/* Transcript: every turn in the active thread, oldest first. */}
      <div className="chat-stack">
        {turns.map((turn, i) => (
          <Card key={i}>
            <p className="chat-turn__q">
              <strong>You asked:</strong> {turn.question}
            </p>

            {turn.error ? (
              <Banner tone="error">{turn.error}</Banner>
            ) : turn.held ? (
              <Banner tone="warn">
                I couldn&apos;t find enough in your playbooks to answer this confidently.
                Try rephrasing, or ask your manager to add supporting content.
              </Banner>
            ) : (
              <>
                {!turn.streaming &&
                  turn.confidence != null &&
                  turn.confidence < LOW_CONFIDENCE && (
                    <Banner tone="warn" style={{ marginBottom: "var(--space-md)" }}>
                      I&apos;m not fully sure on this one — here&apos;s what I found in your
                      playbooks. Double-check the sources below before relying on it.
                    </Banner>
                  )}
                <p className={turn.streaming ? "chat-answer streaming-cursor" : "chat-answer"}>
                  {turn.answer}
                </p>
                {!turn.streaming && turn.confidence != null && (
                  <div className="chat-meta">
                    <span className="muted" style={{ fontSize: "var(--text-xs)" }}>
                      Confidence
                    </span>
                    <Badge
                      tone={turn.confidence < LOW_CONFIDENCE ? "warning" : "success"}
                    >
                      {(turn.confidence * 100).toFixed(0)}%
                    </Badge>
                  </div>
                )}
                {turn.citations.length > 0 && (
                  <div className="chat-sources">
                    <p className="chat-sources__label">Sources</p>
                    {turn.citations.map((c) => (
                      <div className="citation" key={c.chunk_id}>
                        [{c.marker}] {c.filename} — {c.snippet}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
