"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { register } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [tenantName, setTenantName] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await register(tenantName, tenantSlug, email, password);
      router.push("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Create your workspace</h1>
      <p className="muted">Start a free trial — no credit card required.</p>
      <form className="card" onSubmit={onSubmit}>
        <label htmlFor="tname">Company name</label>
        <input
          id="tname"
          type="text"
          value={tenantName}
          onChange={(e) => setTenantName(e.target.value)}
          placeholder="Acme Inc."
          required
        />
        <label htmlFor="tslug">Workspace identifier</label>
        <input
          id="tslug"
          type="text"
          value={tenantSlug}
          onChange={(e) => setTenantSlug(e.target.value.toLowerCase())}
          placeholder="acme"
          pattern="[a-z0-9][a-z0-9-]*"
          autoComplete="organization"
          required
        />
        <label htmlFor="email">Your email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
        <label htmlFor="password">Password (12+ characters)</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          minLength={12}
          required
        />
        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create workspace"}
        </button>
        {error && <p className="error">{error}</p>}
        <p className="muted" style={{ marginTop: 12, fontSize: "0.85rem" }}>
          By creating a workspace you agree to the <Link href="/terms">Terms</Link> and{" "}
          <Link href="/privacy">Privacy Policy</Link>.
        </p>
        <p className="muted" style={{ marginTop: 12 }}>
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </form>
    </main>
  );
}
