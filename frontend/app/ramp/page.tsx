"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { type RampTopic, getToken, listRampTopics } from "@/lib/api";

const DONE_KEY = "ramp_done";

function loadDone(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    return new Set(JSON.parse(window.localStorage.getItem(DONE_KEY) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

export default function RampPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [topics, setTopics] = useState<RampTopic[]>([]);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    setDone(loadDone());
    listRampTopics()
      .then(setTopics)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load topics"));
  }, [router]);

  if (!ready) return null;

  function toggle(id: string) {
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      window.localStorage.setItem(DONE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  const completed = topics.filter((t) => done.has(t.id)).length;

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>New-rep ramp</h1>
        <Link href="/app">
          <button style={{ marginTop: 0 }}>← Back to chat</button>
        </Link>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Work through these starter topics to get up to speed fast. Each one opens a cited
        answer drawn from your team&apos;s playbooks.
      </p>

      {error && <p className="error">{error}</p>}

      {topics.length > 0 && (
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          {completed} of {topics.length} done
        </p>
      )}

      {topics.length === 0 && !error ? (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            No ramp topics yet. Your manager can add starter topics in the admin area.
          </p>
        </div>
      ) : (
        topics.map((t) => {
          const isDone = done.has(t.id);
          return (
            <div className="card" key={t.id} style={{ opacity: isDone ? 0.6 : 1 }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                <input
                  type="checkbox"
                  checked={isDone}
                  onChange={() => toggle(t.id)}
                  style={{ width: "auto", marginTop: 4 }}
                  aria-label={`Mark "${t.title}" done`}
                />
                <div style={{ flex: 1 }}>
                  <strong
                    style={{ textDecoration: isDone ? "line-through" : "none" }}
                  >
                    {t.title}
                  </strong>
                  <p className="muted" style={{ fontSize: "0.9rem", margin: "4px 0 0" }}>
                    {t.suggested_question}
                  </p>
                </div>
                <Link href={`/app?q=${encodeURIComponent(t.suggested_question)}`}>
                  <button style={{ marginTop: 0, whiteSpace: "nowrap" }}>Ask this →</button>
                </Link>
              </div>
            </div>
          );
        })
      )}
    </main>
  );
}
