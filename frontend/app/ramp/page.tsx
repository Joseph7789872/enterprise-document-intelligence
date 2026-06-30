"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  type CurrentUser,
  type RampTopic,
  clearToken,
  getMe,
  getToken,
  listRampTopics,
} from "@/lib/api";
import { AppShell, Banner, Card, EmptyState } from "@/components";

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
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [topics, setTopics] = useState<RampTopic[]>([]);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then((u) => {
        setUser(u);
        setReady(true);
        setDone(loadDone());
        listRampTopics()
          .then(setTopics)
          .catch((err) =>
            setError(err instanceof Error ? err.message : "Failed to load topics"),
          );
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
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
  const pct = topics.length ? Math.round((completed / topics.length) * 100) : 0;

  return (
    <AppShell user={user}>
      <header className="page-head">
        <h1 className="page-head__title">New-rep ramp</h1>
        <p className="page-head__sub">
          Work through these starter topics to get up to speed fast. Each one opens a cited
          answer drawn from your team&apos;s playbooks.
        </p>
      </header>

      {error && <Banner tone="error">{error}</Banner>}

      {topics.length > 0 && (
        <div style={{ marginBottom: "var(--space-lg)" }}>
          <div className="progress__meta">
            <span>
              {completed} of {topics.length} done
            </span>
            <span>{pct}%</span>
          </div>
          <div
            className="progress"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className="progress__bar" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {topics.length === 0 && !error ? (
        <EmptyState
          title="No ramp topics yet"
          description="Your manager can add starter topics in the admin area."
        />
      ) : (
        <div className="chat-stack">
          {topics.map((t) => {
            const isDone = done.has(t.id);
            return (
              <Card key={t.id} className={isDone ? "ramp-item--done" : undefined}>
                <div className="ramp-item">
                  <input
                    type="checkbox"
                    className="ramp-item__check"
                    checked={isDone}
                    onChange={() => toggle(t.id)}
                    aria-label={`Mark "${t.title}" done`}
                  />
                  <div className="ramp-item__body">
                    <div className="ramp-item__title">{t.title}</div>
                    <p className="ramp-item__q">{t.suggested_question}</p>
                  </div>
                  <Link
                    href={`/app?q=${encodeURIComponent(t.suggested_question)}`}
                    className="ui-btn ui-btn--secondary ui-btn--sm"
                  >
                    Ask this →
                  </Link>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
