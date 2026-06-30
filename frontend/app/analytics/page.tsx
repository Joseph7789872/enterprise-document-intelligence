"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  type AnalyticsOverview,
  type CurrentUser,
  type LowConfidenceItem,
  exportAnalyticsCsv,
  getAnalyticsOverview,
  getLowConfidence,
  getMe,
  getToken,
  isManager,
} from "@/lib/api";
import {
  AppShell,
  Badge,
  Banner,
  Button,
  Card,
  CardHeader,
  EmptyState,
  StatCard,
  Table,
  Tabs,
  Td,
  Th,
} from "@/components";

const RANGES = [7, 30, 90];

function pct(n: number | null): string {
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

function MiniBar({ value, max }: { value: number; max: number }) {
  const width = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="minibar">
      <div className="minibar__fill" style={{ width: `${width}%` }} />
    </div>
  );
}

export default function AnalyticsPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [denied, setDenied] = useState(false);
  const [ready, setReady] = useState(false);
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lowConf, setLowConf] = useState<LowConfidenceItem[] | null>(null);
  const [lowConfBusy, setLowConfBusy] = useState(false);

  const load = useCallback(async (d: number) => {
    setError(null);
    try {
      setData(await getAnalyticsOverview(d));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load analytics");
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then((u) => {
        setUser(u);
        if (!isManager(u.role)) setDenied(true);
        else void load(days);
      })
      .catch(() => router.replace("/login"))
      .finally(() => setReady(true));
  }, [router, load, days]);

  async function changeRange(d: number) {
    setDays(d);
    setLowConf(null);
    await load(d);
  }

  async function showLowConfidence() {
    setLowConfBusy(true);
    try {
      setLowConf(await getLowConfidence(days, 20));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load coaching view");
    } finally {
      setLowConfBusy(false);
    }
  }

  if (!ready) return null;

  if (denied) {
    return (
      <AppShell user={user}>
        <header className="page-head">
          <h1 className="page-head__title">Analytics</h1>
        </header>
        <EmptyState
          title="Managers only"
          description="This area is for managers. Head to Ask to query your playbooks."
        />
      </AppShell>
    );
  }

  const maxRep = Math.max(1, ...(data?.rep_activity.map((r) => r.query_count) ?? [1]));
  const maxTrend = Math.max(1, ...(data?.query_trend.map((t) => t.count) ?? [1]));
  const maxCited = Math.max(
    1,
    ...(data?.content_insights.most_cited.map((c) => c.citation_count) ?? [1]),
  );
  const q = data?.answer_quality;

  return (
    <AppShell user={user} wide>
      <header className="page-head">
        <div className="page-head__row">
          <div>
            <h1 className="page-head__title">Team analytics</h1>
            <p className="page-head__sub">
              Adoption, answer quality, and content coverage across your team.
            </p>
          </div>
          <Button variant="secondary" onClick={() => void exportAnalyticsCsv(days)}>
            Export CSV
          </Button>
        </div>
      </header>

      <div style={{ margin: "var(--space-lg) 0" }}>
        <Tabs
          aria-label="Date range"
          value={String(days)}
          onChange={(v) => void changeRange(Number(v))}
          items={RANGES.map((d) => ({ value: String(d), label: `Last ${d} days` }))}
        />
      </div>

      {error && <Banner tone="error">{error}</Banner>}
      {!data && !error && <p className="muted">Loading…</p>}

      {data && q && (
        <div className="section-stack">
          {/* Stat cards */}
          <div className="stat-grid">
            <StatCard label="Total queries" value={data.total_queries} />
            <StatCard label="Active reps" value={data.active_reps} />
            <StatCard label="Avg confidence" value={pct(q.avg_confidence)} />
            <StatCard label="Citation coverage" value={`${q.citation_coverage_pct}%`} />
          </div>

          {/* Rep activity */}
          <Card>
            <CardHeader title="Rep activity" />
            {data.rep_activity.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>No reps yet.</p>
            ) : (
              <Table>
                <tbody>
                  {data.rep_activity.map((r) => (
                    <tr key={r.user_id}>
                      <Td>
                        {r.email} {!r.active && <Badge>inactive</Badge>}
                      </Td>
                      <Td style={{ width: "40%" }}>
                        <MiniBar value={r.query_count} max={maxRep} />
                      </Td>
                      <Td numeric>{r.query_count} queries</Td>
                      <Td numeric className="muted">
                        {r.avg_confidence != null ? `${pct(r.avg_confidence)} conf` : "—"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          {/* Query trend */}
          <Card>
            <CardHeader title="Query volume" />
            <div className="volume">
              {data.query_trend.map((t) => (
                <div
                  key={t.date}
                  className="volume__bar"
                  title={`${t.date}: ${t.count}`}
                  style={{
                    height: `${Math.max(2, Math.round((t.count / maxTrend) * 100))}%`,
                  }}
                />
              ))}
            </div>
            <p className="muted" style={{ fontSize: "var(--text-xs)", marginBottom: 0 }}>
              {data.query_trend[0]?.date} →{" "}
              {data.query_trend[data.query_trend.length - 1]?.date}
            </p>
          </Card>

          {/* Answer quality */}
          <Card>
            <CardHeader title="Answer quality" />
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
              <li>Average confidence: {pct(q.avg_confidence)}</li>
              <li>
                Low-confidence answers: {q.low_confidence}
                {q.total > 0 ? ` (${Math.round((q.low_confidence / q.total) * 100)}%)` : ""}
              </li>
              <li>Held for approval: {q.pending_approval} · Rejected: {q.rejected}</li>
              <li>
                Grounded in citations: {q.with_citations} / {q.total} (
                {q.citation_coverage_pct}%)
              </li>
            </ul>
            <div style={{ marginTop: "var(--space-md)" }}>
              {lowConf === null ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={showLowConfidence}
                  loading={lowConfBusy}
                >
                  {lowConfBusy ? "Loading…" : "Show recent low-confidence questions"}
                </Button>
              ) : lowConf.length === 0 ? (
                <p className="muted" style={{ margin: 0 }}>
                  No low-confidence questions in this range.
                </p>
              ) : (
                <Table>
                  <tbody>
                    {lowConf.map((it) => (
                      <tr key={it.query_id}>
                        <Td>{it.question}</Td>
                        <Td numeric className="muted">
                          {it.user_email} · {pct(it.confidence)}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </div>
          </Card>

          {/* Content insights */}
          <Card>
            <CardHeader title="Content insights" />
            <h3 style={{ fontSize: "var(--text-base)", marginBottom: "var(--space-xs)" }}>
              Most-cited documents
            </h3>
            {data.content_insights.most_cited.length === 0 ? (
              <p className="muted" style={{ marginTop: 0 }}>No citations yet in this range.</p>
            ) : (
              <Table>
                <tbody>
                  {data.content_insights.most_cited.map((c) => (
                    <tr key={c.document_id}>
                      <Td>{c.filename}</Td>
                      <Td style={{ width: "45%" }}>
                        <MiniBar value={c.citation_count} max={maxCited} />
                      </Td>
                      <Td numeric className="muted">{c.citation_count} cites</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}

            <h3
              style={{
                fontSize: "var(--text-base)",
                margin: "var(--space-lg) 0 var(--space-xs)",
              }}
            >
              Coverage gaps (uploaded, never cited)
            </h3>
            {data.content_insights.uncited_documents.length === 0 ? (
              <p className="muted" style={{ marginTop: 0 }}>
                Every document has been cited.
              </p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
                {data.content_insights.uncited_documents.map((d) => (
                  <li key={d.document_id} className="muted">
                    {d.filename} <Badge>{d.content_type}</Badge>
                  </li>
                ))}
              </ul>
            )}

            {data.content_insights.uploads_by_type.length > 0 && (
              <p
                className="muted"
                style={{ fontSize: "var(--text-sm)", margin: "var(--space-md) 0 0" }}
              >
                Uploads this range:{" "}
                {data.content_insights.uploads_by_type
                  .map((u) => `${u.content_type} (${u.count})`)
                  .join(", ")}
              </p>
            )}
          </Card>
        </div>
      )}
    </AppShell>
  );
}
