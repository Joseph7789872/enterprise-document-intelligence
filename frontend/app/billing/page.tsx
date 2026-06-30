"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  type BillingOverview,
  type CurrentUser,
  type PlanInfo,
  getBilling,
  getCapabilities,
  getMe,
  getToken,
  listPlans,
  openBillingPortal,
  startCheckout,
} from "@/lib/api";
import { AppShell, Badge, Banner, Button, Card, CardHeader } from "@/components";

function limitLabel(n: number | null): string {
  return n == null ? "Unlimited" : String(n);
}

export default function BillingPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
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
    getMe().then(setUser).catch(() => {});
    // Billing may be disabled (the whole API surface 404s). Don't render a broken
    // shell — bounce back to admin when the feature is off.
    getCapabilities()
      .then((caps) => {
        if (!caps.billing) {
          router.replace("/admin");
          return null;
        }
        return Promise.all([getBilling(), listPlans()]).then(([o, p]) => {
          setOverview(o);
          setPlans(p);
        });
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
    <AppShell user={user}>
      <header className="page-head">
        <h1 className="page-head__title">Plan &amp; billing</h1>
        <p className="page-head__sub">Manage your subscription, usage, and plan.</p>
      </header>

      {error && <Banner tone="error" style={{ marginBottom: "var(--space-lg)" }}>{error}</Banner>}

      <div className="section-stack">
        {overview && (
          <Card>
            <CardHeader
              title={
                <>
                  Current plan: {overview.plan.name}{" "}
                  <Badge tone="success">{overview.subscription.status}</Badge>
                </>
              }
              action={
                <Button variant="secondary" onClick={onManage} disabled={busy}>
                  Manage billing
                </Button>
              }
            />
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
              <li>
                Seats: {overview.usage.users} / {limitLabel(overview.plan.limits.seats)}
              </li>
              <li>
                Documents: {overview.usage.documents} /{" "}
                {limitLabel(overview.plan.limits.documents)}
              </li>
              <li>
                Queries this month: {overview.usage.queries_this_period} /{" "}
                {limitLabel(overview.plan.limits.queries_per_month)}
              </li>
            </ul>
          </Card>
        )}

        <Card>
          <CardHeader title="Plans" />
          <div className="section-stack" style={{ gap: "var(--space-sm)" }}>
            {plans.map((p) => {
              const current = overview?.plan.key === p.key;
              return (
                <div
                  key={p.key}
                  className={current ? "plan-row plan-row--current" : "plan-row"}
                >
                  <div>
                    <strong>{p.name}</strong> — {p.price_display}
                    <div className="muted" style={{ fontSize: "var(--text-sm)" }}>
                      {limitLabel(p.limits.seats)} seats · {limitLabel(p.limits.documents)}{" "}
                      docs · {limitLabel(p.limits.queries_per_month)} queries/mo
                    </div>
                  </div>
                  {current ? (
                    <Badge>Current</Badge>
                  ) : p.key === "trial" ? null : (
                    <Button size="sm" onClick={() => onUpgrade(p.key)} disabled={busy}>
                      Choose {p.name}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
