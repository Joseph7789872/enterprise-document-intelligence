"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { acceptInvite } from "@/lib/api";

export default function AcceptInvitePage() {
  const router = useRouter();
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [inviteKey, setInviteKey] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Pre-fill from query params if the manager shared a convenience link, but everything
  // is editable — the teammate normally types the workspace id, email, and key by hand.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setTenantSlug(q.get("workspace") ?? q.get("slug") ?? "");
    setEmail(q.get("email") ?? "");
    setInviteKey(q.get("key") ?? "");
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await acceptInvite(tenantSlug.trim(), email.trim(), inviteKey.trim(), password);
      router.push("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not join the workspace");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Join your team</h1>
      <p className="muted">
        Enter your workspace identifier, your email, and the invite key your manager sent
        you, then choose a password.
      </p>
      <form className="card" onSubmit={onSubmit}>
        <label htmlFor="workspace">Workspace identifier</label>
        <input
          id="workspace"
          value={tenantSlug}
          onChange={(e) => setTenantSlug(e.target.value)}
          placeholder="acme"
          autoCapitalize="none"
          required
        />
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@yourco.com"
          required
        />
        <label htmlFor="key">Invite key</label>
        <input
          id="key"
          value={inviteKey}
          onChange={(e) => setInviteKey(e.target.value)}
          placeholder="ABCDE-FGHJK-LMNPQ-RSTUV"
          style={{ fontFamily: "monospace" }}
          required
        />
        <label htmlFor="password">Choose a password (12+ characters)</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          minLength={12}
          required
        />
        <button
          type="submit"
          disabled={busy || !tenantSlug.trim() || !email.trim() || !inviteKey.trim()}
        >
          {busy ? "Joining…" : "Join workspace"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
      <p className="muted" style={{ marginTop: 16 }}>
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
    </main>
  );
}
