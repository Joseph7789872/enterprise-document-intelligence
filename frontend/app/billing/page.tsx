"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  type BillingOverview,
  type PlanInfo,
  getBilling,
  getToken,
  listPlans,
  openBillingPortal,
  startCheckout,
} from "@/lib/api";

function limitLabel(n: number | null): string {
  return n == null ? "Unlimited" : String(n);
}

export default function BillingPage() {
  const router = useRouter();
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    Promise.all([getBilling(), listPlans()])
      .then(([o, p]) => {
        setOverview(o);
        setPlans(p);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load billing"))
      .finally(() => setLoaded(true));
  }, [router]);

  async function onUpgrade(planKey: string) {
    setBusy(true);
    setError(null);
    try {
      const { checkout_url } = await startCheckout(planKey);
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start checkout");
      setBusy(false);
    }
  }

  async function onManage() {
    setBusy(true);
    setError(null);
    try {
      const { portal_url } = await openBillingPortal();
      window.location.href = portal_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open billing portal");
      setBusy(false);
    }
  }

  if (!loaded) return null;

  return (
    <main>
      <h1>Plan &amp; billing</h1>
      <p className="muted">
        <Link href="/admin">← Back to admin</Link>
      </p>

      {error && <p className="error">{error}</p>}

      {overview && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>
            Current plan: {overview.plan.name}{" "}
            <span className="badge">{overview.subscription.status}</span>
          </h2>
          <ul style={{ margin: "8px 0", paddingLeft: 18 }}>
            <li>
              Seats: {overview.usage.users} / {limitLabel(overview.plan.limits.seats)}
            </li>
            <li>
              Documents: {overview.usage.documents} / {limitLabel(overview.plan.limits.documents)}
            </li>
            <li>
              Queries this month: {overview.usage.queries_this_period} /{" "}
              {limitLabel(overview.plan.limits.queries_per_month)}
            </li>
          </ul>
          <button onClick={onManage} disabled={busy}>
            Manage billing
          </button>
        </div>
      )}

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Plans</h2>
        <div style={{ display: "grid", gap: 12 }}>
          {plans.map((p) => {
            const current = overview?.plan.key === p.key;
            return (
              <div
                key={p.key}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  padding: 12,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <strong>{p.name}</strong> — {p.price_display}
                  <div className="muted" style={{ fontSize: "0.85rem" }}>
                    {limitLabel(p.limits.seats)} seats · {limitLabel(p.limits.documents)} docs ·{" "}
                    {limitLabel(p.limits.queries_per_month)} queries/mo
                  </div>
                </div>
                {current ? (
                  <span className="badge">Current</span>
                ) : p.key === "trial" ? null : (
                  <button onClick={() => onUpgrade(p.key)} disabled={busy} style={{ marginTop: 0 }}>
                    Choose {p.name}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </main>
  );
}
