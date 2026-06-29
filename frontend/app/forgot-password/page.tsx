"use client";

import Link from "next/link";
import { useState } from "react";
import { forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await forgotPassword(tenantSlug, email);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Reset your password</h1>
      {sent ? (
        <div className="card">
          <p>If an account exists for that email, we’ve sent a reset link. Check your inbox.</p>
          <p className="muted">
            <Link href="/login">Back to sign in</Link>
          </p>
        </div>
      ) : (
        <form className="card" onSubmit={onSubmit}>
          <p className="muted">Enter your workspace and email and we’ll send a reset link.</p>
          <label htmlFor="tenant">Workspace identifier</label>
          <input
            id="tenant"
            type="text"
            value={tenantSlug}
            onChange={(e) => setTenantSlug(e.target.value.toLowerCase())}
            placeholder="acme"
            autoComplete="organization"
            required
          />
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
          <button type="submit" disabled={busy}>
            {busy ? "Sending…" : "Send reset link"}
          </button>
          {error && <p className="error">{error}</p>}
          <p className="muted" style={{ marginTop: 12 }}>
            <Link href="/login">Back to sign in</Link>
          </p>
        </form>
      )}
    </main>
  );
}
