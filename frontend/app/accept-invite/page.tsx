"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { acceptInvite } from "@/lib/api";
import { AuthShell, Button, Input, Banner } from "@/components";

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
    <AuthShell
      title="Join your team"
      subtitle="Enter your workspace identifier, your email, and the invite key your manager sent you, then choose a password."
      footer={
        <p>
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      }
    >
      <form onSubmit={onSubmit}>
        <Input
          label="Workspace identifier"
          value={tenantSlug}
          onChange={(e) => setTenantSlug(e.target.value)}
          placeholder="acme"
          autoCapitalize="none"
          required
        />
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@yourco.com"
          required
        />
        <Input
          label="Invite key"
          value={inviteKey}
          onChange={(e) => setInviteKey(e.target.value)}
          placeholder="ABCDE-FGHJK-LMNPQ-RSTUV"
          style={{ fontFamily: "var(--font-mono)", letterSpacing: "0.04em" }}
          required
        />
        <Input
          label="Choose a password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          minLength={12}
          helper="At least 12 characters."
          required
        />
        <Button
          type="submit"
          block
          loading={busy}
          disabled={!tenantSlug.trim() || !email.trim() || !inviteKey.trim()}
          className="auth__actions"
        >
          {busy ? "Joining…" : "Join workspace"}
        </Button>
        {error && (
          <Banner tone="error" style={{ marginTop: "var(--space-md)" }}>
            {error}
          </Banner>
        )}
      </form>
    </AuthShell>
  );
}
