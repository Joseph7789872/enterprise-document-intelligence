"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  type AnalyticsOverview,
  type LowConfidenceItem,
  exportAnalyticsCsv,
  getAnalyticsOverview,
  getLowConfidence,
  getMe,
  getToken,
  isManager,
} from "@/lib/api";

const RANGES = [7, 30, 90];

function pct(n: number | null): string {
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

function Bar({ value, max }: { value: number; max: number }) {
  const width = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ background: "var(--border)", borderRadius: 4, height: 8, width: "100%" }}>
      <div
        style={{ background: "var(--accent)", borderRadius: 4, height: 8, width: `${width}%` }}
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 120,
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "12px 16px",
      }}
    >
      <div style={{ fontSize: "1.6rem", fontWeight: 600 }}>{value}</div>
      <div className="muted" style={{ fontSize: "0.8rem" }}>
        {label}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const router = useRouter();
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
      <main>
        <h1>Analytics</h1>
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            This area is for managers only. <Link href="/app">Go to the chat →</Link>
          </p>
        </div>
      </main>
    );
  }

  const maxRep = Math.max(1, ...(data?.rep_activity.map((r) => r.query_count) ?? [1]));
  const maxTrend = Math.max(1, ...(data?.query_trend.map((t) => t.count) ?? [1]));
  const maxCited = Math.max(1, ...(data?.content_insights.most_cited.map((c) => c.citation_count) ?? [1]));
  const q = data?.answer_quality;

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Team analytics</h1>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Link href="/admin" className="muted" style={{ fontSize: "0.9rem" }}>
            ← Admin
          </Link>
          <button onClick={() => void exportAnalyticsCsv(days)} style={{ marginTop: 0 }}>
            Export CSV
          </button>
        </div>
      </div>

      <div className="tabs" style={{ marginBottom: 16 }}>
        {RANGES.map((d) => (
          <button
            key={d}
            className={`tab${days === d ? " active" : ""}`}
            onClick={() => void changeRange(d)}
          >
            Last {d} days
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted">Loading…</p>}

      {data && q && (
        <>
          {/* Stat cards */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 8 }}>
            <Stat label="Total queries" value={data.total_queries} />
            <Stat label="Active reps" value={data.active_reps} />
            <Stat label="Avg confidence" value={pct(q.avg_confidence)} />
            <Stat label="Citation coverage" value={`${q.citation_coverage_pct}%`} />
          </div>

          {/* Rep activity */}
          <div className="card">
            <h2 style={{ marginTop: 0 }}>Rep activity</h2>
            {data.rep_activity.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>No reps yet.</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <tbody>
                  {data.rep_activity.map((r) => (
                    <tr key={r.user_id} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 8px 8px 0", whiteSpace: "nowrap" }}>
                        {r.email}{" "}
                        {!r.active && <span className="badge">inactive</span>}
                      </td>
                      <td style={{ width: "40%", padding: "8px 0" }}>
                        <Bar value={r.query_count} max={maxRep} />
                      </td>
                      <td style={{ textAlign: "right", padding: "8px 0", whiteSpace: "nowrap" }}>
                        {r.query_count} queries
                      </td>
                      <td className="muted" style={{ textAlign: "right", padding: "8px 0 8px 12px", whiteSpace: "nowrap" }}>
                        {r.avg_confidence != null ? `${pct(r.avg_confidence)} conf` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Query trend */}
          <div className="card">
            <h2 style={{ marginTop: 0 }}>Query volume</h2>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 80 }}>
              {data.query_trend.map((t) => (
                <div
                  key={t.date}
                  title={`${t.date}: ${t.count}`}
                  style={{
                    flex: 1,
                    background: "var(--accent)",
                    borderRadius: "2px 2px 0 0",
                    height: `${Math.max(2, Math.round((t.count / maxTrend) * 100))}%`,
                    minWidth: 2,
                  }}
                />
              ))}
            </div>
            <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 0 }}>
              {data.query_trend[0]?.date} → {data.query_trend[data.query_trend.length - 1]?.date}
            </p>
          </div>

          {/* Answer quality */}
          <div className="card">
            <h2 style={{ marginTop: 0 }}>Answer quality</h2>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: "0.95rem" }}>
              <li>Average confidence: {pct(q.avg_confidence)}</li>
              <li>
                Low-confidence answers: {q.low_confidence}
                {q.total > 0 ? ` (${Math.round((q.low_confidence / q.total) * 100)}%)` : ""}
              </li>
              <li>Held for approval: {q.pending_approval} · Rejected: {q.rejected}</li>
              <li>
                Grounded in citations: {q.with_citations} / {q.total} ({q.citation_coverage_pct}%)
              </li>
            </ul>
            <div style={{ marginTop: 12 }}>
              {lowConf === null ? (
                <button onClick={showLowConfidence} disabled={lowConfBusy} style={{ marginTop: 0 }}>
                  {lowConfBusy ? "Loading…" : "Show recent low-confidence questions"}
                </button>
              ) : lowConf.length === 0 ? (
                <p className="muted" style={{ margin: 0 }}>No low-confidence questions in this range.</p>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <tbody>
                    {lowConf.map((it) => (
                      <tr key={it.query_id} style={{ borderTop: "1px solid var(--border)", fontSize: "0.9rem" }}>
                        <td style={{ padding: "6px 0" }}>{it.question}</td>
                        <td className="muted" style={{ textAlign: "right", whiteSpace: "nowrap", padding: "6px 0 6px 12px" }}>
                          {it.user_email} · {pct(it.confidence)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Content insights */}
          <div className="card">
            <h2 style={{ marginTop: 0 }}>Content insights</h2>
            <h3 style={{ fontSize: "0.95rem", marginBottom: 4 }}>Most-cited documents</h3>
            {data.content_insights.most_cited.length === 0 ? (
              <p className="muted" style={{ marginTop: 0 }}>No citations yet in this range.</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
                <tbody>
                  {data.content_insights.most_cited.map((c) => (
                    <tr key={c.document_id} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "6px 8px 6px 0", whiteSpace: "nowrap" }}>{c.filename}</td>
                      <td style={{ width: "45%", padding: "6px 0" }}>
                        <Bar value={c.citation_count} max={maxCited} />
                      </td>
                      <td className="muted" style={{ textAlign: "right", padding: "6px 0", whiteSpace: "nowrap" }}>
                        {c.citation_count} cites
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <h3 style={{ fontSize: "0.95rem", marginBottom: 4 }}>
              Coverage gaps (uploaded, never cited)
            </h3>
            {data.content_insights.uncited_documents.length === 0 ? (
              <p className="muted" style={{ marginTop: 0 }}>Every document has been cited. 🎉</p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: "0.9rem" }}>
                {data.content_insights.uncited_documents.map((d) => (
                  <li key={d.document_id} className="muted">
                    {d.filename} <span className="badge">{d.content_type}</span>
                  </li>
                ))}
              </ul>
            )}

            {data.content_insights.uploads_by_type.length > 0 && (
              <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 0, marginTop: 12 }}>
                Uploads this range:{" "}
                {data.content_insights.uploads_by_type.map((u) => `${u.content_type} (${u.count})`).join(", ")}
              </p>
            )}
          </div>
        </>
      )}
    </main>
  );
}
